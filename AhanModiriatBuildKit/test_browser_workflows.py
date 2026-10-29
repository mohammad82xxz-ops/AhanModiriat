# -*- coding: utf-8 -*-
"""Browser-driven end-to-end acceptance for core finance and inventory workflows."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

TMP = tempfile.TemporaryDirectory(prefix="ahan_browser_workflows_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def main() -> None:
    app.init()
    security_events = []
    original_security_check = app.Handler._request_security_error
    def tracked_security_check(handler, method):
        error = original_security_check(handler, method)
        security_events.append({"method": method, "fetch_site": handler.headers.get("Sec-Fetch-Site"), "origin": handler.headers.get("Origin"), "referer": handler.headers.get("Referer"), "host": handler.headers.get("Host"), "error": error})
        return error
    app.Handler._request_security_error = tracked_security_check
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page(locale="fa-IR")
                page.set_default_timeout(10000)
                page_errors = []
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))

                # Create a controlled product through the actual UI.
                page.goto(base + "/products", wait_until="networkidle")
                form = page.locator('form[action="/add_product"]')
                form.locator('[name="name"]').fill("Phase2 E2E Steel")
                form.locator('[name="unit"]').select_option(label="کیلوگرم")
                form.locator('[name="purchase_unit"]').fill("کیلو")
                form.locator('[name="purchase_factor"]').fill("1")
                form.locator('[name="sale_unit"]').fill("کیلو")
                form.locator('[name="sale_factor"]').fill("1")
                form.locator('[name="stock"]').fill("10")
                form.locator('[name="avg_cost"]').fill("100")
                form.locator('[name="market_price"]').fill("150")
                form.locator('[name="min_stock"]').fill("1")
                form.locator("button").last.click()
                with app.conn() as c:
                    product = c.execute("SELECT * FROM products WHERE name=?", ("Phase2 E2E Steel",)).fetchone()
                    assert product is not None, f"product was not created through the UI; url={page.url}; body={page.locator('body').inner_text()[:1200]}; security={security_events[-5:]}"
                    product_id = product["id"]
                    assert float(product["stock"]) == 10
                    assert float(product["avg_cost"]) == 100

                # Duplicate product names must be rejected without changing the existing product.
                page.goto(base + "/products", wait_until="networkidle")
                form = page.locator('form[action="/add_product"]')
                form.locator('[name="name"]').fill(" phase2   e2e steel ")
                form.locator('[name="unit"]').select_option(label="کیلوگرم")
                form.locator('[name="purchase_unit"]').fill("کیلو")
                form.locator('[name="purchase_factor"]').fill("1")
                form.locator('[name="sale_unit"]').fill("کیلو")
                form.locator('[name="sale_factor"]').fill("1")
                form.locator('[name="stock"]').fill("999")
                form.locator('[name="avg_cost"]').fill("999")
                form.locator('[name="market_price"]').fill("999")
                form.locator('[name="min_stock"]').fill("1")
                form.locator("button").last.click()
                with app.conn() as c:
                    duplicate_rows = c.execute("SELECT COUNT(*) FROM products WHERE TRIM(name)=? COLLATE NOCASE", ("Phase2 E2E Steel",)).fetchone()[0]
                    product_after_duplicate = c.execute("SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)).fetchone()
                    assert duplicate_rows == 1, f"duplicate product was persisted; count={duplicate_rows}"
                    assert float(product_after_duplicate["stock"]) == 10, "duplicate product submission changed stock"
                    assert float(product_after_duplicate["avg_cost"]) == 100, "duplicate product submission changed average cost"
                assert "این کالا قبلاً ثبت شده است" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"duplicate product rejection message missing; url={page.url}"

                # Whitespace-only product names must be rejected server-side.
                page.goto(base + "/products", wait_until="networkidle")
                form = page.locator('form[action="/add_product"]')
                form.locator('[name="name"]').fill("   ")
                form.locator('[name="stock"]').fill("0")
                form.locator('[name="avg_cost"]').fill("0")
                form.locator('[name="market_price"]').fill("0")
                with app.conn() as c:
                    blank_name_count_before = c.execute("SELECT COUNT(*) FROM products WHERE TRIM(name)=''").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM products WHERE TRIM(name)=''").fetchone()[0] == blank_name_count_before, "whitespace-only product name was persisted"
                assert "نام کالا و ضرایب تبدیل معتبر الزامی هستند" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"whitespace-only product name was not rejected; url={page.url}"

                # Negative initial stock must be rejected without creating a product.
                page.goto(base + "/products", wait_until="networkidle")
                form = page.locator('form[action="/add_product"]')
                form.locator('[name="name"]').fill("Phase2 Negative Stock")
                form.locator('[name="stock"]').fill("-1")
                form.locator('[name="avg_cost"]').fill("0")
                form.locator('[name="market_price"]').fill("0")
                with app.conn() as c:
                    negative_stock_count_before = c.execute("SELECT COUNT(*) FROM products WHERE name='Phase2 Negative Stock'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM products WHERE name='Phase2 Negative Stock'").fetchone()[0] == negative_stock_count_before, "product with negative initial stock was persisted"
                assert "نباید منفی باشند" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"negative initial stock was not rejected; url={page.url}"

                # Service validation must reject negative revenue without ledger or cash side effects.
                page.goto(base + "/services", wait_until="networkidle")
                form = page.locator('form[action="/add_service"]')
                form.locator('[name="title"]').fill("Phase2 Invalid Service")
                form.locator('[name="revenue"]').fill("-10")
                form.locator('[name="cost"]').fill("0")
                form.locator('[name="received"]').fill("0")
                with app.conn() as c:
                    service_count_before = c.execute("SELECT COUNT(*) FROM services WHERE title='Phase2 Invalid Service'").fetchone()[0]
                    service_cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='services'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM services WHERE title='Phase2 Invalid Service'").fetchone()[0] == service_count_before, "service with negative revenue was persisted"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='services'").fetchone()[0] == service_cash_before, "cash movement created for rejected service"
                assert "درآمد باید بیشتر از صفر" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"negative service revenue was not rejected; url={page.url}"

                # Loan validation must reject a remaining balance greater than principal.
                page.goto(base + "/loans", wait_until="networkidle")
                form = page.locator('form[action="/add_loan"]')
                form.locator('[name="title"]').fill("Phase2 Invalid Loan")
                form.locator('[name="principal"]').fill("100")
                form.locator('[name="remaining"]').fill("101")
                form.locator('[name="installment"]').fill("10")
                with app.conn() as c:
                    loan_count_before = c.execute("SELECT COUNT(*) FROM loans WHERE title='Phase2 Invalid Loan'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM loans WHERE title='Phase2 Invalid Loan'").fetchone()[0] == loan_count_before, "loan balance greater than principal was persisted"
                assert "مانده بین صفر و اصل وام باشد" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"invalid loan balance was not rejected; url={page.url}"

                # Negative path: reject a loan payment whose principal portion exceeds remaining principal.
                page.goto(base + "/loans", wait_until="networkidle")
                form = page.locator('form[action="/add_loan"]')
                form.locator('[name="title"]').fill("Phase2 Payment Guard Loan")
                form.locator('[name="principal"]').fill("1000")
                form.locator('[name="remaining"]').fill("100")
                form.locator('[name="installment"]').fill("50")
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    guarded_loan = c.execute("SELECT * FROM loans WHERE title=?", ("Phase2 Payment Guard Loan",)).fetchone()
                    assert guarded_loan is not None, "valid guard loan was not created"
                    guarded_loan_id = guarded_loan["id"]
                    guarded_remaining_before = guarded_loan["remaining"]
                    guarded_payments_before = c.execute("SELECT COUNT(*) FROM loan_payments WHERE loan_id=?", (guarded_loan_id,)).fetchone()[0]
                    guarded_cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments'").fetchone()[0]
                page.goto(base + "/loans", wait_until="networkidle")
                form = page.locator('form[action="/add_payment"]')
                form.locator('[name="loan_id"]').select_option(str(guarded_loan_id))
                form.locator('[name="amount"]').fill("110")
                form.locator('[name="principal_part"]').fill("101")
                form.locator('[name="interest_part"]').fill("9")
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    guarded_loan_after = c.execute("SELECT * FROM loans WHERE id=?", (guarded_loan_id,)).fetchone()
                    assert c.execute("SELECT COUNT(*) FROM loan_payments WHERE loan_id=?", (guarded_loan_id,)).fetchone()[0] == guarded_payments_before, "payment exceeding remaining principal was persisted"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments'").fetchone()[0] == guarded_cash_before, "cash movement created for rejected loan payment"
                    assert guarded_loan_after["remaining"] == guarded_remaining_before, "loan remaining principal changed after rejected payment"
                assert "سهم اصل قسط از مانده اصل وام بیشتر است" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"excess principal payment was not rejected; url={page.url}"

                # A zero market price must not create price history or overwrite the current price.
                page.goto(base + "/prices", wait_until="networkidle")
                form = page.locator('form[action="/add_price"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="market_price"]').fill("0")
                with app.conn() as c:
                    price_count_before = c.execute("SELECT COUNT(*) FROM price_history WHERE product_id=?", (product_id,)).fetchone()[0]
                    current_price_before = c.execute("SELECT market_price FROM products WHERE id=?", (product_id,)).fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM price_history WHERE product_id=?", (product_id,)).fetchone()[0] == price_count_before, "zero price history was persisted"
                    assert c.execute("SELECT market_price FROM products WHERE id=?", (product_id,)).fetchone()[0] == current_price_before, "current market price changed after rejected zero price"
                assert "قیمت روز باید بیشتر از صفر باشد" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"zero market price was not rejected; url={page.url}"

                # The duplicate submission redirects back to /products; start a fresh form
                # rather than reusing the now-detached locator.
                page.goto(base + "/products", wait_until="networkidle")
                form = page.locator('form[action="/add_product"]')
                form.locator('[name="name"]').fill("Phase2 E2E Other")
                form.locator('[name="unit"]').select_option(label="کیلوگرم")
                form.locator('[name="purchase_unit"]').fill("کیلو")
                form.locator('[name="purchase_factor"]').fill("1")
                form.locator('[name="sale_unit"]').fill("کیلو")
                form.locator('[name="sale_factor"]').fill("1")
                form.locator('[name="stock"]').fill("0")
                form.locator('[name="avg_cost"]').fill("0")
                form.locator('[name="market_price"]').fill("0")
                form.locator('[name="min_stock"]').fill("1")
                form.locator("button").last.click()
                with app.conn() as c:
                    other_product = c.execute("SELECT id FROM products WHERE name=?", ("Phase2 E2E Other",)).fetchone()
                    assert other_product is not None, "second test product was not created"
                    other_product_id = other_product["id"]
                page.goto(base + f"/edit_product?id={other_product_id}", wait_until="networkidle")
                form = page.locator('form[action="/update_product"]')
                form.locator('[name="name"]').fill(" phase2   e2e steel ")
                form.locator("button").last.click()
                with app.conn() as c:
                    other_after_duplicate_edit = c.execute("SELECT name FROM products WHERE id=?", (other_product_id,)).fetchone()
                    duplicate_rows = c.execute("SELECT COUNT(*) FROM products WHERE TRIM(name)=? COLLATE NOCASE", ("Phase2 E2E Steel",)).fetchone()[0]
                    assert other_after_duplicate_edit["name"] == "Phase2 E2E Other", "duplicate-name edit changed the second product"
                    assert duplicate_rows == 1, f"editing created a duplicate product name; count={duplicate_rows}"
                assert "نام این کالا با کالای دیگری تکراری است" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"duplicate product edit rejection message missing; url={page.url}"

                # Purchase: stock, weighted average cost, supplier link, and cash posting.
                page.goto(base + "/purchases", wait_until="networkidle")
                form = page.locator('form[action="/add_purchase"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("5")
                form.locator('[name="unit_cost"]').fill("120")
                form.locator('[name="extra_cost"]').fill("0")
                form.locator('[name="paid"]').fill("300")
                form.locator('[name="supplier"]').fill("Phase2 Supplier")
                form.locator('[name="notes"]').fill("phase two browser purchase")
                purchase_payload = form.evaluate("(form) => Object.fromEntries(new FormData(form).entries())")
                form.locator("button").last.click()
                with app.conn() as c:
                    product = c.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                    purchase = c.execute("SELECT * FROM purchases WHERE product_id=? ORDER BY id DESC LIMIT 1", (product_id,)).fetchone()
                    assert purchase is not None, f"purchase was not persisted; url={page.url}; body={page.locator('body').inner_text()[:1200]}; security={security_events[-5:]}"
                    assert float(product["stock"]) == 15, product["stock"]
                    assert abs(float(product["avg_cost"]) - (1600 / 15)) < 0.01, product["avg_cost"]
                    assert purchase["supplier_person_id"], "supplier was not linked to the party directory"
                    postings = c.execute("SELECT amount,kind FROM cash_movements WHERE source_table='purchases' AND source_id=?", (purchase["id"],)).fetchall()
                    assert len(postings) == 1 and (postings[0]["amount"], postings[0]["kind"]) == (300, "withdraw"), [dict(x) for x in postings]
                    purchase_count_before_replay = c.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0]
                    stock_before_replay = float(product["stock"])
                    cash_count_before_replay = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases'").fetchone()[0]

                # Replay the exact successful POST payload as happens with refresh/back or a repeated submit.
                replay_response = page.request.post(base + "/add_purchase", form=purchase_payload)
                assert replay_response.status == 200, f"purchase replay should follow the safe redirect, got {replay_response.status}"
                replay_message = parse_qs(urlparse(replay_response.url).query).get("msg", [""])[0]
                assert "قبلاً ارسال شده" in replay_message, f"replayed purchase was not explicitly rejected: {replay_message}"
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0] == purchase_count_before_replay, "replayed purchase created a duplicate row"
                    assert float(c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]) == stock_before_replay, "replayed purchase changed stock"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases'").fetchone()[0] == cash_count_before_replay, "replayed purchase created a duplicate cash movement"

                # Negative path: reject a purchase with zero quantity, even if browser-side validation is bypassed.
                page.goto(base + "/purchases", wait_until="networkidle")
                form = page.locator('form[action="/add_purchase"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("0")
                form.locator('[name="unit_cost"]').fill("120")
                form.locator('[name="extra_cost"]').fill("0")
                form.locator('[name="paid"]').fill("0")
                with app.conn() as c:
                    purchases_before = c.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0]
                    product_before = c.execute("SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)).fetchone()
                # form.submit() bypasses HTML constraint validation so the server-side guard is exercised.
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    purchases_after = c.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0]
                    product_after = c.execute("SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)).fetchone()
                    assert purchases_after == purchases_before, "zero-quantity purchase was persisted"
                    assert float(product_after["stock"]) == float(product_before["stock"]), "stock changed after invalid purchase"
                    assert float(product_after["avg_cost"]) == float(product_before["avg_cost"]), "average cost changed after invalid purchase"
                assert "کالا، مقدار یا قیمت/هزینه خرید نامعتبر است" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"invalid purchase rejection message missing; url={page.url}; body={page.locator('body').inner_text()[:500]}"

                # Negative path: reject a purchase with a negative extra cost.
                page.goto(base + "/purchases", wait_until="networkidle")
                form = page.locator('form[action="/add_purchase"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("1")
                form.locator('[name="unit_cost"]').fill("120")
                form.locator('[name="extra_cost"]').fill("-1")
                form.locator('[name="paid"]').fill("0")
                with app.conn() as c:
                    negative_extra_purchases_before = c.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0]
                    negative_extra_stock_before = c.execute("SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)).fetchone()
                    negative_extra_cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0] == negative_extra_purchases_before, "purchase with negative extra cost was persisted"
                    negative_extra_stock_after = c.execute("SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)).fetchone()
                    assert tuple(negative_extra_stock_after) == tuple(negative_extra_stock_before), "stock/cost changed after negative purchase extra cost"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases'").fetchone()[0] == negative_extra_cash_before, "cash movement created for negative purchase extra cost"
                assert "نباید منفی باشند" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"negative purchase extra cost rejection message missing; url={page.url}"

                # Negative path: reject a purchase with a negative paid amount.
                page.goto(base + "/purchases", wait_until="networkidle")
                form = page.locator('form[action="/add_purchase"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("1")
                form.locator('[name="unit_cost"]').fill("120")
                form.locator('[name="extra_cost"]').fill("0")
                form.locator('[name="paid"]').fill("-1")
                with app.conn() as c:
                    negative_paid_purchases_before = c.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0]
                    negative_paid_stock_before = c.execute("SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)).fetchone()
                    negative_paid_cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM purchases WHERE product_id=?", (product_id,)).fetchone()[0] == negative_paid_purchases_before, "purchase with negative paid amount was persisted"
                    negative_paid_stock_after = c.execute("SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)).fetchone()
                    assert tuple(negative_paid_stock_after) == tuple(negative_paid_stock_before), "stock/cost changed after negative purchase paid amount"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases'").fetchone()[0] == negative_paid_cash_before, "cash movement created for negative purchase paid amount"
                assert "نباید منفی باشند" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"negative purchase paid amount rejection message missing; url={page.url}"

                # Negative path: reject a sale with zero quantity even when browser validation is bypassed.
                page.goto(base + "/sales", wait_until="networkidle")
                form = page.locator('form[action="/add_sale"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("0")
                form.locator('[name="unit_price"]').fill("200")
                form.locator('[name="extra_cost"]').fill("0")
                form.locator('[name="received"]').fill("0")
                with app.conn() as c:
                    zero_sales_before = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    zero_sale_stock_before = c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    zero_sales_after = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    zero_sale_stock_after = c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
                assert zero_sales_after == zero_sales_before, "zero-quantity sale was persisted"
                assert float(zero_sale_stock_after) == float(zero_sale_stock_before), "stock changed after invalid sale"
                assert "کالا، مقدار یا قیمت/هزینه فروش نامعتبر است" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"invalid sale rejection message missing; url={page.url}; body={page.locator('body').inner_text()[:500]}"

                # Negative path: reject a sale with a missing quantity even if browser validation is bypassed.
                page.goto(base + "/sales", wait_until="networkidle")
                form = page.locator('form[action="/add_sale"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("")
                form.locator('[name="unit_price"]').fill("200")
                form.locator('[name="extra_cost"]').fill("0")
                form.locator('[name="received"]').fill("0")
                with app.conn() as c:
                    missing_qty_sales_before = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    missing_qty_stock_before = c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    missing_qty_sales_after = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    missing_qty_stock_after = c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
                assert missing_qty_sales_after == missing_qty_sales_before, "sale with missing quantity was persisted"
                assert float(missing_qty_stock_after) == float(missing_qty_stock_before), "stock changed after sale with missing quantity"
                assert "کالا، مقدار یا قیمت/هزینه فروش نامعتبر است" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"missing-quantity sale rejection message missing; url={page.url}; body={page.locator('body').inner_text()[:500]}"

                # Negative path: reject a sale with a missing unit price even if browser validation is bypassed.
                page.goto(base + "/sales", wait_until="networkidle")
                form = page.locator('form[action="/add_sale"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("1")
                form.locator('[name="unit_price"]').fill("")
                form.locator('[name="extra_cost"]').fill("0")
                form.locator('[name="received"]').fill("0")
                with app.conn() as c:
                    missing_price_sales_before = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    missing_price_stock_before = c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    missing_price_sales_after = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    missing_price_stock_after = c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
                assert missing_price_sales_after == missing_price_sales_before, "sale with missing unit price was persisted"
                assert float(missing_price_stock_after) == float(missing_price_stock_before), "stock changed after sale with missing unit price"
                assert "کالا، مقدار یا قیمت/هزینه فروش نامعتبر است" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"missing-price sale rejection message missing; url={page.url}; body={page.locator('body').inner_text()[:500]}"

                # Negative path: reject a sale with a negative received amount.
                page.goto(base + "/sales", wait_until="networkidle")
                form = page.locator('form[action="/add_sale"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("1")
                form.locator('[name="unit_price"]').fill("200")
                form.locator('[name="extra_cost"]').fill("0")
                form.locator('[name="received"]').fill("-1")
                with app.conn() as c:
                    negative_received_sales_before = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    negative_received_stock_before = c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
                    negative_received_cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0] == negative_received_sales_before, "sale with negative received amount was persisted"
                    assert float(c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]) == float(negative_received_stock_before), "stock changed after negative received amount"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales'").fetchone()[0] == negative_received_cash_before, "cash movement created for negative received amount"
                assert "نباید منفی باشند" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"negative received amount rejection message missing; url={page.url}"

                # Negative path: reject a sale with a negative extra cost.
                page.goto(base + "/sales", wait_until="networkidle")
                form = page.locator('form[action="/add_sale"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("1")
                form.locator('[name="unit_price"]').fill("200")
                form.locator('[name="extra_cost"]').fill("-1")
                form.locator('[name="received"]').fill("0")
                with app.conn() as c:
                    negative_extra_sales_before = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    negative_extra_sale_stock_before = c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]
                    negative_extra_sale_cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0] == negative_extra_sales_before, "sale with negative extra cost was persisted"
                    assert float(c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]) == float(negative_extra_sale_stock_before), "stock changed after negative sale extra cost"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales'").fetchone()[0] == negative_extra_sale_cash_before, "cash movement created for negative sale extra cost"
                assert "نباید منفی باشند" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"negative sale extra cost rejection message missing; url={page.url}"

                # Negative path: reject a sale that exceeds available stock.
                page.goto(base + "/sales", wait_until="networkidle")
                form = page.locator('form[action="/add_sale"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("999")
                form.locator('[name="unit_price"]').fill("200")
                form.locator('[name="extra_cost"]').fill("0")
                form.locator('[name="received"]').fill("0")
                with app.conn() as c:
                    sales_before = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                form.locator("button").last.click()
                with app.conn() as c:
                    rejected_product = c.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                    sales_after = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    assert float(rejected_product["stock"]) == 15, rejected_product["stock"]
                    assert sales_after == sales_before, "oversale was persisted despite insufficient stock"
                assert "موجودی کافی نیست" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"oversale rejection message was not returned in redirect; url={page.url}; body={page.locator('body').inner_text()[:500]}"

                # Sale: stock reduction, frozen cost basis, profit, and cash receipt.
                page.goto(base + "/sales", wait_until="networkidle")
                form = page.locator('form[action="/add_sale"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="qty"]').fill("3")
                form.locator('[name="unit_price"]').fill("200")
                form.locator('[name="extra_cost"]').fill("10")
                form.locator('[name="received"]').fill("400")
                form.locator('[name="customer"]').fill("Phase2 Customer")
                form.locator('[name="notes"]').fill("phase two browser sale")
                sale_payload = form.evaluate("(form) => Object.fromEntries(new FormData(form).entries())")
                form.locator("button").last.click()
                with app.conn() as c:
                    product = c.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                    sale = c.execute("SELECT * FROM sales WHERE product_id=? ORDER BY id DESC LIMIT 1", (product_id,)).fetchone()
                    assert sale is not None, "sale was not persisted"
                    assert float(product["stock"]) == 12, product["stock"]
                    assert abs(float(sale["cost_basis"]) - (1600 / 15)) < 0.01, sale["cost_basis"]
                    expected_profit = 3 * (200 - float(sale["cost_basis"])) - 10
                    assert abs(expected_profit - (3 * 200 - 1600 / 15 * 3 - 10)) < 0.01
                    postings = c.execute("SELECT amount,kind FROM cash_movements WHERE source_table='sales' AND source_id=?", (sale["id"],)).fetchall()
                    assert len(postings) == 1 and (postings[0]["amount"], postings[0]["kind"]) == (400, "deposit"), [dict(x) for x in postings]
                    assert sale["customer_person_id"], "customer was not linked to the party directory"
                    sale_count_before_replay = c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0]
                    sale_stock_before_replay = float(product["stock"])
                    sale_cash_before_replay = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales'").fetchone()[0]

                replay_response = page.request.post(base + "/add_sale", form=sale_payload)
                assert replay_response.status == 200, f"sale replay should follow the safe redirect, got {replay_response.status}"
                replay_message = parse_qs(urlparse(replay_response.url).query).get("msg", [""])[0]
                assert "قبلاً ارسال شده" in replay_message, f"replayed sale was not explicitly rejected: {replay_message}"
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,)).fetchone()[0] == sale_count_before_replay, "replayed sale created a duplicate row"
                    assert float(c.execute("SELECT stock FROM products WHERE id=?", (product_id,)).fetchone()[0]) == sale_stock_before_replay, "replayed sale changed stock"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales'").fetchone()[0] == sale_cash_before_replay, "replayed sale created a duplicate cash movement"

                # Negative path: missing expense description must not create expense/cash records.
                page.goto(base + "/expenses", wait_until="networkidle")
                form = page.locator('form[action="/add_expense"]')
                form.locator('[name="category"]').fill("")
                form.locator('[name="amount"]').fill("10")
                form.locator('[name="business"]').select_option("1")
                with app.conn() as c:
                    missing_category_before = c.execute("SELECT COUNT(*) FROM expenses WHERE category='' OR category IS NULL").fetchone()[0]
                    missing_category_cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM expenses WHERE category='' OR category IS NULL").fetchone()[0] == missing_category_before, "expense without description was persisted"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses'").fetchone()[0] == missing_category_cash_before, "cash movement created for expense without description"
                assert "شرح، مبلغ یا نوع هزینه معتبر نیست" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"missing-description expense rejection message missing; url={page.url}"

                # Negative paths: missing and zero expense amounts must not create expense/cash records.
                page.goto(base + "/expenses", wait_until="networkidle")
                form = page.locator('form[action="/add_expense"]')
                form.locator('[name="category"]').fill("Phase2 invalid expense")
                form.locator('[name="amount"]').fill("")
                form.locator('[name="business"]').select_option("1")
                with app.conn() as c:
                    invalid_expenses_before = c.execute("SELECT COUNT(*) FROM expenses WHERE category='Phase2 invalid expense'").fetchone()[0]
                    invalid_cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM expenses WHERE category='Phase2 invalid expense'").fetchone()[0] == invalid_expenses_before, "expense with missing amount was persisted"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses'").fetchone()[0] == invalid_cash_before, "cash movement created for expense with missing amount"
                assert "مبلغ باید بیشتر از صفر باشد" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"missing-amount expense rejection message missing; url={page.url}"

                page.goto(base + "/expenses", wait_until="networkidle")
                form = page.locator('form[action="/add_expense"]')
                form.locator('[name="category"]').fill("Phase2 zero expense")
                form.locator('[name="amount"]').fill("0")
                form.locator('[name="business"]').select_option("1")
                with app.conn() as c:
                    zero_expenses_before = c.execute("SELECT COUNT(*) FROM expenses WHERE category='Phase2 zero expense'").fetchone()[0]
                with page.expect_navigation(wait_until="networkidle"):
                    form.evaluate("(form) => form.submit()")
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM expenses WHERE category='Phase2 zero expense'").fetchone()[0] == zero_expenses_before, "zero-amount expense was persisted"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses'").fetchone()[0] == invalid_cash_before, "cash movement created for zero-amount expense"
                assert "مبلغ باید بیشتر از صفر باشد" in parse_qs(urlparse(page.url).query).get("msg", [""])[0], f"zero-amount expense rejection message missing; url={page.url}"

                # Expense: a business expense affects the profit ledger and cash.
                page.goto(base + "/expenses", wait_until="networkidle")
                form = page.locator('form[action="/add_expense"]')
                form.locator('[name="category"]').fill("Phase2 test expense")
                form.locator('[name="amount"]').fill("50")
                form.locator('[name="business"]').select_option("1")
                form.locator('[name="source"]').select_option("سود/درآمد جاری")
                form.locator('[name="notes"]').fill("phase two browser expense")
                expense_payload = form.evaluate("(form) => Object.fromEntries(new FormData(form).entries())")
                form.locator("button").last.click()
                with app.conn() as c:
                    expense = c.execute("SELECT * FROM expenses WHERE category=?", ("Phase2 test expense",)).fetchone()
                    assert expense is not None and expense["amount"] == 50 and expense["business"] == 1
                    postings = c.execute("SELECT amount,kind FROM cash_movements WHERE source_table='expenses' AND source_id=?", (expense["id"],)).fetchall()
                    assert len(postings) == 1 and (postings[0]["amount"], postings[0]["kind"]) == (50, "withdraw"), [dict(x) for x in postings]
                    expense_count_before_replay = c.execute("SELECT COUNT(*) FROM expenses WHERE category=?", ("Phase2 test expense",)).fetchone()[0]
                    expense_cash_before_replay = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses'").fetchone()[0]

                replay_response = page.request.post(base + "/add_expense", form=expense_payload)
                assert replay_response.status == 200, f"expense replay should follow the safe redirect, got {replay_response.status}"
                replay_message = parse_qs(urlparse(replay_response.url).query).get("msg", [""])[0]
                assert "قبلاً ارسال شده" in replay_message, f"replayed expense was not explicitly rejected: {replay_message}"
                with app.conn() as c:
                    assert c.execute("SELECT COUNT(*) FROM expenses WHERE category=?", ("Phase2 test expense",)).fetchone()[0] == expense_count_before_replay, "replayed expense created a duplicate row"
                    assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses'").fetchone()[0] == expense_cash_before_replay, "replayed expense created a duplicate cash movement"

                # Physical count: apply only the difference and preserve average cost.
                page.goto(base + "/inventory", wait_until="networkidle")
                form = page.locator('form[action="/inventory_adjust"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="counted_qty"]').fill("11")
                form.locator('[name="reason"]').fill("Phase2 physical count")
                form.locator('[name="notes"]').fill("phase two browser inventory adjustment")
                form.locator("button").last.click()
                with app.conn() as c:
                    product = c.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                    adjustment = c.execute("SELECT * FROM inventory_adjustments WHERE product_id=? ORDER BY id DESC LIMIT 1", (product_id,)).fetchone()
                    assert adjustment is not None, "inventory adjustment was not persisted"
                    assert float(product["stock"]) == 11, product["stock"]
                    assert float(adjustment["expected_qty"]) == 12
                    assert float(adjustment["counted_qty"]) == 11
                    assert float(adjustment["delta_qty"]) == -1
                    assert abs(float(product["avg_cost"]) - (1600 / 15)) < 0.01, product["avg_cost"]
                    assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                    assert c.execute("PRAGMA foreign_key_check").fetchall() == []

                assert not page_errors, page_errors
                print("BROWSER WORKFLOWS PASSED: product -> purchase -> sale -> expense -> physical inventory count.")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        TMP.cleanup()


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

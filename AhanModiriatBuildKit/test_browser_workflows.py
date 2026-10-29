# -*- coding: utf-8 -*-
"""Browser-driven end-to-end acceptance for core finance and inventory workflows."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_browser_workflows_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402


def main() -> None:
    app.init()
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
                form.locator("button").first.click()
                with app.conn() as c:
                    product = c.execute("SELECT * FROM products WHERE name=?", ("Phase2 E2E Steel",)).fetchone()
                    assert product is not None, f"product was not created through the UI; url={page.url}; body={page.locator('body').inner_text()[:1200]}"
                    product_id = product["id"]
                    assert float(product["stock"]) == 10
                    assert float(product["avg_cost"]) == 100

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
                form.locator("button").first.click()
                with app.conn() as c:
                    product = c.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
                    purchase = c.execute("SELECT * FROM purchases WHERE product_id=? ORDER BY id DESC LIMIT 1", (product_id,)).fetchone()
                    assert purchase is not None, "purchase was not persisted"
                    assert float(product["stock"]) == 15, product["stock"]
                    assert abs(float(product["avg_cost"]) - (1600 / 15)) < 0.01, product["avg_cost"]
                    assert purchase["supplier_person_id"], "supplier was not linked to the party directory"
                    postings = c.execute("SELECT amount,kind FROM cash_movements WHERE source_table='purchases' AND source_id=?", (purchase["id"],)).fetchall()
                    assert len(postings) == 1 and (postings[0]["amount"], postings[0]["kind"]) == (300, "withdraw"), [dict(x) for x in postings]

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
                form.locator("button").first.click()
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

                # Expense: a business expense affects the profit ledger and cash.
                page.goto(base + "/expenses", wait_until="networkidle")
                form = page.locator('form[action="/add_expense"]')
                form.locator('[name="category"]').fill("Phase2 test expense")
                form.locator('[name="amount"]').fill("50")
                form.locator('[name="business"]').select_option("1")
                form.locator('[name="source"]').select_option("سود/درآمد جاری")
                form.locator('[name="notes"]').fill("phase two browser expense")
                form.locator("button").first.click()
                with app.conn() as c:
                    expense = c.execute("SELECT * FROM expenses WHERE category=?", ("Phase2 test expense",)).fetchone()
                    assert expense is not None and expense["amount"] == 50 and expense["business"] == 1
                    postings = c.execute("SELECT amount,kind FROM cash_movements WHERE source_table='expenses' AND source_id=?", (expense["id"],)).fetchall()
                    assert len(postings) == 1 and (postings[0]["amount"], postings[0]["kind"]) == (50, "withdraw"), [dict(x) for x in postings]

                # Physical count: apply only the difference and preserve average cost.
                page.goto(base + "/inventory", wait_until="networkidle")
                form = page.locator('form[action="/inventory_adjust"]')
                form.locator('[name="product_id"]').select_option(str(product_id))
                form.locator('[name="counted_qty"]').fill("11")
                form.locator('[name="reason"]').fill("Phase2 physical count")
                form.locator('[name="notes"]').fill("phase two browser inventory adjustment")
                form.locator("button").first.click()
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

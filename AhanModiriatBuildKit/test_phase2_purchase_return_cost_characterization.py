# -*- coding: utf-8 -*-
"""Acceptance tests for owner-approved purchase-return valuation policy DEC-01.

Returns are valued at the source purchase cost plus a proportional share of
ancillary costs. Cumulative allocation avoids rounding drift across partial
returns; the remaining stock average is recalculated from remaining book value.
"""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_purchase_return_policy_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def post(port, fields):
    with app.conn() as c:
        markup = app.submission_token(c, "add_purchase_return")
    token = markup.split('value="', 1)[1].split('"', 1)[0]
    payload = dict(fields, _submission_token=token)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/add_purchase_return",
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        return urllib.parse.parse_qs(
            urllib.parse.urlparse(response.geturl()).query
        ).get("msg", [""])[0]


def add_product(c, name, stock, avg_cost, purchase_unit="kg", factor=1):
    cur = c.execute(
        """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock,
                   purchase_unit,purchase_factor,sale_unit,sale_factor)
           VALUES(?, 'kg', ?, ?, 9000, 0, ?, ?, 'kg', 1)""",
        (name, stock, avg_cost, purchase_unit, factor),
    )
    return cur.lastrowid


def add_purchase(c, product_id, qty, unit_cost, extra_cost):
    cur = c.execute(
        """INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,
                   supplier,paid,notes)
           VALUES('2026-01-01',?,?,?,?,'Fixture Supplier',0,'DEC-01 fixture')""",
        (product_id, qty, unit_cost, extra_cost),
    )
    return cur.lastrowid


def main():
    app.init()
    with app.conn() as c:
        # Purchase unit conversion: 5 bundles × 2 kg = 10 kg.
        # Purchase value = 5 × 8,000 + 4,000 ancillary = 44,000 rial.
        product_id = add_product(c, "DEC01 mixed-cost bundle", 20, 8000, "bundle", 2)
        purchase_id = add_purchase(c, product_id, 5, 8000, 4000)

        # A separate fixture proves cumulative proportional allocation has no
        # one-rial drift across multiple partial returns.
        rounding_product_id = add_product(c, "DEC01 rounding", 6, 2000)
        rounding_purchase_id = add_purchase(c, rounding_product_id, 3, 1000, 1)

        # Returning at source cost greater than the entire current book value
        # must be rejected instead of creating a negative inventory valuation.
        overvalue_product_id = add_product(c, "DEC01 overvalue guard", 1, 100)
        overvalue_purchase_id = add_purchase(c, overvalue_product_id, 1, 200, 0)

        # If all units are returned but book value remains, reject the orphaned
        # value instead of silently dropping it when average cost becomes zero.
        zero_stock_product_id = add_product(c, "DEC01 zero-stock guard", 2, 1000)
        zero_stock_purchase_id = add_purchase(c, zero_stock_product_id, 2, 500, 0)

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # First partial return: source cost 8,000 + ancillary share 800 per kg.
        post(port, {
            "purchase_id": purchase_id, "date": "2026-01-02", "qty": "2",
            "cash_refund": "500", "reason": "first partial return",
        })
        with app.conn() as c:
            product = c.execute(
                "SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)
            ).fetchone()
            returned = c.execute(
                "SELECT qty,return_value,cash_refund FROM purchase_returns WHERE purchase_id=?",
                (purchase_id,),
            ).fetchone()
            assert product["stock"] == 18, dict(product)
            assert product["avg_cost"] == 8400, dict(product)
            assert returned["qty"] == 2, dict(returned)
            assert returned["return_value"] == 8800, dict(returned)
            assert returned["cash_refund"] == 5000, dict(returned)

        # Second partial return allocates the next share from the cumulative
        # source value, then recomputes average cost on the remaining 15 kg.
        post(port, {
            "purchase_id": purchase_id, "date": "2026-01-03", "qty": "3",
            "cash_refund": "300", "reason": "second partial return",
        })
        with app.conn() as c:
            product = c.execute(
                "SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)
            ).fetchone()
            rows = c.execute(
                "SELECT qty,return_value,cash_refund FROM purchase_returns WHERE purchase_id=? ORDER BY id",
                (purchase_id,),
            ).fetchall()
            assert product["stock"] == 15, dict(product)
            assert product["avg_cost"] == 9200, dict(product)
            assert [row["return_value"] for row in rows] == [8800, 13200]
            assert sum(row["return_value"] for row in rows) == 22000
            assert sum(row["cash_refund"] for row in rows) == 8000
            cash_total = c.execute(
                "SELECT COALESCE(SUM(amount),0) FROM cash_movements WHERE source_table='purchase_returns'"
            ).fetchone()[0]
            assert cash_total == 8000, cash_total
            supplier_balances = app.party_balances(c)
            assert supplier_balances["Fixture Supplier"]["payable"] == 34201, supplier_balances

        # Partial allocation of 3,001 rial over 3 kg must total exactly 3,001,
        # even when the owner records three separate one-kilogram returns.
        for day in ("04", "05", "06"):
            post(port, {
                "purchase_id": rounding_purchase_id,
                "date": f"2026-01-{day}", "qty": "1",
                "cash_refund": "0", "reason": "rounding allocation",
            })
        with app.conn() as c:
            values = [
                row[0] for row in c.execute(
                    "SELECT return_value FROM purchase_returns WHERE purchase_id=? ORDER BY id",
                    (rounding_purchase_id,),
                )
            ]
            product = c.execute(
                "SELECT stock,avg_cost FROM products WHERE id=?",
                (rounding_product_id,),
            ).fetchone()
            assert values == [1000, 1001, 1000], values
            assert sum(values) == 3001
            assert product["stock"] == 3 and product["avg_cost"] == 3000, dict(product)

        # A source return that would drive remaining book value below zero is rejected atomically.
        message = post(port, {
            "purchase_id": overvalue_purchase_id, "date": "2026-01-07", "qty": "1",
            "cash_refund": "0", "reason": "over-value rejection",
        })
        assert "بیشتر است" in message, message
        # A zero-stock result cannot leave a residual inventory value with no units.
        message = post(port, {
            "purchase_id": zero_stock_purchase_id, "date": "2026-01-08", "qty": "2",
            "cash_refund": "0", "reason": "orphan-value rejection",
        })
        assert "ارزش دفتری باقی می‌ماند" in message, message

        with app.conn() as c:
            assert c.execute(
                "SELECT COUNT(*) FROM purchase_returns WHERE purchase_id IN (?,?)",
                (overvalue_purchase_id, zero_stock_purchase_id),
            ).fetchone()[0] == 0
            for pid, expected_stock, expected_avg in (
                (overvalue_product_id, 1, 100),
                (zero_stock_product_id, 2, 1000),
            ):
                product = c.execute(
                    "SELECT stock,avg_cost FROM products WHERE id=?", (pid,)
                ).fetchone()
                assert product["stock"] == expected_stock, dict(product)
                assert product["avg_cost"] == expected_avg, dict(product)
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print("PURCHASE RETURN DEC-01 POLICY TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

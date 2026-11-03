# -*- coding: utf-8 -*-
"""B1 characterization for partial returns and purchase-unit factors.

This test freezes existing route semantics with synthetic data only. It does
not approve the valuation policy or any proposed quantity redesign.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_return_characterization_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def post(port: int, path: str, fields: dict[str, object]) -> str:
    payload = dict(fields)
    with app.conn() as c:
        markup = app.submission_token(c, path)
    payload["_submission_token"] = markup.split('value="', 1)[1].split('"', 1)[0]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{path}",
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        return response.read().decode("utf-8")


def main() -> None:
    app.init()
    with app.conn() as c:
        c.execute(
            """INSERT INTO products(
                   name,unit,stock,avg_cost,market_price,min_stock,
                   purchase_unit,purchase_factor,sale_unit,sale_factor
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("phase2 purchase return fixture", "kg", 20, 30, 100, 0,
             "bundle", 5, "kg", 1),
        )
        purchase_product_id = c.execute(
            "SELECT id FROM products WHERE name=?",
            ("phase2 purchase return fixture",),
        ).fetchone()[0]
        purchase_id = c.execute(
            """INSERT INTO purchases(
                   date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes
               ) VALUES(?,?,?,?,?,?,?,?)""",
            ("2026-02-01", purchase_product_id, 2, 10000, 1000,
             "B1 return supplier", 21000, "synthetic purchase source"),
        ).lastrowid

        c.execute(
            """INSERT INTO products(
                   name,unit,stock,avg_cost,market_price,min_stock,
                   purchase_unit,purchase_factor,sale_unit,sale_factor
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("phase2 sales return fixture", "kg", 5, 30, 300, 0,
             "kg", 1, "box", 2),
        )
        sale_product_id = c.execute(
            "SELECT id FROM products WHERE name=?",
            ("phase2 sales return fixture",),
        ).fetchone()[0]
        sale_id = c.execute(
            """INSERT INTO sales(
                   date,product_id,qty,unit_price,extra_cost,customer,
                   received,notes,cost_basis,line_total
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("2026-02-02", sale_product_id, 10, 30000, 10000,
             "B1 return customer", 300000, "synthetic sale source", 3000, 300000),
        ).lastrowid

        app.ensure_person(c, "B1 return supplier", "supplier")
        app.ensure_person(c, "B1 return customer", "customer")
        app.sync_cash_posting(
            c, "purchases", purchase_id, "2026-02-01", 21000,
            "out", "B1 return supplier", "synthetic purchase source",
        )
        app.sync_cash_posting(
            c, "sales", sale_id, "2026-02-02", 300000,
            "in", "B1 return customer", "synthetic sale source",
        )

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # purchase_returns.qty is currently expressed in base units, whereas
        # purchases.qty remains expressed in purchase units.
        post(port, "add_purchase_return", {
            "purchase_id": purchase_id,
            "date": "2026-02-03",
            "qty": "2.5",
            "cash_refund": "40",
            "reason": "synthetic partial purchase return",
            "notes": "2.5 kg from a 2 bundle purchase at factor 5",
        })
        with app.conn() as c:
            purchase_product = c.execute(
                "SELECT * FROM products WHERE id=?", (purchase_product_id,)
            ).fetchone()
            purchase = c.execute(
                "SELECT * FROM purchases WHERE id=?", (purchase_id,)
            ).fetchone()
            purchase_return = c.execute(
                "SELECT * FROM purchase_returns WHERE purchase_id=?",
                (purchase_id,),
            ).fetchone()
            assert purchase["qty"] == 2, purchase["qty"]
            assert purchase_return["qty"] == 2.5, purchase_return["qty"]
            assert purchase_product["stock"] == 17.5, purchase_product["stock"]
            assert purchase_return["return_value"] == 5250, purchase_return["return_value"]
            assert purchase_return["cash_refund"] == 400, purchase_return["cash_refund"]
            assert c.execute(
                """SELECT amount FROM cash_movements
                   WHERE source_table='purchase_returns' AND source_id=?""",
                (purchase_return["id"],),
            ).fetchone()[0] == 400

        # A second partial purchase return exhausts the original 10 kg
        # purchase entitlement. A further return must be rejected without
        # inserting a row or changing stock.
        post(port, "add_purchase_return", {
            "purchase_id": purchase_id,
            "date": "2026-02-06",
            "qty": "7.5",
            "cash_refund": "150",
            "reason": "synthetic final purchase return",
            "notes": "remaining 7.5 kg",
        })
        over_purchase_page = post(port, "add_purchase_return", {
            "purchase_id": purchase_id,
            "date": "2026-02-07",
            "qty": "0.1",
            "cash_refund": "1",
            "reason": "synthetic over-return attempt",
            "notes": "must be rejected",
        })
        assert "مقدار مرجوعی از خرید اصلی بیشتر است" in over_purchase_page
        with app.conn() as c:
            purchase_rows = c.execute(
                "SELECT * FROM purchase_returns WHERE purchase_id=? ORDER BY id",
                (purchase_id,),
            ).fetchall()
            purchase_product = c.execute(
                "SELECT * FROM products WHERE id=?", (purchase_product_id,)
            ).fetchone()
            assert [r["qty"] for r in purchase_rows] == [2.5, 7.5]
            assert [r["return_value"] for r in purchase_rows] == [5250, 15750]
            assert sum(r["qty"] for r in purchase_rows) == 10
            assert sum(r["return_value"] for r in purchase_rows) == 21000
            assert sum(r["cash_refund"] for r in purchase_rows) == 19000
            assert purchase_product["stock"] == 10, purchase_product["stock"]
            assert c.execute(
                """SELECT SUM(amount) FROM cash_movements
                   WHERE source_table='purchase_returns' AND source_id IN
                     (SELECT id FROM purchase_returns WHERE purchase_id=?)""",
                (purchase_id,),
            ).fetchone()[0] == 19000

        # Two partial sales returns allocate the remaining line value and
        # extra cost against the remaining quantity on each successive return.
        post(port, "add_sales_return", {
            "sale_id": sale_id,
            "date": "2026-02-04",
            "qty": "2",
            "refund_amount": "500",
            "reason": "synthetic first partial sales return",
            "notes": "first partial return",
        })
        post(port, "add_sales_return", {
            "sale_id": sale_id,
            "date": "2026-02-05",
            "qty": "3",
            "refund_amount": "700",
            "reason": "synthetic second partial sales return",
            "notes": "second partial return",
        })
        # Return the final 5 kg in a third step, then prove that an
        # additional return is rejected and has no database side effects.
        post(port, "add_sales_return", {
            "sale_id": sale_id,
            "date": "2026-02-06",
            "qty": "5",
            "refund_amount": "1200",
            "reason": "synthetic final sales return",
            "notes": "remaining 5 kg",
        })
        over_sale_page = post(port, "add_sales_return", {
            "sale_id": sale_id,
            "date": "2026-02-07",
            "qty": "0.1",
            "refund_amount": "1",
            "reason": "synthetic over-return attempt",
            "notes": "must be rejected",
        })
        assert "مقدار مرجوعی از ماندهٔ قابل برگشت بیشتر است" in over_sale_page
        with app.conn() as c:
            returns = c.execute(
                """SELECT * FROM sales_returns
                   WHERE sale_id=? ORDER BY id""",
                (sale_id,),
            ).fetchall()
            sale_product = c.execute(
                "SELECT * FROM products WHERE id=?", (sale_product_id,)
            ).fetchone()
            assert len(returns) == 3, len(returns)
            assert [r["qty"] for r in returns] == [2, 3, 5]
            assert [r["return_value"] for r in returns] == [60000, 90000, 150000]
            assert [r["extra_reversed"] for r in returns] == [2000, 3000, 5000]
            assert [r["refund_amount"] for r in returns] == [5000, 7000, 12000]
            assert sum(r["qty"] for r in returns) == 10
            assert sum(r["return_value"] for r in returns) == 300000
            assert sum(r["extra_reversed"] for r in returns) == 10000
            assert sum(r["refund_amount"] for r in returns) == 24000
            assert sale_product["stock"] == 15, sale_product["stock"]
            assert c.execute(
                """SELECT SUM(amount) FROM cash_movements
                   WHERE source_table='sales_returns' AND source_id IN
                     (SELECT id FROM sales_returns WHERE sale_id=?)""",
                (sale_id,),
            ).fetchone()[0] == 24000
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        TMP.cleanup()

    print("PHASE 2 RETURN QUANTITY CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

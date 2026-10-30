# -*- coding: utf-8 -*-
"""Regression tests for malformed edits and opening-capital validation."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_validation_edges_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def post(port: int, path: str, fields: dict[str, object]) -> None:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{path}",
        data=data,
        headers={
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200


def snapshot(product_id: int, purchase_id: int, sale_id: int):
    with app.conn() as c:
        product = c.execute(
            "SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)
        ).fetchone()
        purchase = c.execute(
            "SELECT qty,unit_cost,extra_cost,paid FROM purchases WHERE id=?",
            (purchase_id,),
        ).fetchone()
        sale = c.execute(
            "SELECT qty,unit_price,extra_cost,received FROM sales WHERE id=?",
            (sale_id,),
        ).fetchone()
        cash = c.execute(
            "SELECT source_table,source_id,kind,amount FROM cash_movements ORDER BY id"
        ).fetchall()
        capital = c.execute(
            "SELECT amount,date FROM opening_capital WHERE id=1"
        ).fetchone()
        account = c.execute(
            "SELECT opening_balance FROM cash_accounts WHERE id=1"
        ).fetchone()
        return (
            tuple(product),
            tuple(purchase),
            tuple(sale),
            tuple(tuple(row) for row in cash),
            tuple(capital) if capital else None,
            tuple(account) if account else None,
        )


def main() -> None:
    app.init()
    with app.conn() as c:
        c.execute(
            """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock,
                       purchase_unit,purchase_factor,sale_unit,sale_factor)
               VALUES('phase2 validation steel','kg',10,5,20,0,'kg',1,'kg',1)"""
        )
        product_id = c.execute(
            "SELECT id FROM products WHERE name='phase2 validation steel'"
        ).fetchone()[0]
        purchase_cur = c.execute(
            """INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
               VALUES('2026-01-01',?,2,5,0,'Validation supplier',5,'baseline purchase')""",
            (product_id,),
        )
        purchase_id = purchase_cur.lastrowid
        sale_cur = c.execute(
            """INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
               VALUES('2026-01-02',?,2,20,0,'Validation customer',20,'baseline sale',5)""",
            (product_id,),
        )
        sale_id = sale_cur.lastrowid
        app.sync_cash_posting(
            c, "purchases", purchase_id, "2026-01-01", 5,
            "out", "Validation supplier", "baseline purchase",
        )
        app.sync_cash_posting(
            c, "sales", sale_id, "2026-01-02", 20,
            "in", "Validation customer", "baseline sale",
        )
        c.execute("UPDATE opening_capital SET amount=100,date='2026-01-01' WHERE id=1")
        c.execute("UPDATE cash_accounts SET opening_balance=100 WHERE id=1")

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        baseline = snapshot(product_id, purchase_id, sale_id)

        # Update routes must reject NaN/Infinity rather than allowing non-finite
        # values to flow into inventory or weighted-average-cost calculations.
        invalid_updates = [
            ("update_purchase", {
                "record_id": purchase_id, "qty": "nan", "unit_cost": "5",
                "extra_cost": "0", "paid": "5", "supplier": "Validation supplier",
            }),
            ("update_purchase", {
                "record_id": purchase_id, "qty": "2", "unit_cost": "inf",
                "extra_cost": "0", "paid": "5", "supplier": "Validation supplier",
            }),
            ("update_sale", {
                "record_id": sale_id, "qty": "inf", "unit_price": "20",
                "extra_cost": "0", "received": "20", "customer": "Validation customer",
            }),
        ]
        for route, fields in invalid_updates:
            post(port, route, fields)
            assert snapshot(product_id, purchase_id, sale_id) == baseline, (
                f"{route} accepted malformed numeric input: {fields}"
            )

        # New sales reject a zero unit price; editing an existing sale must enforce
        # the same business rule and must not rewrite stock or cash on rejection.
        post(port, "update_sale", {
            "record_id": sale_id, "qty": "2", "unit_price": "0",
            "extra_cost": "0", "received": "0", "customer": "Validation customer",
        })
        assert snapshot(product_id, purchase_id, sale_id) == baseline, (
            "zero-price sale edit was accepted or caused side effects"
        )

        # Opening capital is a non-negative monetary balance and malformed/blank
        # values must not silently coerce to zero.
        for invalid_amount in ("-1", "not-a-number", ""):
            post(port, "save_capital", {
                "amount": invalid_amount, "date": "2026-01-03",
            })
            assert snapshot(product_id, purchase_id, sale_id) == baseline, (
                f"invalid opening capital was persisted: {invalid_amount!r}"
            )

        with app.conn() as c:
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        TMP.cleanup()
    print("PHASE 2 VALIDATION EDGE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

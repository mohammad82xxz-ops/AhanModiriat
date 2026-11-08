# -*- coding: utf-8 -*-
"""Characterize purchase-return valuation when current average cost differs from source cost.

This records current behavior only. DEC-01 remains Pending; the assertions are
not an accounting-policy approval and must not be treated as target behavior.
"""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_purchase_return_cost_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


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
        return response.read().decode("utf-8")


def main():
    app.init()
    with app.conn() as c:
        c.execute(
            """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock,
                       purchase_unit,purchase_factor,sale_unit,sale_factor)
               VALUES('mixed-cost return fixture','kg',20,8000,9000,0,'kg',1,'kg',1)"""
        )
        product_id = c.execute(
            "SELECT id FROM products WHERE name='mixed-cost return fixture'"
        ).fetchone()[0]
        purchase = c.execute(
            """INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,
                       supplier,paid,notes)
               VALUES('2026-01-01',?,10,4000,0,'Fixture Supplier',0,'historical-cost source')""",
            (product_id,),
        )
        purchase_id = purchase.lastrowid

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        post(port, {
            "purchase_id": purchase_id,
            "date": "2026-01-02",
            "qty": "2",
            "cash_refund": "500",
            "reason": "characterization only",
            "notes": "DEC-01 remains pending",
        })
        with app.conn() as c:
            product = c.execute(
                "SELECT stock,avg_cost FROM products WHERE id=?", (product_id,)
            ).fetchone()
            returned = c.execute(
                "SELECT qty,return_value,cash_refund FROM purchase_returns WHERE purchase_id=?",
                (purchase_id,),
            ).fetchone()

            # Current implementation: source-purchase cost values the return,
            # while the cached current average cost is left unchanged.
            assert product["stock"] == 18, dict(product)
            assert product["avg_cost"] == 8000, dict(product)
            assert returned["qty"] == 2, dict(returned)
            assert returned["return_value"] == 8000, dict(returned)
            assert returned["cash_refund"] == 5000, dict(returned)
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        server.shutdown()
        server.server_close()

    print("PURCHASE RETURN COST CHARACTERIZATION PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

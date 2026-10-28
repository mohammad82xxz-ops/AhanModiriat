# -*- coding: utf-8 -*-
"""HTTP-level tests for editing/deleting purchases, sales and expenses."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_transaction_reversals_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def post(port, path, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{path}",
        data=data,
        headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        return response.read().decode("utf-8")


def main():
    app.init()
    with app.conn() as c:
        c.execute("""INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock,
                     purchase_unit,purchase_factor,sale_unit,sale_factor)
                     VALUES('reversal steel','kg',10,5,10,0,'kg',1,'kg',1)""")
        pid = c.execute("SELECT id FROM products WHERE name='reversal steel'").fetchone()[0]

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        post(port, "add_purchase", {
            "date":"2026-01-03","product_id":pid,"qty":"5","unit_cost":"10",
            "extra_cost":"0","paid":"25","supplier":"Supplier A","notes":"initial purchase"
        })
        with app.conn() as c:
            purchase = c.execute("SELECT * FROM purchases ORDER BY id DESC LIMIT 1").fetchone()
            purchase_id = purchase["id"]
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 15
            assert abs(p["avg_cost"] - (100/15)) < 0.000001
            linked = c.execute("SELECT * FROM cash_movements WHERE source_table='purchases' AND source_id=?", (purchase_id,)).fetchall()
            assert len(linked) == 1 and linked[0]["amount"] == 25, [dict(x) for x in linked]

        # Edit the latest purchase: stock and weighted-average value must reverse old values first.
        page = post(port, "update_purchase", {
            "record_id":purchase_id,"qty":"4","unit_cost":"8","extra_cost":"0",
            "paid":"20","supplier":"Supplier A revised","notes":"edited purchase"
        })
        assert "ثبت خرید" in page
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            purchase = c.execute("SELECT * FROM purchases WHERE id=?", (purchase_id,)).fetchone()
            assert p["stock"] == 14 and abs(p["avg_cost"] - (82/14)) < 0.000001
            assert purchase["qty"] == 4 and purchase["unit_cost"] == 8
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='purchases' AND source_id=?", (purchase_id,)).fetchone()[0] == 20

        post(port, "delete_purchase", {"record_id":purchase_id})
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 10 and abs(p["avg_cost"] - 5) < 0.000001
            assert c.execute("SELECT COUNT(*) FROM purchases WHERE id=?", (purchase_id,)).fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases' AND source_id=?", (purchase_id,)).fetchone()[0] == 0

        post(port, "add_sale", {
            "date":"2026-01-04","product_id":pid,"qty":"3","unit_price":"20",
            "extra_cost":"0","received":"30","customer":"Customer A","notes":"initial sale"
        })
        with app.conn() as c:
            sale = c.execute("SELECT * FROM sales ORDER BY id DESC LIMIT 1").fetchone()
            sale_id = sale["id"]
            assert c.execute("SELECT qty FROM sales WHERE id=?", (sale_id,)).fetchone()[0] == 3
            assert c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0] == 7
            assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales' AND source_id=?", (sale_id,)).fetchone()[0] == 1

        post(port, "update_sale", {
            "record_id":sale_id,"qty":"2","unit_price":"30","extra_cost":"0",
            "received":"40","customer":"Customer A revised","notes":"edited sale"
        })
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 8 and p["avg_cost"] == 5
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='sales' AND source_id=?", (sale_id,)).fetchone()[0] == 40

        post(port, "delete_sale", {"record_id":sale_id})
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 10 and p["avg_cost"] == 5
            assert c.execute("SELECT COUNT(*) FROM sales WHERE id=?", (sale_id,)).fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales' AND source_id=?", (sale_id,)).fetchone()[0] == 0

        post(port, "add_expense", {
            "date":"2026-01-05","category":"test expense","amount":"100",
            "business":"1","source":"نامشخص","notes":"initial expense"
        })
        with app.conn() as c:
            expense = c.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
            expense_id = expense["id"]
        post(port, "update_expense", {
            "record_id":expense_id,"date":"2026-01-06","category":"edited expense","amount":"80",
            "business":"0","source":"سرمایه/پس‌انداز","notes":"edited expense"
        })
        with app.conn() as c:
            expense = c.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
            assert expense["amount"] == 80 and expense["business"] == 0 and expense["date"] == "2026-01-06"
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='expenses' AND source_id=?", (expense_id,)).fetchone()[0] == 80
        post(port, "delete_expense", {"record_id":expense_id})
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM expenses WHERE id=?", (expense_id,)).fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses' AND source_id=?", (expense_id,)).fetchone()[0] == 0
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        server.shutdown()
        server.server_close()
    print("TRANSACTION EDIT/DELETE REVERSAL TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

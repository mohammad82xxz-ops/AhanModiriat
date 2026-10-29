# -*- coding: utf-8 -*-
"""HTTP-level tests for editing/deleting purchases, sales and expenses."""
import os
import json
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


def post(port, path, fields, auto_token=True):
    fields = dict(fields)
    if auto_token and path in ("add_purchase", "add_sale", "add_expense") and "_submission_token" not in fields:
        with app.conn() as c:
            token_markup = app.submission_token(c, path)
            fields["_submission_token"] = token_markup.split('value="', 1)[1].split('"', 1)[0]
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
    assert app.money_int("80.5") == 81
    assert app.money_int("80.4") == 80
    assert app.money_int("-80.5") == -81
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
        # The server must reject direct protected POSTs that omit a form token.
        missing_token_cases = [
            ("add_purchase", {"date":"2026-01-03","product_id":pid,"qty":"1","unit_cost":"10","extra_cost":"0","paid":"0","supplier":"Missing token","notes":"reject"}),
            ("add_sale", {"date":"2026-01-03","product_id":pid,"qty":"1","unit_price":"20","extra_cost":"0","received":"0","customer":"Missing token","notes":"reject"}),
            ("add_expense", {"date":"2026-01-03","category":"missing token","amount":"10","business":"1","source":"نامشخص","notes":"reject"}),
        ]
        with app.conn() as c:
            before_missing_token = (
                c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
                c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
            )
        for route, fields in missing_token_cases:
            post(port, route, fields, auto_token=False)
        with app.conn() as c:
            after_missing_token = (
                c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
                c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
            )
            assert after_missing_token == before_missing_token, (before_missing_token, after_missing_token)
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        # Invalid product references and malformed quantities must fail atomically.
        invalid_input_cases = [
            ("add_purchase", {"date":"2026-01-03","product_id":pid + 99999,"qty":"1","unit_cost":"10","extra_cost":"0","paid":"0","supplier":"Invalid product","notes":"reject"}),
            ("add_sale", {"date":"2026-01-03","product_id":pid + 99999,"qty":"1","unit_price":"20","extra_cost":"0","received":"0","customer":"Invalid product","notes":"reject"}),
            ("add_purchase", {"date":"2026-01-03","product_id":pid,"qty":"not-a-number","unit_cost":"10","extra_cost":"0","paid":"0","supplier":"Invalid quantity","notes":"reject"}),
            ("add_sale", {"date":"2026-01-03","product_id":pid,"qty":"not-a-number","unit_price":"20","extra_cost":"0","received":"0","customer":"Invalid quantity","notes":"reject"}),
            ("add_purchase", {"date":"2026-01-03","product_id":pid,"qty":"-1","unit_cost":"10","extra_cost":"0","paid":"0","supplier":"Negative quantity","notes":"reject"}),
            ("add_sale", {"date":"2026-01-03","product_id":pid,"qty":"-1","unit_price":"20","extra_cost":"0","received":"0","customer":"Negative quantity","notes":"reject"}),
        ]
        with app.conn() as c:
            before_invalid_input = (
                c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
                c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
                c.execute("SELECT avg_cost FROM products WHERE id=?", (pid,)).fetchone()[0],
            )
        for route, fields in invalid_input_cases:
            post(port, route, fields)
        with app.conn() as c:
            after_invalid_input = (
                c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
                c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
                c.execute("SELECT avg_cost FROM products WHERE id=?", (pid,)).fetchone()[0],
            )
            assert after_invalid_input == before_invalid_input, (before_invalid_input, after_invalid_input)
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        # A valid token is scoped to its intended route and cannot authorize another transaction type.
        with app.conn() as c:
            purchase_token_markup = app.submission_token(c, "add_purchase")
            purchase_token = purchase_token_markup.split('value="', 1)[1].split('"', 1)[0]
            before_wrong_action = (
                c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0],
                c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
            )
        post(port, "add_sale", {
            "date":"2026-01-03","product_id":pid,"qty":"1","unit_price":"20",
            "extra_cost":"0","received":"0","customer":"Wrong token action","notes":"reject",
            "_submission_token":purchase_token,
        }, auto_token=False)
        post(port, "add_expense", {
            "date":"2026-01-03","category":"wrong token action","amount":"10",
            "business":"1","source":"نامشخص","notes":"reject",
            "_submission_token":purchase_token,
        }, auto_token=False)
        with app.conn() as c:
            after_wrong_action = (
                c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM sales").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM expenses").fetchone()[0],
                c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
            )
            assert after_wrong_action == before_wrong_action, (before_wrong_action, after_wrong_action)
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

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
            assert purchase["created_at"] and purchase["updated_at"]
            assert purchase["supplier_person_id"]
            assert c.execute("SELECT name FROM people WHERE id=?", (purchase["supplier_person_id"],)).fetchone()[0] == "Supplier A"
            add_purchase_audit=json.loads(c.execute("SELECT details FROM audit_log WHERE action='add_purchase' ORDER BY id DESC LIMIT 1").fetchone()[0])
            assert str(add_purchase_audit["record_id"])==str(purchase_id), add_purchase_audit

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
            assert purchase["updated_at"]
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
            assert sale["created_at"] and sale["customer_person_id"]
            assert c.execute("SELECT name FROM people WHERE id=?", (sale["customer_person_id"],)).fetchone()[0] == "Customer A"
            add_sale_audit=json.loads(c.execute("SELECT details FROM audit_log WHERE action='add_sale' ORDER BY id DESC LIMIT 1").fetchone()[0])
            assert str(add_sale_audit["record_id"])==str(sale_id), add_sale_audit

        post(port, "update_sale", {
            "record_id":sale_id,"qty":"2","unit_price":"30","extra_cost":"0",
            "received":"40","customer":"Customer A revised","notes":"edited sale"
        })
        # Changing unit conversions after movement history exists must be rejected.
        protected_page=post(port,"update_product",{
            "product_id":pid,"name":"reversal steel","code":"","unit":"kg","stock":"8",
            "avg_cost":"5","market_price":"10","min_stock":"0","notes":"",
            "category":"سایر","purchase_unit":"kg","purchase_factor":"2",
            "sale_unit":"kg","sale_factor":"1","roll_weight":"0","sheet_area":"0"
        })
        assert "reversal steel" in protected_page
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 8 and p["avg_cost"] == 5 and p["purchase_factor"] == 1
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='sales' AND source_id=?", (sale_id,)).fetchone()[0] == 40

        post(port, "delete_sale", {"record_id":sale_id})
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 10 and p["avg_cost"] == 5
            assert c.execute("SELECT COUNT(*) FROM sales WHERE id=?", (sale_id,)).fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='sales' AND source_id=?", (sale_id,)).fetchone()[0] == 0

        post(port, "add_expense", {
            "date":"2026-01-05","category":"test expense","amount":"100.6",
            "business":"1","source":"نامشخص","notes":"initial expense"
        })
        with app.conn() as c:
            expense = c.execute("SELECT * FROM expenses ORDER BY id DESC LIMIT 1").fetchone()
            expense_id = expense["id"]
            add_expense_audit=json.loads(c.execute("SELECT details FROM audit_log WHERE action='add_expense' ORDER BY id DESC LIMIT 1").fetchone()[0])
            assert str(add_expense_audit["record_id"])==str(expense_id), add_expense_audit
        post(port, "update_expense", {
            "record_id":expense_id,"date":"2026-01-06","category":"edited expense","amount":"80.6",
            "business":"0","source":"سرمایه/پس‌انداز","notes":"edited expense"
        })
        with app.conn() as c:
            expense = c.execute("SELECT * FROM expenses WHERE id=?", (expense_id,)).fetchone()
            assert expense["amount"] == 81 and expense["business"] == 0 and expense["date"] == "2026-01-06"
            assert expense["created_at"] and expense["updated_at"]
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='expenses' AND source_id=?", (expense_id,)).fetchone()[0] == 81
        post(port, "delete_expense", {"record_id":expense_id})
        post(port,"add_cash_movement",{
            "date":"2026-01-07","kind":"deposit","to_account_id":"1",
            "party":"Counter sale","note":"audit id test","amount":"200"
        })
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM expenses WHERE id=?", (expense_id,)).fetchone()[0] == 0
            assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='expenses' AND source_id=?", (expense_id,)).fetchone()[0] == 0
            cash_row=c.execute("SELECT id FROM cash_movements WHERE kind='deposit' AND party='Counter sale' ORDER BY id DESC LIMIT 1").fetchone()
            cash_audit=json.loads(c.execute("SELECT details FROM audit_log WHERE action='add_cash_movement' ORDER BY id DESC LIMIT 1").fetchone()[0])
            assert cash_row and str(cash_audit["record_id"])==str(cash_row["id"]), (cash_row,cash_audit)
            audit = c.execute("SELECT * FROM audit_log WHERE action='update_purchase' ORDER BY id DESC LIMIT 1").fetchone()
            assert audit and audit["created_at"]
            details = json.loads(audit["details"])
            assert details["actor"] == "local_user" and str(details["record_id"]) == str(purchase_id)
            assert details["values_stored"] is False and "fields" in details
            audit_html=app.audit_page(c)
            assert "اصلاح خرید" in audit_html and "local_user" in audit_html
            assert "Supplier A revised" not in audit_html
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
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

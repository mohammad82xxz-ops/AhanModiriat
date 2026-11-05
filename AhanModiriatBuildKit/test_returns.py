# -*- coding: utf-8 -*-
"""Regression tests for purchase/sales returns, stock, profit, party balances and cash."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_returns_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def post(port, path, fields, auto_token=True):
    fields = dict(fields)
    protected = {"add_purchase", "add_sale", "add_expense", "add_sales_return", "add_purchase_return"}
    if auto_token and path in protected and "_submission_token" not in fields:
        with app.conn() as c:
            token_markup = app.submission_token(c, path)
            fields["_submission_token"] = token_markup.split('value="', 1)[1].split('"', 1)[0]
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{path}", data=data,
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
                     VALUES('return steel','kg',6,50,200,0,'kg',1,'kg',1)""")
        pid = c.execute("SELECT id FROM products WHERE name='return steel'").fetchone()[0]
        pc = c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                          VALUES('2026-01-01',?,10,50,0,'Seller A',300,'source purchase')""", (pid,))
        purchase_id = pc.lastrowid
        sc = c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                          VALUES('2026-01-02',?,4,200,40,'Customer A',400,'source sale',50)""", (pid,))
        sale_id = sc.lastrowid
        app.ensure_person(c, "Seller A", "supplier")
        app.ensure_person(c, "Customer A", "customer")
        app.sync_cash_posting(c,"purchases",purchase_id,"2026-01-01",300,"out","Seller A","source purchase")
        app.sync_cash_posting(c,"sales",sale_id,"2026-01-02",400,"in","Customer A","source sale")

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        post(port, "add_purchase_return", {
            "purchase_id":purchase_id,"date":"2026-01-03","qty":"1",
            "cash_refund":"3","reason":"damaged goods","notes":"vendor refund"
        })
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 5 and p["avg_cost"] == 50
            ret = c.execute("SELECT * FROM purchase_returns").fetchone()
            assert ret["return_value"] == 50 and ret["cash_refund"] == 30
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='purchase_returns' AND source_id=?", (ret["id"],)).fetchone()[0] == 30
            bal = app.party_balances(c)
            assert bal["Seller A"]["payable"] == 180, bal

        post(port, "add_sales_return", {
            "sale_id":sale_id,"date":"2026-01-04","qty":"1",
            "refund_amount":"15","reason":"customer return","notes":"returned item"
        })
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 6 and abs(p["avg_cost"]-50) < 1e-7
            ret = c.execute("SELECT * FROM sales_returns").fetchone()
            assert ret["return_value"] == 200 and ret["cost_basis"] == 50 and ret["extra_reversed"] == 10
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='sales_returns' AND source_id=?", (ret["id"],)).fetchone()[0] == 150
            bal = app.party_balances(c)
            assert bal["Customer A"]["receivable"] == 350, bal
            assert app.account_balance(c, 1) == -20
            totals = app.calc(c)
            assert totals["sales_rev"] == 600, totals
            assert totals["sales_cost"] == 150, totals
            assert totals["sales_extra"] == 30, totals
            assert totals["net"] == 420, totals
            ledger = app.product_ledger_page(c, pid)
            assert "مرجوعی خرید" in ledger and "مرجوعی فروش" in ledger
            page = app.returns_page(c)
            assert "damaged goods" in page and "customer return" in page

        # A source document with a return must not be edited or deleted out from under it.
        post(port,"delete_sale",{"record_id":sale_id})
        post(port,"delete_purchase",{"record_id":purchase_id})
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM sales WHERE id=?",(sale_id,)).fetchone()[0] == 1
            assert c.execute("SELECT COUNT(*) FROM purchases WHERE id=?",(purchase_id,)).fetchone()[0] == 1
            assert c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0] == 6

        # Cash mirrors must follow edits and disappear when their source documents are deleted.
        # Use fresh source documents without returns so lifecycle guards do not block the operation.
        with app.conn() as c:
            c.execute("UPDATE products SET stock=8,avg_cost=50 WHERE id=?", (pid,))
            pc = c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                              VALUES('2026-02-01',?,2,50,0,'Lifecycle Seller',30,'before edit')""", (pid,))
            lifecycle_purchase_id = pc.lastrowid
            app.sync_cash_posting(c,"purchases",lifecycle_purchase_id,"2026-02-01",30,"out","Lifecycle Seller","before edit")
        post(port,"update_purchase",{
            "record_id":lifecycle_purchase_id,"qty":"3","unit_cost":"60","extra_cost":"0",
            "paid":"45","supplier":"Lifecycle Seller Updated","notes":"after edit"
        })
        with app.conn() as c:
            purchase_posting = c.execute(
                "SELECT date,kind,amount,party,note FROM cash_movements WHERE source_table='purchases' AND source_id=?",
                (lifecycle_purchase_id,),
            ).fetchone()
            assert purchase_posting is not None
            assert (purchase_posting["kind"],purchase_posting["amount"],purchase_posting["party"],purchase_posting["note"]) == (
                "withdraw",450,"Lifecycle Seller Updated","after edit"
            ), dict(purchase_posting)
            assert c.execute("SELECT stock FROM products WHERE id=?",(pid,)).fetchone()[0] == 9
        post(port,"delete_purchase",{"record_id":lifecycle_purchase_id})
        with app.conn() as c:
            assert c.execute("SELECT 1 FROM purchases WHERE id=?",(lifecycle_purchase_id,)).fetchone() is None
            assert c.execute(
                "SELECT 1 FROM cash_movements WHERE source_table='purchases' AND source_id=?",
                (lifecycle_purchase_id,),
            ).fetchone() is None
            assert c.execute("SELECT stock FROM products WHERE id=?",(pid,)).fetchone()[0] == 6

            sc = c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,line_total,extra_cost,customer,received,notes,cost_basis)
                              VALUES('2026-02-02',?,1,100,100,0,'Lifecycle Customer',60,'before edit',50)""", (pid,))
            lifecycle_sale_id = sc.lastrowid
            c.execute("UPDATE products SET stock=stock-1 WHERE id=?",(pid,))
            app.sync_cash_posting(c,"sales",lifecycle_sale_id,"2026-02-02",60,"in","Lifecycle Customer","before edit")
        post(port,"update_sale",{
            "record_id":lifecycle_sale_id,"qty":"2","unit_price":"110","extra_cost":"0",
            "received":"75","customer":"Lifecycle Customer Updated","notes":"after edit"
        })
        with app.conn() as c:
            sale_posting = c.execute(
                "SELECT kind,amount,party,note FROM cash_movements WHERE source_table='sales' AND source_id=?",
                (lifecycle_sale_id,),
            ).fetchone()
            assert sale_posting is not None
            assert (sale_posting["kind"],sale_posting["amount"],sale_posting["party"],sale_posting["note"]) == (
                "deposit",750,"Lifecycle Customer Updated","after edit"
            ), dict(sale_posting)
            assert c.execute("SELECT stock FROM products WHERE id=?",(pid,)).fetchone()[0] == 4
        post(port,"delete_sale",{"record_id":lifecycle_sale_id})
        with app.conn() as c:
            assert c.execute("SELECT 1 FROM sales WHERE id=?",(lifecycle_sale_id,)).fetchone() is None
            assert c.execute(
                "SELECT 1 FROM cash_movements WHERE source_table='sales' AND source_id=?",
                (lifecycle_sale_id,),
            ).fetchone() is None
            assert c.execute("SELECT stock FROM products WHERE id=?",(pid,)).fetchone()[0] == 6

            ec = c.execute("""INSERT INTO expenses(date,category,amount,source,business,notes)
                              VALUES('2026-02-02','Lifecycle expense',70,'Lifecycle source',1,'before edit')""")
            lifecycle_expense_id = ec.lastrowid
            app.sync_cash_posting(c,"expenses",lifecycle_expense_id,"2026-02-02",70,"out","Lifecycle source","before edit")
        post(port,"update_expense",{
            "record_id":lifecycle_expense_id,"date":"2026-02-03","category":"Updated lifecycle expense",
            "amount":"9","source":"Updated lifecycle source","business":"1","notes":"after edit"
        })
        with app.conn() as c:
            expense_posting = c.execute(
                "SELECT date,kind,amount,party,note FROM cash_movements WHERE source_table='expenses' AND source_id=?",
                (lifecycle_expense_id,),
            ).fetchone()
            assert expense_posting is not None
            assert (expense_posting["date"],expense_posting["kind"],expense_posting["amount"],
                    expense_posting["party"],expense_posting["note"]) == (
                "2026-02-03","withdraw",90,"Updated lifecycle source","after edit"
            ), dict(expense_posting)
        post(port,"delete_expense",{"record_id":lifecycle_expense_id})
        with app.conn() as c:
            assert c.execute("SELECT 1 FROM expenses WHERE id=?",(lifecycle_expense_id,)).fetchone() is None
            assert c.execute(
                "SELECT 1 FROM cash_movements WHERE source_table='expenses' AND source_id=?",
                (lifecycle_expense_id,),
            ).fetchone() is None
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

        # The refund cannot exceed the returned sales value.
        post(port, "add_sales_return", {
            "sale_id":sale_id,"date":"2026-01-05","qty":"0.5",
            "refund_amount":"21","reason":"over-refund","notes":"should be rejected"
        })
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0] == 1

        # Enforce the original sale's remaining returnable quantity.
        post(port, "add_sales_return", {
            "sale_id":sale_id,"date":"2026-01-05","qty":"4",
            "refund_amount":"0","reason":"oversized return","notes":"should be rejected"
        })
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0] == 1
            assert c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0] == 6
        # Invalid returns must leave ledgers, stock, and party balances unchanged.
        invalid_return_cases = [
            ("add_sales_return", {"sale_id":sale_id,"date":"2026-01-05","qty":"0","refund_amount":"0","reason":"zero quantity","notes":"reject"}, "sales_returns"),
            ("add_sales_return", {"sale_id":sale_id,"date":"2026-01-05","qty":"0.5","refund_amount":"21","reason":"over-refund","notes":"reject"}, "sales_returns"),
            ("add_sales_return", {"sale_id":sale_id,"date":"2026-01-05","qty":"4","refund_amount":"0","reason":"oversized return","notes":"reject"}, "sales_returns"),
            ("add_purchase_return", {"purchase_id":purchase_id,"date":"2026-01-05","qty":"0","cash_refund":"0","reason":"zero quantity","notes":"reject"}, "purchase_returns"),
            ("add_purchase_return", {"purchase_id":purchase_id,"date":"2026-01-05","qty":"1","cash_refund":"6","reason":"over-refund","notes":"reject"}, "purchase_returns"),
            ("add_purchase_return", {"purchase_id":purchase_id,"date":"2026-01-05","qty":"20","cash_refund":"0","reason":"oversized return","notes":"reject"}, "purchase_returns"),
        ]
        for route, fields, _table in invalid_return_cases:
            with app.conn() as c:
                stock_before = c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0]
                sales_returns_before = c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0]
                purchase_returns_before = c.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0]
                cash_before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table IN ('sales_returns','purchase_returns')").fetchone()[0]
                sales_total_before = app.calc(c)["sales_rev"]
                balances_before = app.party_balances(c)
            post(port, route, fields)
            with app.conn() as c:
                assert c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0] == sales_returns_before, (route, fields)
                assert c.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0] == purchase_returns_before, (route, fields)
                assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table IN ('sales_returns','purchase_returns')").fetchone()[0] == cash_before, (route, fields)
                assert c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0] == stock_before, (route, fields)
                assert app.calc(c)["sales_rev"] == sales_total_before, (route, fields)
                assert app.party_balances(c) == balances_before, (route, fields)
                assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        # A protected return POST without a server-issued token must have no side effects.
        for route, fields in [
            ("add_sales_return", {"sale_id":sale_id,"date":"2026-01-06","qty":"0.25","refund_amount":"1","reason":"missing token","notes":"must reject"}),
            ("add_purchase_return", {"purchase_id":purchase_id,"date":"2026-01-06","qty":"0.25","cash_refund":"1","reason":"missing token","notes":"must reject"}),
        ]:
            with app.conn() as c:
                before = (
                    c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table IN ('sales_returns','purchase_returns')").fetchone()[0],
                    c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
                    app.party_balances(c),
                )
            post(port, route, fields, auto_token=False)
            with app.conn() as c:
                after = (
                    c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table IN ('sales_returns','purchase_returns')").fetchone()[0],
                    c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
                    app.party_balances(c),
                )
                assert after == before, (route, before, after)
                assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        # Replaying a consumed return form token must not create a second financial event.
        for route, fields in [
            ("add_sales_return", {"sale_id":sale_id,"date":"2026-01-06","qty":"0.25","refund_amount":"1","reason":"replay guard","notes":"one-use token"}),
            ("add_purchase_return", {"purchase_id":purchase_id,"date":"2026-01-06","qty":"0.25","cash_refund":"1","reason":"replay guard","notes":"one-use token"}),
        ]:
            with app.conn() as c:
                token_markup = app.submission_token(c, route)
                token = token_markup.split('value="', 1)[1].split('"', 1)[0]
                before = (
                    c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table IN ('sales_returns','purchase_returns')").fetchone()[0],
                    c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
                    app.party_balances(c),
                )
            fields["_submission_token"] = token
            post(port, route, fields)
            with app.conn() as c:
                after_first = (
                    c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table IN ('sales_returns','purchase_returns')").fetchone()[0],
                    c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
                    app.party_balances(c),
                )
            post(port, route, fields)  # replay the same consumed token
            with app.conn() as c:
                after = (
                    c.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0],
                    c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table IN ('sales_returns','purchase_returns')").fetchone()[0],
                    c.execute("SELECT stock FROM products WHERE id=?", (pid,)).fetchone()[0],
                    app.party_balances(c),
                )
                assert after == after_first, (route, after_first, after)
                assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        with app.conn() as c:
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        server.shutdown()
        server.server_close()
    print("PURCHASE AND SALES RETURN TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

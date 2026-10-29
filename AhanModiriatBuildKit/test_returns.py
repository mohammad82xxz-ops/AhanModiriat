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


def post(port, path, fields):
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
                     VALUES('return steel','kg',6,5,20,0,'kg',1,'kg',1)""")
        pid = c.execute("SELECT id FROM products WHERE name='return steel'").fetchone()[0]
        pc = c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                          VALUES('2026-01-01',?,10,5,0,'Seller A',30,'source purchase')""", (pid,))
        purchase_id = pc.lastrowid
        sc = c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                          VALUES('2026-01-02',?,4,20,4,'Customer A',40,'source sale',5)""", (pid,))
        sale_id = sc.lastrowid
        app.ensure_person(c, "Seller A", "supplier")
        app.ensure_person(c, "Customer A", "customer")
        app.sync_cash_posting(c,"purchases",purchase_id,"2026-01-01",30,"out","Seller A","source purchase")
        app.sync_cash_posting(c,"sales",sale_id,"2026-01-02",40,"in","Customer A","source sale")

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
            assert p["stock"] == 5 and p["avg_cost"] == 5
            ret = c.execute("SELECT * FROM purchase_returns").fetchone()
            assert ret["return_value"] == 5 and ret["cash_refund"] == 3
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='purchase_returns' AND source_id=?", (ret["id"],)).fetchone()[0] == 3
            bal = app.party_balances(c)
            assert bal["Seller A"]["payable"] == 18, bal

        post(port, "add_sales_return", {
            "sale_id":sale_id,"date":"2026-01-04","qty":"1",
            "refund_amount":"15","reason":"customer return","notes":"returned item"
        })
        with app.conn() as c:
            p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
            assert p["stock"] == 6 and abs(p["avg_cost"]-5) < 1e-7
            ret = c.execute("SELECT * FROM sales_returns").fetchone()
            assert ret["return_value"] == 20 and ret["cost_basis"] == 5 and ret["extra_reversed"] == 1
            assert c.execute("SELECT amount FROM cash_movements WHERE source_table='sales_returns' AND source_id=?", (ret["id"],)).fetchone()[0] == 15
            bal = app.party_balances(c)
            assert bal["Customer A"]["receivable"] == 35, bal
            assert app.account_balance(c, 1) == -2
            totals = app.calc(c)
            assert totals["sales_rev"] == 60, totals
            assert totals["sales_cost"] == 15, totals
            assert totals["sales_extra"] == 3, totals
            assert totals["net"] == 42, totals
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

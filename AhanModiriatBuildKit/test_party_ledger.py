# -*- coding: utf-8 -*-
"""Regression tests for party balances, statements, settlements, and cash posting."""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_party_ledger_")
os.environ["AHAN_DATA_DIR"] = TMP.name
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def main():
    app.init()
    with app.conn() as c:
        c.execute("INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock) VALUES('steel','kg',0,0,1000,0)")
        pid = c.execute("SELECT id FROM products WHERE name='steel'").fetchone()[0]
        c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                     VALUES('2026-02-01',?,10,1000,0,'Customer A',5000,'partial sale',200)""", (pid,))
        c.execute("""INSERT INTO services(date,title,revenue,cost,received,customer,notes)
                     VALUES('2026-02-02','cutting',2000,500,1000,'Customer A','partial service')""")
        c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                     VALUES('2026-02-03',?,2,1000,0,'Supplier B',500,'partially paid purchase')""", (pid,))
        app.ensure_person(c, "Customer A", "customer")
        app.ensure_person(c, "Supplier B", "supplier")
        sale_ref=c.execute("SELECT customer_person_id FROM sales WHERE customer='Customer A'").fetchone()[0]
        service_ref=c.execute("SELECT customer_person_id FROM services WHERE customer='Customer A'").fetchone()[0]
        purchase_ref=c.execute("SELECT supplier_person_id FROM purchases WHERE supplier='Supplier B'").fetchone()[0]
        assert sale_ref and service_ref and purchase_ref
        assert c.execute("PRAGMA foreign_key_check").fetchall()==[]
        cur = c.execute("INSERT INTO settlements(date,party,kind,amount,notes) VALUES('2026-02-04','Customer A','receive',2500,'customer settlement')")
        app.sync_cash_posting(c, "settlements", cur.lastrowid, "2026-02-04", 2500, "in", "Customer A", "customer settlement")
        cur = c.execute("INSERT INTO settlements(date,party,kind,amount,notes) VALUES('2026-02-05','Supplier B','pay',400,'supplier settlement')")
        app.sync_cash_posting(c, "settlements", cur.lastrowid, "2026-02-05", 400, "out", "Supplier B", "supplier settlement")

        # Simulate upgrading a database where legacy transactions predate the ledger.
        app.backfill_legacy_cash_postings(c)
        balances = app.party_balances(c)
        assert balances["Customer A"]["receivable"] == 3500, balances
        assert balances["Supplier B"]["payable"] == 1100, balances
        assert c.execute("SELECT kind FROM people WHERE name='Customer A'").fetchone()[0] == "customer"
        customer_statement=app.parties_page(c, "Customer A")
        supplier_statement=app.parties_page(c, "Supplier B")
        assert "ریز حساب: Customer A" in customer_statement
        assert "مانده تجمعی دریافتنی" in customer_statement and "مانده تجمعی پرداختنی" in customer_statement
        assert "350" in customer_statement, customer_statement
        assert "110" in supplier_statement, supplier_statement
        assert app.account_balance(c, 1) == 7600, app.account_balance(c, 1)

        # Re-run cash backfill; already linked settlement rows must not be duplicated.
        before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='settlements'").fetchone()[0]
        app.backfill_legacy_cash_postings(c)
        after = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='settlements'").fetchone()[0]
        assert before == after == 2, (before, after)
        assert app.account_balance(c, 1) == 7600
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("PARTY LEDGER TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

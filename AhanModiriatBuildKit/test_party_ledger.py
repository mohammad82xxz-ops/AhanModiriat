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
        c.execute("INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock) VALUES('steel','kg',0,0,100,0)")
        pid = c.execute("SELECT id FROM products WHERE name='steel'").fetchone()[0]
        c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                     VALUES('2026-02-01',?,10,100,0,'Customer A',500,'partial sale',20)""", (pid,))
        c.execute("""INSERT INTO services(date,title,revenue,cost,received,customer,notes)
                     VALUES('2026-02-02','cutting',200,50,100,'Customer A','partial service')""")
        c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                     VALUES('2026-02-03',?,2,100,0,'Supplier B',50,'partially paid purchase')""", (pid,))
        app.ensure_person(c, "Customer A", "customer")
        app.ensure_person(c, "Supplier B", "supplier")
        cur = c.execute("INSERT INTO settlements(date,party,kind,amount,notes) VALUES('2026-02-04','Customer A','receive',250,'customer settlement')")
        app.sync_cash_posting(c, "settlements", cur.lastrowid, "2026-02-04", 250, "in", "Customer A", "customer settlement")
        cur = c.execute("INSERT INTO settlements(date,party,kind,amount,notes) VALUES('2026-02-05','Supplier B','pay',40,'supplier settlement')")
        app.sync_cash_posting(c, "settlements", cur.lastrowid, "2026-02-05", 40, "out", "Supplier B", "supplier settlement")

        balances = app.party_balances(c)
        assert balances["Customer A"]["receivable"] == 350, balances
        assert balances["Supplier B"]["payable"] == 110, balances
        assert c.execute("SELECT kind FROM people WHERE name='Customer A'").fetchone()[0] == "customer"
        assert "ریز حساب: Customer A" in app.parties_page(c, "Customer A")
        assert app.account_balance(c, 1) == 760, app.account_balance(c, 1)

        # Re-run cash backfill; already linked settlement rows must not be duplicated.
        before = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='settlements'").fetchone()[0]
        app.backfill_legacy_cash_postings(c)
        after = c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='settlements'").fetchone()[0]
        assert before == after == 2, (before, after)
        assert app.account_balance(c, 1) == 210
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("PARTY LEDGER TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

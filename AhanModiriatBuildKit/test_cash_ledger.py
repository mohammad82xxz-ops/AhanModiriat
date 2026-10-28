# -*- coding: utf-8 -*-
"""Regression test for idempotent migration into the cash/bank ledger."""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_cash_ledger_")
os.environ["AHAN_DATA_DIR"] = TMP.name
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def main():
    app.init()
    with app.conn() as c:
        c.execute("UPDATE opening_capital SET amount=2000,date='2026-01-01' WHERE id=1")
        c.execute("INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock) VALUES('legacy product','عدد',0,0,100,0)")
        product_id = c.execute("SELECT id FROM products WHERE name='legacy product'").fetchone()[0]
        c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                     VALUES('2026-01-01',?,1,120,0,'legacy supplier',100,'legacy purchase')""", (product_id,))
        c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                     VALUES('2026-01-02',?,1,250,0,'legacy customer',250,'legacy sale',120)""", (product_id,))
        c.execute("""INSERT INTO services(date,title,revenue,cost,received,customer,notes)
                     VALUES('2026-01-03','legacy service',500,100,150,'legacy customer','service receipt')""")
        c.execute("""INSERT INTO expenses(date,category,amount,source,business,notes)
                     VALUES('2026-01-04','legacy expense',75,'legacy vendor',1,'paid expense')""")
        c.execute("INSERT INTO loans(title,principal,remaining,installment) VALUES('legacy loan',1000,1000,50)")
        loan_id = c.execute("SELECT id FROM loans WHERE title='legacy loan'").fetchone()[0]
        c.execute("""INSERT INTO loan_payments(loan_id,date,amount,principal_part,interest_part,source,notes)
                     VALUES(?, '2026-01-05',50,50,0,'legacy bank','loan installment')""", (loan_id,))
        c.execute("""INSERT INTO cash_events(date,kind,amount,source,notes)
                     VALUES('2026-01-06','in',30,'legacy inflow','cash event')""")
        # This pre-existing manual transfer must not block the migration.
        c.execute("""INSERT INTO cash_movements(date,kind,from_account_id,to_account_id,amount,party,note)
                     VALUES('2026-01-09','transfer',1,2,7,'','manual transfer')""")

    app.init()
    with app.conn() as c:
        expected = {
            "purchases": ("withdraw", 100),
            "sales": ("deposit", 250),
            "services": ("deposit", 150),
            "expenses": ("withdraw", 75),
            "loan_payments": ("withdraw", 50),
            "cash_events": ("deposit", 30),
        }
        for table, (kind, amount) in expected.items():
            row = c.execute(
                "SELECT kind,amount FROM cash_movements WHERE source_table=? ORDER BY id LIMIT 1",
                (table,),
            ).fetchone()
            assert row is not None, f"missing migrated source: {table}"
            assert (row["kind"], row["amount"]) == (kind, amount), (table, dict(row))
        # Opening cash 2000 + 250 + 150 + 30 - 100 - 75 - 50 - transfer 7.
        assert app.account_balance(c, 1) == 2198, app.account_balance(c, 1)
        assert app.account_balance(c, 2) == 7, app.account_balance(c, 2)
        assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases'").fetchone()[0] == 1
        assert app.backfill_legacy_cash_postings(c) == 0, "migration must be idempotent"
        assert app.account_balance(c, 1) == 2198
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("SELECT COUNT(*) FROM people WHERE name='legacy supplier'").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM people WHERE name='legacy customer'").fetchone()[0] == 1
    print("CASH LEDGER MIGRATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

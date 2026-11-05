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
        c.execute("UPDATE opening_capital SET amount=20000,date='2026-01-01' WHERE id=1")
        c.execute("INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock) VALUES('legacy product','عدد',0,0,1000,0)")
        product_id = c.execute("SELECT id FROM products WHERE name='legacy product'").fetchone()[0]
        purchase_cur = c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                     VALUES('2026-01-01',?,1,1200,0,'legacy supplier',1000,'legacy purchase')""", (product_id,))
        purchase_id = purchase_cur.lastrowid
        sale_cur = c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                     VALUES('2026-01-02',?,1,2500,0,'legacy customer',2500,'legacy sale',1200)""", (product_id,))
        sale_id = sale_cur.lastrowid
        c.execute("""INSERT INTO purchase_returns(date,purchase_id,product_id,supplier,qty,return_value,cash_refund,reason,notes)
                     VALUES('2026-01-07',?,?, 'legacy supplier',0.1,120,120,'legacy purchase return','explicit vendor refund')""",
                  (purchase_id, product_id))
        c.execute("""INSERT INTO sales_returns(date,sale_id,product_id,customer,qty,return_value,cost_basis,extra_reversed,refund_amount,reason,notes)
                     VALUES('2026-01-08',?,?, 'legacy customer',0.1,250,120,0,250,'legacy sales return','explicit customer refund')""",
                  (sale_id, product_id))
        # Positive return value alone is not evidence of a cash refund.
        zero_purchase_return = c.execute("""INSERT INTO purchase_returns(date,purchase_id,product_id,supplier,qty,return_value,cash_refund,reason,notes)
                     VALUES('2026-01-10',?,?, 'legacy supplier',0.1,80,0,'non-cash purchase return','no cash received')""",
                  (purchase_id, product_id)).lastrowid
        zero_sales_return = c.execute("""INSERT INTO sales_returns(date,sale_id,product_id,customer,qty,return_value,cost_basis,extra_reversed,refund_amount,reason,notes)
                     VALUES('2026-01-11',?,?, 'legacy customer',0.1,90,120,0,0,'non-cash sales return','no cash paid')""",
                  (sale_id, product_id)).lastrowid
        c.execute("""INSERT INTO services(date,title,revenue,cost,received,customer,notes)
                     VALUES('2026-01-03','legacy service',5000,1000,1500,'legacy customer','service receipt')""")
        c.execute("""INSERT INTO expenses(date,category,amount,source,business,notes)
                     VALUES('2026-01-04','legacy expense',750,'legacy vendor',1,'paid expense')""")
        c.execute("INSERT INTO loans(title,principal,remaining,installment) VALUES('legacy loan',10000,10000,500)")
        loan_id = c.execute("SELECT id FROM loans WHERE title='legacy loan'").fetchone()[0]
        c.execute("""INSERT INTO loan_payments(loan_id,date,amount,principal_part,interest_part,source,notes)
                     VALUES(?, '2026-01-05',500,500,0,'legacy bank','loan installment')""", (loan_id,))
        c.execute("""INSERT INTO cash_events(date,kind,amount,source,notes)
                     VALUES('2026-01-06','in',300,'legacy inflow','cash event')""")
        # This pre-existing manual transfer must not block the migration.
        c.execute("""INSERT INTO cash_movements(date,kind,from_account_id,to_account_id,amount,party,note)
                     VALUES('2026-01-09','transfer',1,2,70,'','manual transfer')""")

    app.init()
    with app.conn() as c:
        expected = {
            "purchases": ("withdraw", 1000),
            "sales": ("deposit", 2500),
            "services": ("deposit", 1500),
            "expenses": ("withdraw", 750),
            "loan_payments": ("withdraw", 500),
            "cash_events": ("deposit", 300),
            "purchase_returns": ("deposit", 120),
            "sales_returns": ("withdraw", 250),
        }
        for table, (kind, amount) in expected.items():
            row = c.execute(
                "SELECT kind,amount FROM cash_movements WHERE source_table=? ORDER BY id LIMIT 1",
                (table,),
            ).fetchone()
            assert row is not None, f"missing migrated source: {table}"
            assert (row["kind"], row["amount"]) == (kind, amount), (table, dict(row))
        for table, source_id in (
            ("purchase_returns", zero_purchase_return),
            ("sales_returns", zero_sales_return),
        ):
            assert c.execute(
                "SELECT 1 FROM cash_movements WHERE source_table=? AND source_id=?",
                (table, source_id),
            ).fetchone() is None, f"non-cash return must not create a cash posting: {table} #{source_id}"
        # Explicit return refunds also post: +120 vendor refund and -250 customer refund.
        # Opening cash 20000 + 2500 + 1500 + 300 + 120 - 1000 - 750 - 500 - 250 - transfer 70.
        assert app.account_balance(c, 1) == 21850, app.account_balance(c, 1)
        assert app.account_balance(c, 2) == 70, app.account_balance(c, 2)
        assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='purchases'").fetchone()[0] == 1
        assert app.backfill_legacy_cash_postings(c) == 0, "migration must be idempotent"
        assert app.account_balance(c, 1) == 21850
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("SELECT COUNT(*) FROM people WHERE name='legacy supplier'").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM people WHERE name='legacy customer'").fetchone()[0] == 1
        supplier_ref = c.execute("SELECT supplier_person_id FROM purchases WHERE supplier='legacy supplier'").fetchone()[0]
        customer_ref = c.execute("SELECT customer_person_id FROM sales WHERE customer='legacy customer'").fetchone()[0]
        service_ref = c.execute("SELECT customer_person_id FROM services WHERE customer='legacy customer'").fetchone()[0]
        assert supplier_ref and customer_ref and service_ref
        assert c.execute("SELECT name FROM people WHERE id=?", (supplier_ref,)).fetchone()[0] == "legacy supplier"
        assert c.execute("SELECT name FROM people WHERE id=?", (customer_ref,)).fetchone()[0] == "legacy customer"
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    print("CASH LEDGER MIGRATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

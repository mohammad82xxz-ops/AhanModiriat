# -*- coding: utf-8 -*-
"""Tests the SQL-backed search, total counts and page boundaries."""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_pagination_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def main():
    app.init()
    with app.conn() as c:
        c.execute("INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock) VALUES('pagination seed','kg',100,5,10,0)")
        pid = c.execute("SELECT id FROM products WHERE name='pagination seed'").fetchone()[0]
        purchase_id=c.execute("SELECT id FROM purchases ORDER BY id LIMIT 1").fetchone()[0] if c.execute("SELECT COUNT(*) FROM purchases").fetchone()[0] else None
        for i in range(55):
            c.execute("""INSERT INTO products(name,code,unit,stock,avg_cost,market_price,min_stock,category)
                         VALUES(?,?, 'kg', 1, 5, 10, 0, 'pagination')""", (f"needle product {i:03d}", f"N{i:03d}"))
            pc=c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                         VALUES('2026-01-01',?,1,5,0,'needle supplier',0,'pagination test')""", (pid,))
            purchase_id=pc.lastrowid
            sale=c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                         VALUES('2026-01-02',?,1,10,0,'needle customer',0,'pagination test',5)""", (pid,))
            c.execute("""INSERT INTO services(date,title,revenue,cost,received,customer,notes)
                         VALUES('2026-01-03', 'needle service', 10, 1, 0, 'needle customer', 'pagination test')""")
            c.execute("""INSERT INTO expenses(date,category,amount,source,business,notes)
                         VALUES('2026-01-04','needle expense',1,'needle source',1,'pagination test')""")
            c.execute("""INSERT INTO cash_movements(date,kind,from_account_id,to_account_id,amount,party,note)
                         VALUES('2026-01-05','deposit',NULL,1,1,'needle cash party','needle cash movement')""")
            c.execute("""INSERT INTO inventory_adjustments(date,product_id,expected_qty,counted_qty,delta_qty,reason,notes)
                         VALUES('2026-01-06',?,2,1,-1,'needle count reason','needle inventory note')""",(pid,))
            c.execute("""INSERT INTO purchase_returns(date,purchase_id,product_id,supplier,qty,return_value,cash_refund,reason,notes)
                         VALUES('2026-01-07',?,?,'needle return supplier',0.01,1,0,'needle return reason','pagination test')""",(purchase_id,pid))
            c.execute("INSERT INTO audit_log(action,details) VALUES('needle audit','pagination regression row')")
            c.execute("INSERT INTO people(name,kind,phone,notes) VALUES(?,?,?,?)",(f"needle person {i:03d}","customer",f"09{i:09d}","pagination test"))
            c.execute("INSERT INTO loans(title,principal,remaining,installment,next_date,rate_note,notes,interval_value,interval_unit) VALUES(?,100,90,10,'2026-12-01','needle loan rate','pagination test',1,'month')",(f"needle loan {i:03d}",))
            c.execute("INSERT INTO price_history(date,product_id,market_price,notes) VALUES('2026-01-08',?,10,?)",(pid,f"needle price {i:03d}"))

        checks = [
            ("products", app.products(c, "needle product", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("purchases", app.purchases(c, "needle supplier", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("sales", app.sales(c, "needle customer", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("services", app.services(c, "needle service", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("expenses", app.expenses(c, "needle expense", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("cash", app.cash_page(c, "needle cash", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("inventory", app.inventory_page(c, "needle count", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("returns", app.returns_page(c, "needle return", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("audit", app.audit_page(c, "needle audit", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("parties", app.parties_page(c, "", "needle person", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("loans", app.loans(c, "needle loan", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
            ("prices", app.prices(c, pid, "needle price", 1), "نمایش 50 رکورد از مجموع 55 رکورد"),
        ]
        for name, html, expected in checks:
            assert expected in html, (name, expected)
            assert "صفحه بعدی" in html, name
        second_page = app.products(c, "needle product", 2)
        assert "نمایش 5 رکورد از مجموع 55 رکورد" in second_page
        assert "صفحه 2 از 2" in second_page
        filtered = app.products(c, "needle product 054", 1)
        assert "نمایش 1 رکورد از مجموع 1 رکورد" in filtered
        assert "needle product 054" in filtered
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("SQL SEARCH AND PAGINATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

# -*- coding: utf-8 -*-
"""Profitability report acceptance test across products, customers and Jalali months."""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_profit_reports_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def main():
    app.init()
    with app.conn() as c:
        c.execute("""INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
                     VALUES('profit product','kg',4,40,100,0)""")
        pid = c.execute("SELECT id FROM products WHERE name='profit product'").fetchone()[0]
        c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                     VALUES('2026-05-01',?,10,100,100,'Customer Profit',800,'sale before return',40)""", (pid,))
        sale_id = c.execute("SELECT id FROM sales WHERE product_id=?", (pid,)).fetchone()[0]
        c.execute("""INSERT INTO sales_returns(date,sale_id,product_id,customer,qty,return_value,cost_basis,extra_reversed,refund_amount,reason,notes)
                     VALUES('2026-05-15',?,?,'Customer Profit',2,200,40,20,150,'return','test return')""", (sale_id,pid))
        c.execute("""INSERT INTO services(date,title,revenue,cost,received,customer,notes)
                     VALUES('2026-05-10','service profit',300,50,100,'Customer Profit','service test')""")
        c.execute("""INSERT INTO expenses(date,category,amount,source,business,notes)
                     VALUES('2026-05-12','business expense',80,'cash',1,'expense test')""")
        c.execute("INSERT INTO loans(title,principal,remaining,installment) VALUES('report loan',100,100,10)")
        loan_id = c.execute("SELECT id FROM loans WHERE title='report loan'").fetchone()[0]
        c.execute("""INSERT INTO loan_payments(loan_id,date,amount,principal_part,interest_part,source,notes)
                     VALUES(?,'2026-05-13',10,0,10,'cash','interest test')""", (loan_id,))
        html = app.report_detail_sections(c)
        assert "profit product" in html
        assert "Customer Profit" in html
        assert "سود خالص ماهانه (تقویم شمسی)" in html
        # Sale 1000 revenue, 400 cost, 100 direct expense; return 200 / 80 / 20.
        assert "800" in html and "320" in html and "80" in html and "400" in html
        # Customer profitability includes service profit: 400 + (300 - 50) = 650.
        assert "650" in html and "250" in html and "300" in html
        jy,jm,_ = app.gregorian_to_jalali(2026,5,15)
        assert f"{jy:04d}/{jm:02d}" in html
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("PROFIT REPORT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

# -*- coding: utf-8 -*-
"""UI-boundary tests: integer rial storage must be presented and edited in toman."""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_money_units_ui_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def main():
    app.init()
    with app.conn() as c:
        pid = c.execute(
            """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock,
                       purchase_unit,purchase_factor,sale_unit,sale_factor)
               VALUES('rial ui product','kg',10,1234,5678,0,'kg',1,'kg',1)"""
        ).lastrowid
        purchase_id = c.execute(
            """INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
               VALUES('2026-01-01',?,2,2345,678,'vendor',1900,'purchase ui')""",
            (pid,),
        ).lastrowid
        sale_id = c.execute(
            """INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
               VALUES('2026-01-02',?,1,3456,789,'customer',2500,'sale ui',1234)""",
            (pid,),
        ).lastrowid
        expense_id = c.execute(
            """INSERT INTO expenses(date,category,amount,source,business,notes)
               VALUES('2026-01-03','expense ui',4567,'cash',1,'expense')"""
        ).lastrowid

        product_html = app.product_editor(c, pid)
        purchase_html = app.purchase_editor(c, purchase_id)
        sale_html = app.sale_editor(c, sale_id)
        expense_html = app.expense_editor(c, expense_id)

        assert 'name="avg_cost" type="text" value="123.4"' in product_html
        assert 'name="market_price" type="text" value="567.8"' in product_html
        assert 'name="unit_cost" type="text" value="234.5"' in purchase_html
        assert 'name="extra_cost" type="text" value="67.8"' in purchase_html
        assert 'name="paid" type="text" value="190"' in purchase_html
        assert 'name="unit_price" type="text" value="345.6"' in sale_html
        assert 'name="extra_cost" type="text" value="78.9"' in sale_html
        assert 'name="received" type="text" value="250"' in sale_html
        assert 'name="amount" type="text" value="456.7"' in expense_html

        assert app.money(1234) == "123.4"
        assert app.money_input(4567) == "456.7"
        amount_field = app.field("مبلغ", "amount", "number", "123.4", True, "0.01")
        assert 'step="0.1"' in amount_field
        assert 'data-unit="تومان"' in amount_field
        assert app.strict_money_int("123.4", "test amount") == 1234
        assert app.strict_money_int("0.05", "half rial") == 1
        # Each document line is rounded independently in integer rial, half-up.
        assert app.money_line_total("0.0005", "1000") == 1
        assert app.money_line_total("0.0004", "1000") == 0
        assert app.money_line_total("1.234", "1000") == 1234
        assert app.money_line_total("0.0005", "1000") + app.money_line_total("0.0005", "1000") == 2
        assert app.money_average(1000, 15) == 67
        assert c.execute("SELECT money_line_total(0.0005,1000)").fetchone()[0] == 1
        before = app.calc(c)
        c.execute(
            """INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
               VALUES('2026-01-04',?,0.0005,1000,0,'fractional line customer',0,'rounding test',0)""",
            (pid,),
        )
        c.execute(
            """INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
               VALUES('2026-01-05',?,0.0005,1000,0,'fractional line supplier',0,'rounding test')""",
            (pid,),
        )
        after = app.calc(c)
        assert after["sales_rev"] - before["sales_rev"] == 1
        balances = app.party_balances(c)
        assert balances["fractional line customer"]["receivable"] == 1
        assert balances["fractional line supplier"]["payable"] == 1
        try:
            app.money_line_total("NaN", "1000")
        except ValueError:
            pass
        else:
            raise AssertionError("non-finite line amount was accepted")
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("MONEY UNIT UI TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

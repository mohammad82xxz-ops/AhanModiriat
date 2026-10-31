# -*- coding: utf-8 -*-
"""Test rial migration: integer transaction totals and precise per-unit rates."""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_money_schema_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def create_legacy_db(path):
    c=sqlite3.connect(path)
    c.row_factory=sqlite3.Row
    c.execute("PRAGMA foreign_keys=OFF")
    c.executescript("""
    CREATE TABLE products(
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, unit TEXT NOT NULL DEFAULT 'kg',
        stock REAL NOT NULL DEFAULT 0, avg_cost REAL NOT NULL DEFAULT 0,
        market_price REAL NOT NULL DEFAULT 0, min_stock REAL NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX ix_products_name ON products(name);
    CREATE TABLE purchases(
        id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id),
        qty REAL NOT NULL, unit_cost REAL NOT NULL, extra_cost REAL NOT NULL DEFAULT 0,
        supplier TEXT NOT NULL DEFAULT '', paid REAL NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX ix_purchases_product_date ON purchases(product_id,date,id);
    CREATE TABLE sales(
        id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL REFERENCES products(id),
        qty REAL NOT NULL, unit_price REAL NOT NULL, extra_cost REAL NOT NULL DEFAULT 0,
        customer TEXT NOT NULL DEFAULT '', received REAL NOT NULL DEFAULT 0,
        notes TEXT NOT NULL DEFAULT '', cost_basis REAL NOT NULL DEFAULT 0
    );
    CREATE INDEX ix_sales_product_date ON sales(product_id,date,id);
    CREATE TABLE expenses(
        id INTEGER PRIMARY KEY, date TEXT NOT NULL, category TEXT NOT NULL,
        amount REAL NOT NULL, source TEXT NOT NULL DEFAULT '', business INTEGER NOT NULL DEFAULT 1,
        notes TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE audit_log(
        id INTEGER PRIMARY KEY, created_at TEXT NOT NULL DEFAULT '', action TEXT NOT NULL,
        details TEXT NOT NULL DEFAULT ''
    );
    CREATE TABLE purchase_returns(
        id INTEGER PRIMARY KEY, purchase_id INTEGER REFERENCES purchases(id),
        product_id INTEGER REFERENCES products(id), return_value REAL NOT NULL,
        cash_refund INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE sales_returns(
        id INTEGER PRIMARY KEY, sale_id INTEGER REFERENCES sales(id),
        product_id INTEGER REFERENCES products(id), return_value REAL NOT NULL,
        cost_basis REAL NOT NULL, extra_reversed REAL NOT NULL DEFAULT 0,
        refund_amount INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE cash_accounts(id INTEGER PRIMARY KEY, opening_balance INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE cash_movements(id INTEGER PRIMARY KEY, amount INTEGER NOT NULL);
    CREATE TABLE services(id INTEGER PRIMARY KEY, revenue REAL NOT NULL, cost REAL NOT NULL, received REAL NOT NULL);
    CREATE TABLE loans(id INTEGER PRIMARY KEY, principal REAL NOT NULL, remaining REAL NOT NULL, installment REAL NOT NULL);
    CREATE TABLE loan_payments(id INTEGER PRIMARY KEY, amount REAL NOT NULL, principal_part REAL NOT NULL, interest_part REAL NOT NULL);
    CREATE TABLE cash_events(id INTEGER PRIMARY KEY, amount REAL NOT NULL);
    CREATE TABLE price_history(id INTEGER PRIMARY KEY, market_price REAL NOT NULL);
    CREATE TABLE opening_capital(id INTEGER PRIMARY KEY CHECK(id=1), amount REAL NOT NULL);
    CREATE TABLE settlements(id INTEGER PRIMARY KEY, amount REAL NOT NULL);
    CREATE TRIGGER trg_products_test_insert AFTER INSERT ON products
    BEGIN UPDATE products SET notes='trigger-preserved' WHERE id=NEW.id; END;
    """)
    c.execute("INSERT INTO products(id,name,unit,stock,avg_cost,market_price,min_stock,notes) VALUES(1,'Legacy','kg',3.5,12.7,18.6,0,'seed')")
    c.execute("INSERT INTO purchases(id,date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes) VALUES(4,'2026-01-01',1,2,100.6,4.6,'Vendor',50.5,'purchase')")
    c.execute("INSERT INTO sales(id,date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis) VALUES(8,'2026-01-02',1,1,200.5,5.5,'Customer',80.6,'sale',100.8)")
    c.execute("INSERT INTO expenses(id,date,category,amount,source,business,notes) VALUES(9,'2026-01-03','fee',1.6,'cash',1,'expense')")
    c.execute("INSERT INTO purchase_returns(id,return_value,cash_refund) VALUES(10,3.4,2)")
    c.execute("INSERT INTO sales_returns(id,return_value,cost_basis,extra_reversed,refund_amount) VALUES(11,5.4,2.2,0.6,4)")
    c.execute("INSERT INTO cash_accounts(id,opening_balance) VALUES(1,7)")
    c.execute("INSERT INTO cash_movements(id,amount) VALUES(1,8)")
    c.execute("INSERT INTO services(id,revenue,cost,received) VALUES(1,1.1,2.2,3.3)")
    c.execute("INSERT INTO loans(id,principal,remaining,installment) VALUES(1,4.4,3.3,1.1)")
    c.execute("INSERT INTO loan_payments(id,amount,principal_part,interest_part) VALUES(1,4.4,3.3,1.1)")
    c.execute("INSERT INTO cash_events(id,amount) VALUES(1,2.5)")
    c.execute("INSERT INTO price_history(id,market_price) VALUES(1,7.7)")
    c.execute("INSERT INTO opening_capital(id,amount) VALUES(1,9.9)")
    c.execute("INSERT INTO settlements(id,amount) VALUES(1,8.8)")
    c.commit()
    # Exercise the same FK-enforced connection mode used by the application.
    c.execute("PRAGMA foreign_keys=ON")
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    return c


def test_large_rial_precision():
    """Large integer rials must not round when legacy REAL columns are rebuilt."""
    path = Path(TMP.name) / "large_rial_precision.db"
    c = create_legacy_db(path)
    try:
        # This source REAL is exactly representable as binary64. Multiplying by ten
        # yields an odd integer above 2**53, which binary64 cannot represent.
        c.execute("UPDATE products SET avg_cost=? WHERE id=1", (900719925474099.5,))
        c.commit()
        c.execute("PRAGMA foreign_keys=OFF")
        app.migrate_money_units_to_rial(c)
        app.migrate_money_columns_to_integer(c)
        actual = c.execute("SELECT avg_cost,typeof(avg_cost) FROM products WHERE id=1").fetchone()
        assert actual[0] == 9007199254740995, actual[0]
        assert actual[1] == "integer", actual[1]
        assert c.execute("SELECT 1 FROM sqlite_temp_master WHERE name='__rial_exact_values'").fetchone() is None
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        c.commit()
    finally:
        c.close()


def main():
    app.init()
    test_large_rial_precision()
    legacy_path=Path(TMP.name)/"legacy.db"
    c=create_legacy_db(legacy_path)
    try:
        # Match init(): disable FK enforcement only for the table rebuild, then
        # re-enable it after commit and verify every relationship still resolves.
        c.execute("PRAGMA foreign_keys=OFF")
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        scaled_rows=app.migrate_money_units_to_rial(c)
        assert scaled_rows==15, scaled_rows
        converted=app.migrate_money_columns_to_integer(c)
        assert converted==27, converted
        assert c.execute("PRAGMA foreign_key_check").fetchall()==[]
        assert c.execute("PRAGMA legacy_alter_table").fetchone()[0] == 0
        c.commit()
        c.execute("PRAGMA foreign_keys=ON")

        expected={
            "products":{"avg_cost":127,"market_price":186},
            "purchases":{"unit_cost":1006,"extra_cost":46,"paid":505},
            "sales":{"unit_price":2005,"extra_cost":55,"received":806,"cost_basis":1008},
            "expenses":{"amount":16},
        }
        for table,columns in expected.items():
            schema={r["name"]:r["type"].upper() for r in c.execute(f'PRAGMA table_info("{table}")')}
            for col,value in columns.items():
                assert schema[col]=="INTEGER",(table,col,schema[col])
                actual=c.execute(f'SELECT "{col}",typeof("{col}") FROM "{table}" LIMIT 1').fetchone()
                assert actual[0]==value,(table,col,actual[0],value)
                assert actual[1]=="integer",(table,col,actual[1])
        additional_expected = {
            "purchase_returns": {"return_value":34,"cash_refund":20},
            "sales_returns": {"return_value":54,"cost_basis":22,"extra_reversed":6,"refund_amount":40},
            "cash_accounts": {"opening_balance":70},
            "cash_movements": {"amount":80},
            "services": {"revenue":11,"cost":22,"received":33},
            "loans": {"principal":44,"remaining":33,"installment":11},
            "loan_payments": {"amount":44,"principal_part":33,"interest_part":11},
            "cash_events": {"amount":25},
            "price_history": {"market_price":77},
            "opening_capital": {"amount":99},
            "settlements": {"amount":88},
        }
        for table, columns in additional_expected.items():
            schema={r["name"]:r["type"].upper() for r in c.execute(f'PRAGMA table_info("{table}")')}
            for column, value in columns.items():
                assert schema[column]=="INTEGER",(table,column,schema[column])
                actual=c.execute(f'SELECT "{column}",typeof("{column}") FROM "{table}" LIMIT 1').fetchone()
                assert actual[0]==value,(table,column,actual[0],value)
                assert actual[1]=="integer",(table,column,actual[1])
        for table, columns in app.MONEY_INTEGER_COLUMNS.items():
            schema={r["name"]:r["type"].upper() for r in c.execute(f'PRAGMA table_info("{table}")')}
            for column in columns:
                if column in schema:  # New additive columns are verified against init() below.
                    assert schema[column]=="INTEGER",(table,column,schema[column])
        assert app.migrate_money_units_to_rial(c)==0,"rial unit migration must be idempotent"
        assert app.money(1234)=="123.4"
        assert app.money_input(1234)=="123.4"
        assert app.strict_money_int("123.4","money test")==1234
        assert app.strict_money_int("0.05","half rial test")==1
        # Non-money quantity columns keep their decimal type.
        product_schema={r["name"]:r["type"].upper() for r in c.execute("PRAGMA table_info(products)")}
        assert product_schema["stock"]=="REAL"
        assert c.execute("SELECT stock FROM products WHERE id=1").fetchone()[0]==3.5
        # Explicit indexes and triggers survive the rebuild.
        indexes={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")}
        triggers={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        assert "ix_products_name" in indexes and "ix_purchases_product_date" in indexes and "ix_sales_product_date" in indexes
        assert "trg_products_test_insert" in triggers
        c.execute("INSERT INTO products(id,name,unit,stock,avg_cost,market_price,min_stock) VALUES(2,'triggered','kg',0,1,2,0)")
        assert c.execute("SELECT notes FROM products WHERE id=2").fetchone()[0]=="trigger-preserved"
        assert c.execute("SELECT COUNT(*) FROM purchases WHERE id=4").fetchone()[0]==1
        assert c.execute("SELECT COUNT(*) FROM sales WHERE id=8").fetchone()[0]==1
        assert c.execute("PRAGMA foreign_key_check").fetchall()==[]
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        purchase_fk={r["table"] for r in c.execute("PRAGMA foreign_key_list(purchase_returns)")}
        sales_fk={r["table"] for r in c.execute("PRAGMA foreign_key_list(sales_returns)")}
        assert "purchases" in purchase_fk and "products" in purchase_fk, purchase_fk
        assert "sales" in sales_fk and "products" in sales_fk, sales_fk
        assert app.migrate_money_columns_to_integer(c)==0,"money migration must be idempotent"
        assert c.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
    finally:
        c.close()
    # The normal app schema also needs to start with the converted money column declarations.
    with app.conn() as live:
        for table,columns in app.MONEY_INTEGER_COLUMNS.items():
            info={r["name"]:r["type"].upper() for r in live.execute(f'PRAGMA table_info("{table}")')}
            for col in columns:
                if col in info:
                    assert info[col]=="INTEGER",(table,col,info[col])
        live_sales_schema={r["name"]:r["type"].upper() for r in live.execute("PRAGMA table_info(sales)")}
        assert live_sales_schema.get("line_total")=="INTEGER",live_sales_schema
        assert live.execute("PRAGMA foreign_key_check").fetchall()==[]
    # A bad value late in the scale pass must roll back every earlier row update
    # and must not leave the database marked as migrated.
    rollback_cases = (
        ("settlements", "amount", "NaN", "غیرمتناهی"),
        ("products", "avg_cost", "9000000000000000000", "ظرفیت عدد صحیح ریال"),
        ("products", "avg_cost", "9000000000000000000000000000000", "ظرفیت عدد صحیح ریال"),
    )
    for index, (table, column, bad_value, message_fragment) in enumerate(rollback_cases, start=1):
        rollback_db = create_legacy_db(Path(TMP.name) / f"rollback_{index}.db")
        try:
            rollback_db.execute(f'UPDATE "{table}" SET "{column}"=? WHERE id=1', (bad_value,))
            rollback_db.commit()
            rollback_db.execute("PRAGMA foreign_keys=OFF")
            try:
                with rollback_db:
                    app.migrate_money_units_to_rial(rollback_db)
            except RuntimeError as exc:
                assert message_fragment in str(exc), str(exc)
            else:
                raise AssertionError(f"invalid legacy value was accepted: {table}.{column}={bad_value}")
            expected_avg_cost = float(bad_value) if table == "products" and column == "avg_cost" else 12.7
            assert rollback_db.execute("SELECT avg_cost FROM products WHERE id=1").fetchone()[0] == expected_avg_cost
            assert rollback_db.execute("SELECT unit_cost FROM purchases WHERE id=4").fetchone()[0] == 100.6
            assert rollback_db.execute(
                "SELECT value FROM settings WHERE key=?", (app.RIAL_UNIT_SETTING,)
            ).fetchone() is None
        finally:
            rollback_db.close()
    print("INTEGER RIAL SCHEMA MIGRATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

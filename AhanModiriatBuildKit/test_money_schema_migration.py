# -*- coding: utf-8 -*-
"""Test rebuild of legacy REAL monetary columns into INTEGER without losing schema/data."""
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
        id INTEGER PRIMARY KEY, return_value REAL NOT NULL, cash_refund INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE sales_returns(
        id INTEGER PRIMARY KEY, return_value REAL NOT NULL, cost_basis REAL NOT NULL,
        extra_reversed REAL NOT NULL DEFAULT 0, refund_amount INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE cash_accounts(id INTEGER PRIMARY KEY, opening_balance INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE cash_movements(id INTEGER PRIMARY KEY, amount INTEGER NOT NULL);
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
    c.commit()
    return c


def main():
    app.init()
    legacy_path=Path(TMP.name)/"legacy.db"
    c=create_legacy_db(legacy_path)
    try:
        converted=app.migrate_money_columns_to_integer(c)
        assert converted==14, converted
        scaled_rows=app.migrate_money_units_to_rial(c)
        assert scaled_rows==8, scaled_rows
        c.commit()

        expected={
            "products":{"avg_cost":130,"market_price":190},
            "purchases":{"unit_cost":1010,"extra_cost":50,"paid":510},
            "sales":{"unit_price":2010,"extra_cost":60,"received":810,"cost_basis":1010},
            "expenses":{"amount":20},
        }
        for table,columns in expected.items():
            schema={r["name"]:r["type"].upper() for r in c.execute(f'PRAGMA table_info("{table}")')}
            for col,value in columns.items():
                assert schema[col]=="INTEGER",(table,col,schema[col])
                actual=c.execute(f'SELECT "{col}",typeof("{col}") FROM "{table}" LIMIT 1').fetchone()
                assert actual[0]==value,(table,col,actual[0],value)
                assert actual[1]=="integer",(table,col,actual[1])
        additional_expected = {
            "purchase_returns": {"return_value":30,"cash_refund":20},
            "sales_returns": {"return_value":50,"cost_basis":20,"extra_reversed":10,"refund_amount":40},
            "cash_accounts": {"opening_balance":70},
            "cash_movements": {"amount":80},
        }
        for table, columns in additional_expected.items():
            for column, value in columns.items():
                actual=c.execute(f'SELECT "{column}" FROM "{table}" LIMIT 1').fetchone()[0]
                assert actual==value,(table,column,actual,value)
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
        assert live.execute("PRAGMA foreign_key_check").fetchall()==[]
    print("INTEGER RIAL SCHEMA MIGRATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

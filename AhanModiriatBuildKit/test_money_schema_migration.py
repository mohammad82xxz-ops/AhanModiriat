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
    CREATE TRIGGER trg_products_test_insert AFTER INSERT ON products
    BEGIN UPDATE products SET notes='trigger-preserved' WHERE id=NEW.id; END;
    """)
    c.execute("INSERT INTO products(id,name,unit,stock,avg_cost,market_price,min_stock,notes) VALUES(1,'Legacy','kg',3.5,12.7,18.6,0,'seed')")
    c.execute("INSERT INTO purchases(id,date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes) VALUES(4,'2026-01-01',1,2,100.6,4.6,'Vendor',50.5,'purchase')")
    c.execute("INSERT INTO sales(id,date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis) VALUES(8,'2026-01-02',1,1,200.5,5.5,'Customer',80.6,'sale',100.8)")
    c.execute("INSERT INTO expenses(id,date,category,amount,source,business,notes) VALUES(9,'2026-01-03','fee',1.6,'cash',1,'expense')")
    c.commit()
    return c


def main():
    app.init()
    legacy_path=Path(TMP.name)/"legacy.db"
    c=create_legacy_db(legacy_path)
    try:
        converted=app.migrate_money_columns_to_integer(c)
        assert converted==10, converted
        c.commit()

        expected={
            "products":{"avg_cost":13,"market_price":19},
            "purchases":{"unit_cost":101,"extra_cost":5,"paid":51},
            "sales":{"unit_price":201,"extra_cost":6,"received":81,"cost_basis":101},
            "expenses":{"amount":2},
        }
        for table,columns in expected.items():
            schema={r["name"]:r["type"].upper() for r in c.execute(f'PRAGMA table_info("{table}")')}
            for col,value in columns.items():
                assert schema[col]=="INTEGER",(table,col,schema[col])
                actual=c.execute(f'SELECT "{col}",typeof("{col}") FROM "{table}" LIMIT 1').fetchone()
                assert actual[0]==value,(table,col,actual[0],value)
                assert actual[1]=="integer",(table,col,actual[1])
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
    print("INTEGER TOMAN SCHEMA MIGRATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

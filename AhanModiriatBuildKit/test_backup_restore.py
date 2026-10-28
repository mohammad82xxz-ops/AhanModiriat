# -*- coding: utf-8 -*-
"""Tests that backup restore validates, preserves a pre-restore snapshot and migrates."""
import os
import sqlite3
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_restore_test_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def make_backup(path, product_name):
    with sqlite3.connect(path) as c:
        c.executescript("""
        CREATE TABLE products(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT DEFAULT '',
            unit TEXT NOT NULL DEFAULT 'kg', stock REAL NOT NULL DEFAULT 0,
            avg_cost REAL NOT NULL DEFAULT 0, market_price REAL NOT NULL DEFAULT 0,
            min_stock REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT ''
        );
        CREATE TABLE purchases(
            id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL,
            qty REAL NOT NULL, unit_cost REAL NOT NULL, extra_cost REAL NOT NULL DEFAULT 0,
            supplier TEXT DEFAULT '', paid REAL NOT NULL DEFAULT 0, notes TEXT DEFAULT ''
        );
        CREATE TABLE sales(
            id INTEGER PRIMARY KEY, date TEXT NOT NULL, product_id INTEGER NOT NULL,
            qty REAL NOT NULL, unit_price REAL NOT NULL, extra_cost REAL NOT NULL DEFAULT 0,
            customer TEXT DEFAULT '', received REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '', cost_basis REAL NOT NULL DEFAULT 0
        );
        """)
        c.execute("INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock) VALUES(?, 'kg', 2, 10, 15, 0)", (product_name,))


def main():
    app.init()
    with app.conn() as c:
        c.execute("INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock) VALUES('current only','kg',1,5,7,0)")
    # The HTTP backup endpoint must use SQLite's backup API so uncheckpointed WAL data is included.
    server = app.ThreadingHTTPServer(("127.0.0.1",0),app.Handler)
    port=server.server_address[1]
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        request=urllib.request.Request(f"http://127.0.0.1:{port}/backup",headers={"Host":f"127.0.0.1:{port}"})
        with urllib.request.urlopen(request,timeout=10) as response:
            assert response.status==200
            assert "application/octet-stream" in response.headers.get("Content-Type","")
            downloaded=response.read()
        download_path=Path(TMP.name)/"downloaded-backup.db"
        download_path.write_bytes(downloaded)
        with sqlite3.connect(download_path) as backup_db:
            assert backup_db.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
            names={row[0] for row in backup_db.execute("SELECT name FROM products")}
            assert "current only" in names,names
    finally:
        server.shutdown()
        server.server_close()
    base = Path(TMP.name)
    candidate = base / "valid-backup.db"
    make_backup(candidate, "restored product")
    app.restore_database_from_file(candidate)
    with app.conn() as c:
        names = {r[0] for r in c.execute("SELECT name FROM products")}
        assert "restored product" in names, names
        assert "current only" not in names, names
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("SELECT COUNT(*) FROM cash_accounts").fetchone()[0] == 2
    backups = list((app.DATA / "backups").glob("business_*.db"))
    assert len(backups) >= 2, len(backups)

    # An invalid/non-database file must be rejected before the live database is touched.
    invalid = base / "invalid.db"
    invalid.write_bytes(b"not a sqlite database")
    rejected = False
    try:
        app.restore_database_from_file(invalid)
    except ValueError:
        rejected = True
    assert rejected, "invalid backup was accepted"
    with app.conn() as c:
        names = {r[0] for r in c.execute("SELECT name FROM products")}
        assert names == {"restored product"}, names
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("BACKUP RESTORE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

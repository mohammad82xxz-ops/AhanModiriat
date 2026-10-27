# -*- coding: utf-8 -*-
"""Isolated smoke tests for the GitHub branch app; never uses the user's database."""
import os, sys, tempfile
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="ahan_github_smoke_")
os.environ["AHAN_DATA_DIR"] = _TMP.name
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app

def main():
    app.init()
    with app.conn() as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        tables = {r["name"] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for name in ("products", "purchases", "sales", "expenses", "audit_log"):
            assert name in tables, name
        for html in (app.dash(c), app.products(c), app.purchases(c), app.sales(c),
                     app.services(c), app.expenses(c), app.loans(c), app.prices(c),
                     app.reports(c), app.settings(c), app.design_page(c)):
            assert "<html" in html and "</html>" in html
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("GitHub branch smoke tests passed.")
    _TMP.cleanup()

if __name__ == "__main__":
    main()

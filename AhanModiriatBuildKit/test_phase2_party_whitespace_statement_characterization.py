# -*- coding: utf-8 -*-
"""Characterize whitespace normalization differences between party balances and statements."""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_party_whitespace_statement_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def main():
    app.init()
    with app.conn() as c:
        c.execute(
            """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
               VALUES('whitespace-test-steel','kg',0,0,1000,0)"""
        )
        product_id = c.execute(
            "SELECT id FROM products WHERE name='whitespace-test-steel'"
        ).fetchone()[0]
        c.execute(
            """INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
               VALUES('2026-02-01',?,1,1000,0,'Alpha  Beta',0,'legacy double-space name',100)""",
            (product_id,),
        )
        c.execute(
            """INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
               VALUES('2026-02-02',?,1,2000,0,'Alpha Beta',0,'single-space name',100)""",
            (product_id,),
        )
        app.ensure_person(c, "Alpha Beta", "customer")

        # The balance aggregator collapses internal whitespace and combines both legacy names.
        balances = app.party_balances(c)
        assert balances["Alpha Beta"]["receivable"] == 3000, balances

        # The detail statement currently filters with TRIM(), which does not collapse
        # internal whitespace. Preserve this observed behavior as characterization only.
        statement_html = app.parties_page(c, "Alpha Beta")
        assert statement_html.count("فروش کالا") == 1, statement_html
        assert "ریز حساب: Alpha Beta" in statement_html

        # Confirm that both source rows still exist; this test must not rewrite legacy text.
        rows = c.execute(
            "SELECT customer FROM sales ORDER BY date,id"
        ).fetchall()
        assert [row["customer"] for row in rows] == ["Alpha  Beta", "Alpha Beta"]
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    print("PARTY WHITESPACE STATEMENT CHARACTERIZATION PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

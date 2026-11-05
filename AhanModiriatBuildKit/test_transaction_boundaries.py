# -*- coding: utf-8 -*-
"""Characterization tests for settlement atomicity and legacy party-name spacing."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from unittest.mock import patch

TMP = tempfile.TemporaryDirectory(prefix="ahan_transaction_boundary_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def _post(port, path, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{path}",
        data=data,
        headers={
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.read().decode("utf-8")


def test_legacy_internal_spacing_mismatch(c):
    """Expose current summary-vs-statement mismatch without blessing it as desired behavior."""
    c.execute(
        """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
           VALUES('spacing-test-steel','kg',0,0,500,0)"""
    )
    product_id = c.execute(
        "SELECT id FROM products WHERE name='spacing-test-steel'"
    ).fetchone()[0]
    c.execute(
        """INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,
                            received,notes,cost_basis)
           VALUES('2026-02-01',?,2,500,0,'Acme  Steel',0,
                  'legacy-spacing-marker',100)""",
        (product_id,),
    )
    app.ensure_person(c, "Acme Steel", "customer")

    balances = app.party_balances(c)
    assert balances["Acme Steel"]["receivable"] == 1000, balances

    # The statement query currently compares TRIM(text) with the canonical
    # selected name; TRIM does not collapse the doubled internal whitespace.
    statement_rows = c.execute(
        "SELECT id FROM sales WHERE TRIM(customer)=?",
        ("Acme Steel",),
    ).fetchall()
    assert statement_rows == [], statement_rows

    statement_html = app.parties_page(c, selected="Acme Steel")
    assert "ریز حساب: Acme Steel" in statement_html
    assert "legacy-spacing-marker" not in statement_html

    # This is a known mismatch characterization, not an assertion that the
    # missing statement row is acceptable product behavior.


def test_settlement_sync_failure_rolls_back_everything():
    app.init()
    with app.conn() as c:
        token_markup = app.submission_token(c, "add_settlement")
        token = token_markup.split('value="', 1)[1].split('"', 1)[0]
        before = {
            "people": c.execute("SELECT COUNT(*) FROM people").fetchone()[0],
            "settlements": c.execute("SELECT COUNT(*) FROM settlements").fetchone()[0],
            "cash": c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
            "audit": c.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action='add_settlement'"
            ).fetchone()[0],
        }

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original_sync = app.sync_cash_posting

    def fail_settlement_sync(c, source_table, *args, **kwargs):
        if source_table == "settlements":
            raise RuntimeError("injected settlement cash-sync failure")
        return original_sync(c, source_table, *args, **kwargs)

    try:
        with patch.object(app, "sync_cash_posting", side_effect=fail_settlement_sync):
            _post(port, "add_settlement", {
                "party": "Atomicity Test Party",
                "kind": "receive",
                "date": "2026-02-02",
                "amount": "1250",
                "notes": "fault-injection",
                "_submission_token": token,
            })

        with app.conn() as c:
            after = {
                "people": c.execute("SELECT COUNT(*) FROM people").fetchone()[0],
                "settlements": c.execute("SELECT COUNT(*) FROM settlements").fetchone()[0],
                "cash": c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
                "audit": c.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE action='add_settlement'"
                ).fetchone()[0],
            }
            token_row = c.execute(
                "SELECT consumed_at FROM form_submission_tokens WHERE token=?",
                (token,),
            ).fetchone()
            assert after == before, (before, after)
            assert token_row is not None and token_row["consumed_at"] is None, token_row
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

        # With the injected failure removed, a fresh token/request must succeed.
        with app.conn() as c:
            fresh_markup = app.submission_token(c, "add_settlement")
            fresh_token = fresh_markup.split('value="', 1)[1].split('"', 1)[0]
        _post(port, "add_settlement", {
            "party": "Atomicity Test Party",
            "kind": "receive",
            "date": "2026-02-02",
            "amount": "1250",
            "notes": "positive-control",
            "_submission_token": fresh_token,
        })
        with app.conn() as c:
            settlement = c.execute(
                "SELECT * FROM settlements WHERE party=?",
                ("Atomicity Test Party",),
            ).fetchall()
            assert len(settlement) == 1, [dict(row) for row in settlement]
            settlement_id = settlement[0]["id"]
            mirrors = c.execute(
                """SELECT * FROM cash_movements
                   WHERE source_table='settlements' AND source_id=?""",
                (settlement_id,),
            ).fetchall()
            assert len(mirrors) == 1, [dict(row) for row in mirrors]
            assert mirrors[0]["kind"] == "deposit"
            # Settlement form values are entered in toman; strict_money_int
            # stores the equivalent integer-rial amount (×10) in both ledgers.
            assert settlement[0]["amount"] == 12500
            assert mirrors[0]["amount"] == 12500
            assert settlement[0]["person_id"]
            assert c.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action='add_settlement'"
            ).fetchone()[0] == before["audit"] + 1
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    app.init()
    with app.conn() as c:
        test_legacy_internal_spacing_mismatch(c)
    test_settlement_sync_failure_rolls_back_everything()
    print("TRANSACTION BOUNDARY CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

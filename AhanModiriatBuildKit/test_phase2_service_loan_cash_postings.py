# -*- coding: utf-8 -*-
"""HTTP regression tests for service cash postings and legacy loan-payment postings."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_service_cash_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def token_for(action):
    with app.conn() as c:
        markup = app.submission_token(c, action)
        return markup.split('value="', 1)[1].split('"', 1)[0]


def post(port, fields, token=None):
    fields = dict(fields)
    fields["_submission_token"] = token or token_for("add_service")
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/add_service",
        data=data,
        headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        return response.read().decode("utf-8")


def main():
    app.init()
    with app.conn() as c:
        loan_id = c.execute(
            "INSERT INTO loans(title,principal,remaining,installment) VALUES('legacy loan',10000,9000,1000)"
        ).lastrowid
        payment_id = c.execute(
            """INSERT INTO loan_payments(loan_id,date,amount,principal_part,interest_part,source,notes)
               VALUES(?, '2026-02-03',5000,4000,1000,'legacy bank','historic payment')""",
            (loan_id,),
        ).lastrowid
    # Backfill historical payments without enabling new loan-payment entry.
    app.init()
    with app.conn() as c:
        posting = c.execute(
            "SELECT amount,kind FROM cash_movements WHERE source_table='loan_payments' AND source_id=?",
            (payment_id,),
        ).fetchone()
        assert posting is not None and tuple(posting) == (5000, "withdraw")
        app.sync_cash_posting(
            c, "loan_payments", payment_id, "2026-02-03", 5000,
            "out", "legacy bank", "reconciled historical payment",
        )
        assert c.execute(
            "SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments' AND source_id=?",
            (payment_id,),
        ).fetchone()[0] == 1
        revised = c.execute(
            "SELECT amount,note FROM cash_movements WHERE source_table='loan_payments' AND source_id=?",
            (payment_id,),
        ).fetchone()
        assert tuple(revised) == (5000, "reconciled historical payment")
        assert c.execute("SELECT COUNT(*) FROM loan_payments WHERE id=?", (payment_id,)).fetchone()[0] == 1

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        fields = {
            "date": "2026-02-04", "title": "Cash mirror service",
            "revenue": "900", "cost": "200", "received": "350",
            "customer": "Service customer", "notes": "service receipt",
        }
        token = token_for("add_service")
        post(port, fields, token=token)
        # Replaying a one-use form token must not duplicate either source or posting.
        post(port, fields, token=token)
        with app.conn() as c:
            service = c.execute(
                "SELECT id FROM services WHERE title='Cash mirror service'"
            ).fetchone()
            assert service is not None
            postings = c.execute(
                "SELECT date,kind,amount,party,note FROM cash_movements WHERE source_table='services' AND source_id=?",
                (service["id"],),
            ).fetchall()
            assert len(postings) == 1
            assert tuple(postings[0]) == (
                "2026-02-04", "deposit", 3500, "Service customer", "service receipt"
            )
            before = (
                c.execute("SELECT COUNT(*) FROM services").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='services'").fetchone()[0],
                app.account_balance(c, 1),
            )

        invalid = dict(fields, title="Invalid service", revenue="-1")
        post(port, invalid)
        with app.conn() as c:
            after = (
                c.execute("SELECT COUNT(*) FROM services").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='services'").fetchone()[0],
                app.account_balance(c, 1),
            )
            assert after == before, (before, after)

        original_sync = app.sync_cash_posting
        def fail_after_cash_mirror(*args, **kwargs):
            original_sync(*args, **kwargs)
            raise RuntimeError("injected failure after cash mirror")
        app.sync_cash_posting = fail_after_cash_mirror
        try:
            post(port, dict(fields, title="Rollback service", received="125"))
        finally:
            app.sync_cash_posting = original_sync
        with app.conn() as c:
            assert c.execute(
                "SELECT COUNT(*) FROM services WHERE title='Rollback service'"
            ).fetchone()[0] == 0
            assert c.execute(
                "SELECT COUNT(*) FROM cash_movements WHERE source_table='services' AND party='Service customer'"
            ).fetchone()[0] == 1
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print("SERVICE CASH AND HISTORICAL LOAN POSTING TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

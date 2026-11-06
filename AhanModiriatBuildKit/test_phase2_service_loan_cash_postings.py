# -*- coding: utf-8 -*-
"""HTTP-level cash mirror tests for service receipts and loan payments."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_service_loan_cash_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def post(port, path, fields, token=None):
    fields = dict(fields)
    if path in {"add_service", "add_payment"}:
        if token is None:
            with app.conn() as c:
                token_markup = app.submission_token(c, path)
                token = token_markup.split('value="', 1)[1].split('"', 1)[0]
        fields["_submission_token"] = token
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{path}",
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
        loan_cur = c.execute(
            """INSERT INTO loans(title,principal,remaining,installment,next_date,rate_note,notes,interval_value,interval_unit)
               VALUES('Cash mirror test loan',10000,10000,2500,'2026-03-01','','',1,'month')"""
        )
        loan_id = loan_cur.lastrowid
        balance_before = app.account_balance(c, 1)

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        post(port, "add_service", {
            "date": "2026-02-04", "title": "Cash mirror service",
            "revenue": "900", "cost": "200", "received": "350",
            "customer": "Service customer", "notes": "service receipt",
        })
        with app.conn() as c:
            service = c.execute(
                "SELECT id FROM services WHERE title='Cash mirror service'"
            ).fetchone()
            assert service is not None
            posting = c.execute(
                """SELECT date,kind,amount,party,note FROM cash_movements
                   WHERE source_table='services' AND source_id=?""",
                (service["id"],),
            ).fetchone()
            assert posting is not None, "service receipt must create its cash mirror"
            assert tuple(posting) == (
                "2026-02-04", "deposit", 3500, "Service customer", "service receipt"
            ), dict(posting)

        # Replaying the exact same one-use form token must not create a second
        # source record or a second cash posting.
        with app.conn() as c:
            token_markup = app.submission_token(c, "add_service")
            replay_token = token_markup.split('value="', 1)[1].split('"', 1)[0]
            before_replay = (
                c.execute("SELECT COUNT(*) FROM services").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='services'").fetchone()[0],
                app.account_balance(c, 1),
            )
        replay_fields = {
            "date": "2026-02-04", "title": "Replay protected service",
            "revenue": "400", "cost": "50", "received": "175",
            "customer": "Replay customer", "notes": "one-use token replay",
        }
        post(port, "add_service", replay_fields, token=replay_token)
        post(port, "add_service", replay_fields, token=replay_token)
        with app.conn() as c:
            after_replay = (
                c.execute("SELECT COUNT(*) FROM services").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='services'").fetchone()[0],
                app.account_balance(c, 1),
            )
        assert after_replay == (
            before_replay[0] + 1, before_replay[1] + 1, before_replay[2] + 175
        ), (before_replay, after_replay)

        post(port, "add_service", {
            "date": "2026-02-05", "title": "Unpaid cash mirror service",
            "revenue": "500", "cost": "100", "received": "0",
            "customer": "Unpaid customer", "notes": "no cash received",
        })
        with app.conn() as c:
            unpaid = c.execute(
                "SELECT id FROM services WHERE title='Unpaid cash mirror service'"
            ).fetchone()
            assert unpaid is not None
            assert c.execute(
                "SELECT 1 FROM cash_movements WHERE source_table='services' AND source_id=?",
                (unpaid["id"],),
            ).fetchone() is None, "zero service receipt must not create a cash movement"

        # A mismatched installment must be rejected without partially writing
        # a payment, cash movement, or loan-balance update.
        post(port, "add_payment", {
            "loan_id": str(loan_id), "date": "2026-02-06",
            "amount": "250", "principal_part": "200", "interest_part": "40",
            "source": "Rejected loan payment", "notes": "amount mismatch",
        })
        with app.conn() as c:
            assert c.execute(
                "SELECT COUNT(*) FROM loan_payments WHERE loan_id=?", (loan_id,)
            ).fetchone()[0] == 0
            assert c.execute(
                "SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments'"
            ).fetchone()[0] == 0
            assert c.execute(
                "SELECT remaining FROM loans WHERE id=?", (loan_id,)
            ).fetchone()["remaining"] == 10000

        # Invalid loan-payment edge cases must leave every financial table unchanged.
        invalid_payment_cases = [
            {
                "loan_id": "999999", "date": "2026-02-06",
                "amount": "250", "principal_part": "200", "interest_part": "50",
                "source": "Missing loan", "notes": "unknown loan",
            },
            {
                "loan_id": str(loan_id), "date": "2026-02-06",
                "amount": "10500", "principal_part": "10001", "interest_part": "499",
                "source": "Over-principal payment", "notes": "principal exceeds balance",
            },
            {
                "loan_id": str(loan_id), "date": "2026-02-06",
                "amount": "250", "principal_part": "300", "interest_part": "-50",
                "source": "Negative interest", "notes": "negative split",
            },
            {
                "loan_id": str(loan_id), "date": "2026-02-31",
                "amount": "250", "principal_part": "200", "interest_part": "50",
                "source": "Invalid payment date", "notes": "invalid calendar date",
            },
        ]
        for invalid_fields in invalid_payment_cases:
            with app.conn() as c:
                before = (
                    c.execute("SELECT COUNT(*) FROM loan_payments WHERE loan_id=?", (loan_id,)).fetchone()[0],
                    c.execute(
                        "SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments' AND source_id IN (SELECT id FROM loan_payments WHERE loan_id=?)",
                        (loan_id,),
                    ).fetchone()[0],
                    c.execute("SELECT remaining FROM loans WHERE id=?", (loan_id,)).fetchone()["remaining"],
                    app.account_balance(c, 1),
                )
            post(port, "add_payment", invalid_fields)
            with app.conn() as c:
                after = (
                    c.execute("SELECT COUNT(*) FROM loan_payments WHERE loan_id=?", (loan_id,)).fetchone()[0],
                    c.execute(
                        "SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments' AND source_id IN (SELECT id FROM loan_payments WHERE loan_id=?)",
                        (loan_id,),
                    ).fetchone()[0],
                    c.execute("SELECT remaining FROM loans WHERE id=?", (loan_id,)).fetchone()["remaining"],
                    app.account_balance(c, 1),
                )
            assert after == before, (
                f"invalid loan payment caused partial financial writes: {invalid_fields}; "
                f"before={before}, after={after}"
            )

        post(port, "add_payment", {
            "loan_id": str(loan_id), "date": "2026-02-06",
            "amount": "250", "principal_part": "200", "interest_part": "50",
            "source": "Loan payment source", "notes": "installment payment",
        })
        with app.conn() as c:
            payment = c.execute(
                "SELECT id FROM loan_payments WHERE loan_id=? ORDER BY id DESC LIMIT 1",
                (loan_id,),
            ).fetchone()
            assert payment is not None
            posting = c.execute(
                """SELECT date,kind,amount,party,note FROM cash_movements
                   WHERE source_table='loan_payments' AND source_id=?""",
                (payment["id"],),
            ).fetchone()
            assert posting is not None, "loan payment must create its cash mirror"
            assert tuple(posting) == (
                "2026-02-06", "withdraw", 2500, "Loan payment source", "installment payment"
            ), dict(posting)
            loan = c.execute("SELECT remaining FROM loans WHERE id=?", (loan_id,)).fetchone()
            assert loan["remaining"] == 8000, dict(loan)
            assert app.account_balance(c, 1) == balance_before + 1000
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

            # Re-syncing the same source must replace, not duplicate, its cash mirror.
            service_id = c.execute(
                "SELECT id FROM services WHERE title='Cash mirror service'"
            ).fetchone()["id"]
            payment_id = c.execute(
                "SELECT id FROM loan_payments WHERE loan_id=?", (loan_id,)
            ).fetchone()["id"]

            # Simulate a legacy duplicate and verify the source sync repairs it.
            c.execute(
                """INSERT INTO cash_movements(date,kind,to_account_id,amount,source_table,source_id)
                   VALUES('2026-02-04','deposit',1,3500,'services',?)""",
                (service_id,),
            )
            assert c.execute(
                "SELECT COUNT(*) FROM cash_movements WHERE source_table='services' AND source_id=?",
                (service_id,),
            ).fetchone()[0] == 2
            app.sync_cash_posting(
                c, "services", service_id, "2026-02-04", 4500,
                "in", "Service customer", "re-synced service receipt",
            )
            service_postings = c.execute(
                "SELECT amount,note FROM cash_movements WHERE source_table='services' AND source_id=?",
                (service_id,),
            ).fetchall()
            assert len(service_postings) == 1
            assert tuple(service_postings[0]) == (4500, "re-synced service receipt")

            # Zero means the source no longer represents a cash movement.
            app.sync_cash_posting(
                c, "services", service_id, "2026-02-04", 0,
                "in", "Service customer", "zero service receipt",
            )
            assert c.execute(
                "SELECT COUNT(*) FROM cash_movements WHERE source_table='services' AND source_id=?",
                (service_id,),
            ).fetchone()[0] == 0
            # Restore the original receipt for the final balance assertion.
            app.sync_cash_posting(
                c, "services", service_id, "2026-02-04", 3500,
                "in", "Service customer", "service receipt",
            )

            # Loan-payment sync follows the same idempotent and zero-removal contract.
            app.sync_cash_posting(
                c, "loan_payments", payment_id, "2026-02-06", 2700,
                "out", "Loan payment source", "re-synced installment",
            )
            loan_postings = c.execute(
                "SELECT amount,note FROM cash_movements WHERE source_table='loan_payments' AND source_id=?",
                (payment_id,),
            ).fetchall()
            assert len(loan_postings) == 1
            assert tuple(loan_postings[0]) == (2700, "re-synced installment")
            app.sync_cash_posting(
                c, "loan_payments", payment_id, "2026-02-06", 0,
                "out", "Loan payment source", "zero installment",
            )
            assert c.execute(
                "SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments' AND source_id=?",
                (payment_id,),
            ).fetchone()[0] == 0
            app.sync_cash_posting(
                c, "loan_payments", payment_id, "2026-02-06", 2500,
                "out", "Loan payment source", "installment payment",
            )

            assert app.account_balance(c, 1) == balance_before + 1000
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

        # Force a failure after the source row and cash mirror have both been
        # written. The request transaction must roll both writes back.
        original_sync = app.sync_cash_posting

        def fail_after_cash_mirror(*args, **kwargs):
            original_sync(*args, **kwargs)
            raise RuntimeError("injected failure after cash mirror")

        with app.conn() as c:
            before_service_rollback = (
                c.execute("SELECT COUNT(*) FROM services").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='services'").fetchone()[0],
                app.account_balance(c, 1),
            )
        app.sync_cash_posting = fail_after_cash_mirror
        try:
            post(port, "add_service", {
                "date": "2026-02-07", "title": "Rollback service",
                "revenue": "300", "cost": "20", "received": "125",
                "customer": "Rollback customer", "notes": "injected rollback",
            })
        finally:
            app.sync_cash_posting = original_sync
        with app.conn() as c:
            after_service_rollback = (
                c.execute("SELECT COUNT(*) FROM services").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='services'").fetchone()[0],
                app.account_balance(c, 1),
            )
        assert after_service_rollback == before_service_rollback, (
            before_service_rollback, after_service_rollback
        )

        with app.conn() as c:
            before_payment_rollback = (
                c.execute("SELECT COUNT(*) FROM loan_payments WHERE loan_id=?", (loan_id,)).fetchone()[0],
                c.execute(
                    "SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments' AND source_id IN (SELECT id FROM loan_payments WHERE loan_id=?)",
                    (loan_id,),
                ).fetchone()[0],
                c.execute("SELECT remaining FROM loans WHERE id=?", (loan_id,)).fetchone()["remaining"],
                app.account_balance(c, 1),
            )
        app.sync_cash_posting = fail_after_cash_mirror
        try:
            post(port, "add_payment", {
                "loan_id": str(loan_id), "date": "2026-02-07",
                "amount": "100", "principal_part": "100", "interest_part": "0",
                "source": "Rollback loan payment", "notes": "injected rollback",
            })
        finally:
            app.sync_cash_posting = original_sync
        with app.conn() as c:
            after_payment_rollback = (
                c.execute("SELECT COUNT(*) FROM loan_payments WHERE loan_id=?", (loan_id,)).fetchone()[0],
                c.execute(
                    "SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments' AND source_id IN (SELECT id FROM loan_payments WHERE loan_id=?)",
                    (loan_id,),
                ).fetchone()[0],
                c.execute("SELECT remaining FROM loans WHERE id=?", (loan_id,)).fetchone()["remaining"],
                app.account_balance(c, 1),
            )
        assert after_payment_rollback == before_payment_rollback, (
            before_payment_rollback, after_payment_rollback
        )

        print("SERVICE AND LOAN CASH MIRROR TESTS PASSED")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

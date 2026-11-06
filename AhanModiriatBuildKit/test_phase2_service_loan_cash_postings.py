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


def post(port, path, fields):
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
               VALUES('Cash mirror test loan',1000,1000,250,'2026-03-01','','',1,'month')"""
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
                "2026-02-04", "deposit", 350, "Service customer", "service receipt"
            ), dict(posting)

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
                "2026-02-06", "withdraw", 250, "Loan payment source", "installment payment"
            ), dict(posting)
            loan = c.execute("SELECT remaining FROM loans WHERE id=?", (loan_id,)).fetchone()
            assert loan["remaining"] == 800, dict(loan)
            assert app.account_balance(c, 1) == balance_before + 100
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

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

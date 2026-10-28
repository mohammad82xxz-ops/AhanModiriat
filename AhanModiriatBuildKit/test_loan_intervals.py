# -*- coding: utf-8 -*-
"""Regression tests for configurable loan repayment intervals."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_loan_intervals_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def post(port, path, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{path}", data=data,
        headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        return response.read().decode("utf-8")


def main():
    assert app.add_interval_date("2026-01-31", 1, "month") == "2026-02-28"
    assert app.add_interval_date("2026-01-31", 2, "week") == "2026-02-14"
    assert app.add_interval_date("2024-02-29", 1, "year") == "2025-02-28"
    assert app.add_interval_date("", 1, "month") == ""

    app.init()
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        post(port, "add_loan", {
            "title":"monthly loan", "principal":"100", "remaining":"100", "installment":"50",
            "next_date":"2026-01-31", "interval_value":"1", "interval_unit":"month",
            "rate_note":"test", "notes":"month-end test"
        })
        with app.conn() as c:
            loan = c.execute("SELECT * FROM loans WHERE title='monthly loan'").fetchone()
            loan_id = loan["id"]
            assert loan["interval_value"] == 1 and loan["interval_unit"] == "month"
        post(port, "add_payment", {
            "loan_id":loan_id, "date":"2026-01-31", "amount":"50", "principal_part":"50",
            "interest_part":"0", "source":"نامشخص", "notes":"one payment"
        })
        with app.conn() as c:
            loan = c.execute("SELECT * FROM loans WHERE id=?", (loan_id,)).fetchone()
            assert loan["remaining"] == 50
            assert loan["next_date"] == "2026-02-28", loan["next_date"]
            assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE source_table='loan_payments'").fetchone()[0] == 1

        post(port, "add_loan", {
            "title":"biweekly loan", "principal":"40", "remaining":"40", "installment":"20",
            "next_date":"2026-01-31", "interval_value":"2", "interval_unit":"week",
            "rate_note":"test", "notes":"two-week test"
        })
        with app.conn() as c:
            loan2 = c.execute("SELECT * FROM loans WHERE title='biweekly loan'").fetchone()
        post(port, "add_payment", {
            "loan_id":loan2["id"], "date":"2026-02-01", "amount":"20", "principal_part":"20",
            "interest_part":"0", "source":"نامشخص", "notes":"one two-week payment"
        })
        with app.conn() as c:
            loan2 = c.execute("SELECT * FROM loans WHERE id=?", (loan2["id"],)).fetchone()
            assert loan2["next_date"] == "2026-02-14", loan2["next_date"]
            assert "۲ هفته" in app.loans(c) or "2 هفته" in app.loans(c)
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        server.shutdown()
        server.server_close()
    print("LOAN INTERVAL TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

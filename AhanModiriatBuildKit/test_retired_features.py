# -*- coding: utf-8 -*-
"""Regression tests for retired UI/actions and preservation of historical finance data."""
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_retired_features_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def expect_http_error(url, method="GET", fields=None, expected=404):
    data = None
    headers = {"Host": "127.0.0.1"}
    if fields is not None:
        from urllib.parse import urlencode
        data = urlencode(fields).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        urllib.request.urlopen(request, timeout=5)
    except urllib.error.HTTPError as error:
        assert error.code == expected, (url, error.code, expected)
        error.read()
    else:
        raise AssertionError(f"{method} {url} should return HTTP {expected}")


def main():
    app.init()
    with app.conn() as c:
        # Simulate legacy records from a database created before feature retirement.
        c.execute("INSERT INTO cash_accounts(id,name,account_type,opening_balance) VALUES(2,'legacy bank','bank',0)")
        c.execute("INSERT INTO loans(title,principal,remaining,installment) VALUES('Archived loan',1000,900,100)")
        loan_id = c.execute("SELECT id FROM loans WHERE title='Archived loan'").fetchone()["id"]
        c.execute("""INSERT INTO loan_payments(loan_id,date,amount,principal_part,interest_part,source,notes)
                     VALUES(?, '2026-05-13',200,100,100,'legacy bank','historical installment')""", (loan_id,))
        c.execute("""INSERT INTO cash_movements(date,kind,from_account_id,to_account_id,amount,party,note)
                     VALUES('2026-05-14','transfer',1,2,70,'','legacy manual transfer')""")
        c.execute("""INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
                     VALUES('low stock preserved','عدد',1,100,150,3)""")

    # Existing loan payments are backfilled once and remain part of financial history.
    app.init()
    with app.conn() as c:
        assert c.execute("SELECT COUNT(*) FROM loans WHERE id=?", (loan_id,)).fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM loan_payments WHERE loan_id=?", (loan_id,)).fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM cash_accounts WHERE id=2").fetchone()[0] == 1
        assert c.execute("SELECT COUNT(*) FROM cash_movements WHERE note='legacy manual transfer'").fetchone()[0] == 1
        historical_posting = c.execute(
            "SELECT amount,kind FROM cash_movements WHERE source_table='loan_payments'"
        ).fetchone()
        assert historical_posting is not None
        assert (historical_posting["amount"], historical_posting["kind"]) == (2000, "withdraw")
        result = app.calc(c, "2026-05-13", "2026-05-13")
        assert result["interest"] == 1000 and result["loan_paid"] == 2000, result
        report = app.report_detail_sections(c)
        assert "سود/کارمزد وام" in report
        assert "سود به تفکیک مشتری" not in report
        dashboard = app.dash(c)
        assert "وام‌ها و اقساط آینده" not in dashboard
        assert "مانده اصل وام‌ها" not in dashboard
        assert "کل اقساط پرداخت‌شده" not in dashboard
        assert "low stock preserved" in dashboard
        assert not hasattr(app, "loans")
        assert not hasattr(app, "cash_page")
        assert not hasattr(app, "purchase_advice")
        assert not hasattr(app, "compute_purchase_advice")

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for route in ("/loans", "/cash", "/buy-advice"):
            expect_http_error(base + route, expected=404)

        with app.conn() as c:
            before = (
                c.execute("SELECT COUNT(*) FROM loans").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM loan_payments").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
            )
        for action in ("add_loan", "add_payment", "add_cash_movement"):
            expect_http_error(base + "/" + action, method="POST", fields={"legacy":"blocked"}, expected=410)
        with app.conn() as c:
            after = (
                c.execute("SELECT COUNT(*) FROM loans").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM loan_payments").fetchone()[0],
                c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
            )
            assert after == before, (before, after)
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    print("RETIRED FEATURES AND HISTORICAL DATA TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

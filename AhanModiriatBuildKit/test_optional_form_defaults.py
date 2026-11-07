# -*- coding: utf-8 -*-
"""Regression tests for numeric defaults on omitted optional form fields."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_optional_form_defaults_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def post(port: int, path: str, fields: dict[str, object]) -> None:
    fields = dict(fields)
    if path == "add_loan" and "_submission_token" not in fields:
        with app.conn() as c:
            markup = app.submission_token(c, path)
            fields["_submission_token"] = markup.split('value="', 1)[1].split('"', 1)[0]
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
        assert response.status == 200


def main() -> None:
    app.init()
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # purchase_factor and sale_factor both default to integer 1.
        # Omitting them used to call .strip() on int and crash the POST handler.
        post(port, "add_product", {
            "name": "optional defaults steel",
            "unit": "کیلوگرم",
            "stock": "0",
            "avg_cost": "0",
            "market_price": "0",
        })
        with app.conn() as c:
            product = c.execute(
                """SELECT purchase_factor,sale_factor,purchase_unit,sale_unit
                   FROM products WHERE name=?""",
                ("optional defaults steel",),
            ).fetchone()
            assert product is not None, "product with omitted optional factors was not saved"
            assert tuple(product) == (1, 1, "کیلوگرم", "کیلوگرم"), tuple(product)

        # interval_value also defaults to integer 1; interval_unit is a string default.
        post(port, "add_loan", {
            "title": "optional interval default loan",
            "principal": "1000",
            "remaining": "1000",
            "installment": "100",
        })
        with app.conn() as c:
            loan = c.execute(
                "SELECT interval_value,interval_unit FROM loans WHERE title=?",
                ("optional interval default loan",),
            ).fetchone()
            assert loan is not None, "loan with omitted interval fields was not saved"
            assert tuple(loan) == (1, "month"), tuple(loan)

        # Check persisted state and audit evidence, not merely that the connection
        # factory exists (the previous assertion did not exercise the database).
        with app.conn() as c:
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
            audit_actions = dict(c.execute(
                """SELECT action,COUNT(*) FROM audit_log
                   WHERE action IN ('add_product','add_loan') GROUP BY action"""
            ))
            assert audit_actions == {"add_product": 1, "add_loan": 1}, audit_actions

        print("OPTIONAL FORM DEFAULTS TESTS PASSED")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        TMP.cleanup()


if __name__ == "__main__":
    main()

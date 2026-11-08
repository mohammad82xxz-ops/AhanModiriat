# -*- coding: utf-8 -*-
"""Characterize action binding and non-consumption of one-use financial tokens."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_token_action_binding_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def post(port, path, fields):
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
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response = opener.open(request, timeout=10)
    except urllib.error.HTTPError as exc:
        if exc.code != 303:
            raise
        response = exc
    with response:
        return response.code, response.headers.get("Location", "")


def redirect_message(location):
    return urllib.parse.parse_qs(
        urllib.parse.urlparse(location).query
    ).get("msg", [""])[0]


def main():
    app.init()
    with closing(app.conn()) as c, c:
        markup = app.submission_token(c, "add_settlement")
        token = markup.split('value="', 1)[1].split('"', 1)[0]
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
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        # A token issued for settlement must not authorize a different financial route.
        wrong_status, wrong_location = post(port, "add_price", {
            "date": "2026-02-05",
            "product_id": "1",
            "market_price": "900",
            "notes": "action-binding-negative-control",
            "_submission_token": token,
        })
        assert wrong_status == 303, (wrong_status, wrong_location)
        assert "قبلاً ارسال شده یا منقضی است" in redirect_message(wrong_location), wrong_location

        with closing(app.conn()) as c, c:
            after_wrong_route = {
                "people": c.execute("SELECT COUNT(*) FROM people").fetchone()[0],
                "settlements": c.execute("SELECT COUNT(*) FROM settlements").fetchone()[0],
                "cash": c.execute("SELECT COUNT(*) FROM cash_movements").fetchone()[0],
                "audit": c.execute(
                    "SELECT COUNT(*) FROM audit_log WHERE action='add_settlement'"
                ).fetchone()[0],
            }
            token_row = c.execute(
                "SELECT action,consumed_at FROM form_submission_tokens WHERE token=?",
                (token,),
            ).fetchone()
            assert after_wrong_route == before, (before, after_wrong_route)
            assert token_row is not None, "issued token disappeared"
            assert token_row["action"] == "add_settlement", dict(token_row)
            assert token_row["consumed_at"] is None, dict(token_row)

        # The rejected cross-route attempt must not consume the token for its intended route.
        good_status, good_location = post(port, "add_settlement", {
            "party": "Action Binding Party",
            "kind": "receive",
            "date": "2026-02-05",
            "amount": "1250",
            "notes": "action-binding-positive-control",
            "_submission_token": token,
        })
        assert good_status == 303, (good_status, good_location)
        assert "تسویه ثبت شد و دفتر صندوق به‌روز شد." in redirect_message(good_location), good_location

        with closing(app.conn()) as c, c:
            settlements = c.execute(
                "SELECT * FROM settlements WHERE party=?",
                ("Action Binding Party",),
            ).fetchall()
            assert len(settlements) == 1, [dict(row) for row in settlements]
            settlement = settlements[0]
            assert settlement["amount"] == 12500, settlement["amount"]
            mirrors = c.execute(
                """SELECT * FROM cash_movements
                   WHERE source_table='settlements' AND source_id=?""",
                (settlement["id"],),
            ).fetchall()
            assert len(mirrors) == 1, [dict(row) for row in mirrors]
            assert mirrors[0]["amount"] == 12500, dict(mirrors[0])
            assert c.execute(
                "SELECT COUNT(*) FROM people WHERE name=?",
                ("Action Binding Party",),
            ).fetchone()[0] == 1
            assert c.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action='add_settlement'"
            ).fetchone()[0] == before["audit"] + 1
            token_row = c.execute(
                "SELECT consumed_at FROM form_submission_tokens WHERE token=?",
                (token,),
            ).fetchone()
            assert token_row is not None and token_row["consumed_at"] is not None
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

        # Replaying the now-consumed token on its correct route is also rejected.
        replay_status, replay_location = post(port, "add_settlement", {
            "party": "Action Binding Party",
            "kind": "receive",
            "date": "2026-02-05",
            "amount": "1250",
            "notes": "action-binding-replay",
            "_submission_token": token,
        })
        assert replay_status == 303, (replay_status, replay_location)
        assert "قبلاً ارسال شده یا منقضی است" in redirect_message(replay_location), replay_location
        with closing(app.conn()) as c, c:
            assert c.execute(
                "SELECT COUNT(*) FROM settlements WHERE party=?",
                ("Action Binding Party",),
            ).fetchone()[0] == 1
            assert c.execute(
                "SELECT COUNT(*) FROM cash_movements WHERE source_table='settlements'"
            ).fetchone()[0] == before["cash"] + 1
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

        print("TOKEN ACTION-BINDING CHARACTERIZATION PASSED")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        TMP.cleanup()


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

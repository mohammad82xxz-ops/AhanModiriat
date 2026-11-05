# -*- coding: utf-8 -*-
"""Single-process concurrency characterization for one-use financial form tokens."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_token_race_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def _post(port, fields):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/add_settlement",
        data=data,
        headers={
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status, response.read().decode("utf-8")


def main():
    app.init()
    with app.conn() as c:
        markup = app.submission_token(c, "add_settlement")
        token = markup.split('value="', 1)[1].split('"', 1)[0]

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    barrier = threading.Barrier(3)

    def submit_same_token():
        barrier.wait(timeout=10)
        return _post(port, {
            "party": "Concurrent Token Party",
            "kind": "receive",
            "date": "2026-02-03",
            "amount": "1250",
            "notes": "same-token-race",
            "_submission_token": token,
        })

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(submit_same_token) for _ in range(2)]
            barrier.wait(timeout=10)
            responses = [future.result(timeout=15) for future in futures]

        with app.conn() as c:
            settlements = c.execute(
                "SELECT * FROM settlements WHERE party=?",
                ("Concurrent Token Party",),
            ).fetchall()
            assert len(settlements) == 1, [dict(row) for row in settlements]
            settlement = settlements[0]
            assert settlement["kind"] == "receive"
            assert settlement["amount"] == 12500

            mirrors = c.execute(
                """SELECT * FROM cash_movements
                   WHERE source_table='settlements' AND source_id=?""",
                (settlement["id"],),
            ).fetchall()
            assert len(mirrors) == 1, [dict(row) for row in mirrors]
            assert mirrors[0]["kind"] == "deposit"
            assert mirrors[0]["amount"] == 12500

            assert c.execute(
                "SELECT COUNT(*) FROM people WHERE name=?",
                ("Concurrent Token Party",),
            ).fetchone()[0] == 1
            assert c.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action='add_settlement'"
            ).fetchone()[0] == 1
            token_row = c.execute(
                "SELECT consumed_at FROM form_submission_tokens WHERE token=?",
                (token,),
            ).fetchone()
            assert token_row is not None and token_row["consumed_at"] is not None
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

        assert len(responses) == 2, responses
        print("SINGLE-PROCESS TOKEN CONCURRENCY CHARACTERIZATION PASSED")
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

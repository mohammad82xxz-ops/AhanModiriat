# -*- coding: utf-8 -*-
"""Cross-process characterization for one-use financial form submission tokens."""
import multiprocessing
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


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
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        response_obj = opener.open(request, timeout=25)
    except urllib.error.HTTPError as exc:
        if exc.code != 303:
            raise
        response_obj = exc
    with response_obj:
        return response_obj.code, response_obj.headers.get("Location", "")


def _serve_one_process(ready_queue):
    """Run one independent app server; each process has its own in-memory LOCK."""
    try:
        import app

        server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
        ready_queue.put(("ready", server.server_address[1]))
        server.serve_forever(poll_interval=0.1)
    except BaseException as exc:
        ready_queue.put(("error", repr(exc)))
        raise


def main():
    with tempfile.TemporaryDirectory(prefix="ahan_token_multiprocess_") as temp_dir:
        os.environ["AHAN_DATA_DIR"] = str(Path(temp_dir) / "shared-appdata")
        os.environ["AHAN_NOBROWSER"] = "1"
        import app

        app.init()
        with closing(app.conn()) as c, c:
            markup = app.submission_token(c, "add_settlement")
            token = markup.split('value="', 1)[1].split('"', 1)[0]

        # Spawn forces genuinely independent Python processes rather than threads
        # sharing the module-level threading.Lock.
        context = multiprocessing.get_context("spawn")
        ready_queue = context.Queue()
        processes = [
            context.Process(target=_serve_one_process, args=(ready_queue,))
            for _ in range(2)
        ]
        ports = []
        try:
            for process in processes:
                process.start()
            for _ in processes:
                state, value = ready_queue.get(timeout=20)
                assert state == "ready", value
                ports.append(value)

            fields = {
                "party": "Multiprocess Token Party",
                "kind": "receive",
                "date": "2026-02-04",
                "amount": "1250",
                "notes": "same-token-multiprocess-race",
                "_submission_token": token,
            }

            # Requests reach different server processes concurrently. Their
            # process-local LOCK objects cannot serialize one another.
            from threading import Barrier

            barrier = Barrier(3)

            def submit(port):
                barrier.wait(timeout=15)
                return _post(port, fields)

            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(submit, port) for port in ports]
                barrier.wait(timeout=15)
                responses = [future.result(timeout=35) for future in futures]

            with closing(app.conn()) as c, c:
                settlements = c.execute(
                    "SELECT * FROM settlements WHERE party=?",
                    ("Multiprocess Token Party",),
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
                    ("Multiprocess Token Party",),
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
            assert all(status == 303 for status, _location in responses), responses
            messages = [
                urllib.parse.parse_qs(
                    urllib.parse.urlparse(location).query
                ).get("msg", [""])[0]
                for _status, location in responses
            ]
            assert sum(
                "تسویه ثبت شد و دفتر صندوق به‌روز شد." in message
                for message in messages
            ) == 1, messages
            assert sum(
                "این فرم قبلاً ارسال شده یا منقضی است" in message
                for message in messages
            ) == 1, messages
            print("CROSS-PROCESS TOKEN CONCURRENCY CHARACTERIZATION PASSED")
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=10)
            ready_queue.close()
            ready_queue.join_thread()


if __name__ == "__main__":
    main()

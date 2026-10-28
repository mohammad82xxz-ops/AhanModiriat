# -*- coding: utf-8 -*-
"""Loopback Host/Origin validation and browser security-header regression tests."""
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_local_security_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def request(port, path, *, fields=None, host=None, origin=None, referer=None, fetch_site=None):
    headers = {"Host": host or f"127.0.0.1:{port}"}
    if fields is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        if origin is not None:
            headers["Origin"] = origin
        if referer is not None:
            headers["Referer"] = referer
        if fetch_site is not None:
            headers["Sec-Fetch-Site"] = fetch_site
        data = urllib.parse.urlencode(fields).encode("utf-8")
        req = urllib.request.Request(f"http://127.0.0.1:{port}/{path}", data=data, headers=headers, method="POST")
    else:
        if origin is not None:
            headers["Origin"] = origin
        if referer is not None:
            headers["Referer"] = referer
        if fetch_site is not None:
            headers["Sec-Fetch-Site"] = fetch_site
        req = urllib.request.Request(f"http://127.0.0.1:{port}/{path}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status, response.headers, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read().decode("utf-8", "replace")


def main():
    app.init()
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{port}"
    try:
        status, headers, html = request(port, "parties")
        assert status == 200
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("Referrer-Policy") == "no-referrer"
        assert "frame-ancestors 'none'" in headers.get("Content-Security-Policy", "")
        assert headers.get("Cache-Control") == "no-store"
        assert "طرف حساب‌ها" in html

        status, _, _ = request(port, "parties", host="attacker.example")
        assert status == 403

        status, _, _ = request(port, "parties", fetch_site="cross-site")
        assert status == 403

        # A hostile cross-origin form post must be rejected before creating any record.
        status, _, _ = request(port, "add_person", fields={
            "name": "should not exist", "kind": "customer", "phone": "", "notes": ""
        }, origin="http://attacker.example", referer="http://attacker.example/form",
           fetch_site="cross-site")
        assert status == 403
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM people WHERE name='should not exist'").fetchone()[0] == 0

        # A normal same-origin browser form post remains supported.
        status, _, body = request(port, "add_person", fields={
            "name": "same origin person", "kind": "customer", "phone": "", "notes": ""
        }, origin=origin, referer=origin+"/parties", fetch_site="same-origin")
        assert status == 200
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM people WHERE name='same origin person'").fetchone()[0] == 1
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        server.shutdown()
        server.server_close()
    print("LOCAL HOST/ORIGIN SECURITY TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

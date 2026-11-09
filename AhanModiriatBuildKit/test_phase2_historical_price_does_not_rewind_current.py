# -*- coding: utf-8 -*-
"""Regression tests: recording an older market price must not rewind the current price."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_historical_price_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def post_price(port: int, product_id: int, date: str, price: int, note: str) -> None:
    with app.conn() as c:
        markup = app.submission_token(c, "add_price")
    token = markup.split('value="', 1)[1].split('"', 1)[0]
    payload = {
        "product_id": product_id,
        "date": date,
        "market_price": price,
        "notes": note,
        "_submission_token": token,
    }
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/add_price",
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200


def current_price(product_id: int) -> int:
    with app.conn() as c:
        return c.execute(
            "SELECT market_price FROM products WHERE id=?", (product_id,)
        ).fetchone()["market_price"]


def main() -> None:
    app.init()
    with app.conn() as c:
        c.execute(
            """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
               VALUES('historical price fixture A','kg',0,0,500,0)"""
        )
        first_id = c.execute(
            "SELECT id FROM products WHERE name='historical price fixture A'"
        ).fetchone()["id"]
        c.execute(
            """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
               VALUES('historical price fixture B','kg',0,0,600,0)"""
        )
        second_id = c.execute(
            "SELECT id FROM products WHERE name='historical price fixture B'"
        ).fetchone()["id"]

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # A newer rate establishes the current market price.
        post_price(port, first_id, "2026-11-08", 1200, "newer rate")
        assert current_price(first_id) == 1200

        # A later-entered but older-dated rate must remain historical only.
        post_price(port, first_id, "2026-11-07", 900, "backfilled historical rate")
        assert current_price(first_id) == 1200

        # Equal dates use the latest inserted row as a deterministic tie-break.
        post_price(port, first_id, "2026-11-08", 1300, "same-day correction")
        assert current_price(first_id) == 1300

        # Price history is isolated per product.
        post_price(port, second_id, "2026-11-09", 700, "other product rate")
        assert current_price(second_id) == 700
        assert current_price(first_id) == 1300

        with app.conn() as c:
            rows = c.execute(
                """SELECT date,market_price FROM price_history
                   WHERE product_id=? ORDER BY date DESC,id DESC""",
                (first_id,),
            ).fetchall()
            assert [(row["date"], row["market_price"]) for row in rows] == [
                ("2026-11-08", 1300),
                ("2026-11-08", 1200),
                ("2026-11-07", 900),
            ]
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        TMP.cleanup()

    print("HISTORICAL PRICE DOES NOT REWIND CURRENT PRICE TESTS PASSED")


if __name__ == "__main__":
    main()

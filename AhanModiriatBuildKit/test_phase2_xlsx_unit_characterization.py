# -*- coding: utf-8 -*-
"""B1 characterization of the current XLSX product-unit import behavior."""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_xlsx_units_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def multipart(sheet: str, payload: bytes) -> tuple[bytes, str]:
    boundary = "----AhanPhase2XlsxUnits"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"sheet\"\r\n\r\n{sheet}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"units.xlsx\"\r\n"
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def main() -> None:
    app.init()
    headers = [
        "name", "code", "unit", "stock", "avg_cost", "market_price",
        "min_stock", "category", "purchase_unit", "purchase_factor",
        "sale_unit", "sale_factor", "roll_weight", "sheet_area", "notes",
    ]
    rows = [
        headers,
        ["unknown unit fixture", "U-1", "cartonX", 4, 100, 120, 0,
         "synthetic", "bundleX", 5, "caseX", 2, 0, 0, "raw units"],
        # Current import uses value-or-default: explicit zero factors silently
        # become 1. This test records existing behavior, not desired policy.
        ["zero factor fixture", "U-2", "kg", 2, 100, 120, 0,
         "synthetic", "bundle", 0, "box", 0, 0, 0, "zero factor"],
        ["negative factor fixture", "U-3", "kg", 2, 100, 120, 0,
         "synthetic", "bundle", -2, "box", 1, 0, 0, "negative factor"],
    ]
    payload = app.build_xlsx_workbook([("Products", rows)])
    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        body, content_type = multipart("Products", payload)
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/import.xlsx",
            data=body,
            headers={
                "Host": f"127.0.0.1:{port}",
                "Content-Type": content_type,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            assert response.status == 200
        with app.conn() as c:
            raw = c.execute(
                "SELECT * FROM products WHERE name='unknown unit fixture'"
            ).fetchone()
            assert raw is not None
            assert raw["unit"] == "cartonX"
            assert raw["purchase_unit"] == "bundleX"
            assert raw["purchase_factor"] == 5
            assert raw["sale_unit"] == "caseX"
            assert raw["sale_factor"] == 2

            zero = c.execute(
                "SELECT * FROM products WHERE name='zero factor fixture'"
            ).fetchone()
            assert zero is not None
            assert zero["purchase_factor"] == 1
            assert zero["sale_factor"] == 1

            assert c.execute(
                "SELECT COUNT(*) FROM products WHERE name='negative factor fixture'"
            ).fetchone()[0] == 0
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        server.shutdown()
        server.server_close()
        TMP.cleanup()

    print("PHASE 2 XLSX UNIT CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    main()

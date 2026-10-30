# -*- coding: utf-8 -*-
"""XLSX round-trip and HTTP import tests for products and people."""
import os
import sys
import io
import zipfile
import tempfile
import threading
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_excel_io_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def multipart(fields, file_field, filename, payload):
    boundary = "----AhanExcelTestBoundary8c82"
    chunks = []
    for key, value in fields.items():
        chunks.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode("utf-8")
        )
    chunks.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; filename=\"{filename}\"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n".encode("utf-8")
        + payload + b"\r\n"
    )
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def post_import(port, sheet, payload):
    data, content_type = multipart({"sheet": sheet}, "file", "import.xlsx", payload)
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/import.xlsx",
        data=data,
        headers={"Host": f"127.0.0.1:{port}", "Content-Type": content_type},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 200
        return response.read().decode("utf-8")


def main():
    app.init()
    product_rows = [
        ["name","code","unit","stock","avg_cost","market_price","min_stock","category","purchase_unit","purchase_factor","sale_unit","sale_factor","roll_weight","sheet_area","notes"],
        ["excel steel","XS-1","kg",3,12,18,1,"پروفیل","bundle",10,"kg",1,0,0,"round-trip test"],
    ]
    people_rows = [
        ["name","kind","phone","notes"],
        ["Excel Customer","customer","09120000000","sample"],
    ]
    workbook_bytes = app.build_xlsx_workbook([("Products",product_rows),("People",people_rows)])
    parsed = app.parse_xlsx_workbook(workbook_bytes)
    assert parsed["Products"][1][0] == "excel steel"
    assert parsed["Products"][1][3] == "3"
    assert parsed["People"][1][0] == "Excel Customer"

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        post_import(port, "Products", workbook_bytes)
        with app.conn() as c:
            product = c.execute("SELECT * FROM products WHERE name='excel steel'").fetchone()
            assert product is not None
            assert product["stock"] == 3 and product["avg_cost"] == 12
        # A second import is idempotent for duplicate names and must not overwrite stock.
        post_import(port, "Products", workbook_bytes)
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM products WHERE name='excel steel'").fetchone()[0] == 1
            assert c.execute("SELECT stock FROM products WHERE name='excel steel'").fetchone()[0] == 3

        # Malformed/non-finite numeric cells must be skipped, never stored as NULL/NaN.
        invalid_product_rows = [
            ["name","code","unit","stock","avg_cost","market_price","min_stock","category","purchase_unit","purchase_factor","sale_unit","sale_factor","roll_weight","sheet_area","notes"],
            ["nan stock steel","NAN-1","kg","nan",12,18,1,"پروفیل","kg",1,"kg",1,0,0,"invalid stock"],
            ["infinite cost steel","INF-1","kg",3,"inf",18,1,"پروفیل","kg",1,"kg",1,0,0,"invalid cost"],
        ]
        invalid_workbook = app.build_xlsx_workbook([("Products", invalid_product_rows)])
        post_import(port, "Products", invalid_workbook)
        with app.conn() as c:
            assert c.execute("SELECT COUNT(*) FROM products WHERE name IN ('nan stock steel','infinite cost steel')").fetchone()[0] == 0
        post_import(port, "People", workbook_bytes)
        with app.conn() as c:
            person = c.execute("SELECT * FROM people WHERE name='Excel Customer'").fetchone()
            assert person is not None and person["kind"] == "customer"
            assert c.execute("SELECT COUNT(*) FROM people WHERE name='Excel Customer'").fetchone()[0] == 1
        request = urllib.request.Request(f"http://127.0.0.1:{port}/export.xlsx", headers={"Host": f"127.0.0.1:{port}"})
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            assert "spreadsheetml.sheet" in response.headers.get("Content-Type","")
            exported = response.read()
    finally:
        server.shutdown()
        server.server_close()

    round_trip = app.parse_xlsx_workbook(exported)
    # A tiny compressed upload must not be allowed to expand a huge XML entry in memory.
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb,"w",zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml","<workbook/>")
        archive.writestr("xl/worksheets/sheet1.xml","x"*(16*1024*1024+1))
    rejected=False
    try:
        app.parse_xlsx_workbook(bomb.getvalue())
    except ValueError as exc:
        rejected="سقف" in str(exc) or "حجم" in str(exc)
    assert rejected,"oversized expanded XLSX was not rejected"
    # HTTP export contains the full product template (stock is column D).
    assert round_trip["Products"][1][0] == "excel steel", round_trip["Products"][1]
    assert round_trip["Products"][1][3] == "3.0", round_trip["Products"][1]
    assert round_trip["People"][1][0:2] == ["Excel Customer","customer"]
    with app.conn() as c:
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("XLSX IMPORT/EXPORT TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

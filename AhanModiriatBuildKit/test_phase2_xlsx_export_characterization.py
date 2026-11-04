# -*- coding: utf-8 -*-
"""B1 characterization of the legacy XLSX product export contract.

Synthetic fixture only. This test records the existing workbook shape and
quantity-related product fields; it does not define a migration template.
"""
import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_xlsx_export_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def main():
    app.init()
    with app.conn() as c:
        c.execute(
            """INSERT INTO products(
                   name,code,unit,stock,avg_cost,market_price,min_stock,category,
                   purchase_unit,purchase_factor,sale_unit,sale_factor,
                   roll_weight,sheet_area,notes
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "Phase2 export steel", "SKU-EXPORT-01", "kg", 12.5,
                12345, 67890, 2.25, "profile", "bundle", 10.5,
                "piece", 2.5, 125.75, 1.44, "export fixture",
            ),
        )
        c.execute(
            "INSERT INTO people(name,kind,phone,notes) VALUES(?,?,?,?)",
            ("Phase2 Export Customer", "customer", "09120000001", "person fixture"),
        )

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/export.xlsx",
            headers={"Host": f"127.0.0.1:{port}"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            assert "spreadsheetml.sheet" in response.headers.get("Content-Type", "")
            assert 'AhanModiriat-Export.xlsx' in response.headers.get("Content-Disposition", "")
            payload = response.read()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    workbook = app.parse_xlsx_workbook(payload)
    assert list(workbook) == ["Products", "People"], list(workbook)
    assert workbook["Products"][0] == [
        "name", "code", "unit", "stock", "avg_cost", "market_price",
        "min_stock", "category", "purchase_unit", "purchase_factor",
        "sale_unit", "sale_factor", "roll_weight", "sheet_area", "notes",
    ]
    assert workbook["Products"][1] == [
        "Phase2 export steel", "SKU-EXPORT-01", "kg", "12.5",
        "1234.5", "6789", "2.25", "profile", "bundle", "10.5",
        "piece", "2.5", "125.75", "1.44", "export fixture",
    ], workbook["Products"][1]
    assert workbook["People"][0] == ["name", "kind", "phone", "notes"]
    assert workbook["People"][1] == [
        "Phase2 Export Customer", "customer", "09120000001", "person fixture"
    ]
    # The legacy export is a master-data workbook, not a transaction ledger.
    assert not {"Purchases", "Sales", "Returns", "Inventory"}.intersection(workbook)
    print("PHASE 2 XLSX EXPORT CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

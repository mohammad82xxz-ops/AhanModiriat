# -*- coding: utf-8 -*-
"""B1 characterization of the legacy CSV export scope.

Synthetic fixture only. This test records the current export contract; it does
not claim that CSV is a complete accounting or inventory ledger.
"""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_csv_characterization_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def main() -> None:
    app.init()
    with app.conn() as c:
        product_id = c.execute(
            """INSERT INTO products(
                   name,unit,stock,avg_cost,market_price,min_stock,
                   purchase_unit,purchase_factor,sale_unit,sale_factor
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("phase2 CSV steel", "kg", 8, 30, 100, 0, "bundle", 5, "box", 2),
        ).lastrowid
        c.execute(
            """INSERT INTO purchases(
                   date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes
               ) VALUES(?,?,?,?,?,?,?,?)""",
            ("2026-03-01", product_id, 2, 10000, 1000,
             "CSV synthetic supplier", 21000, "purchase must not appear in legacy CSV"),
        )
        c.execute(
            """INSERT INTO sales(
                   date,product_id,qty,unit_price,extra_cost,customer,
                   received,notes,cost_basis,line_total
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("2026-03-02", product_id, 4, 30000, 2000,
             "CSV synthetic customer", 120000, "sale row", 3000, 120000),
        )
        c.execute(
            """INSERT INTO services(date,title,revenue,cost,customer,received,notes)
               VALUES(?,?,?,?,?,?,?)""",
            ("2026-03-03", "CSV synthetic service", 50000, 10000,
             "CSV synthetic customer", 50000, "service row"),
        )
        c.execute(
            """INSERT INTO expenses(date,category,amount,source,business,notes)
               VALUES(?,?,?,?,?,?)""",
            ("2026-03-04", "CSV synthetic expense", 7000,
             "CSV synthetic source", 1, "expense row"),
        )

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/export.csv",
            headers={"Host": f"127.0.0.1:{port}"},
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            assert "text/csv" in response.headers.get("Content-Type", "")
            raw = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    rows = list(csv.reader(io.StringIO(raw.lstrip("\ufeff"))))
    assert rows[0] == ["نوع", "تاریخ", "شرح", "مبلغ/درآمد", "هزینه/اصل", "یادداشت"], rows[0]
    data = rows[1:]
    types = [row[0] for row in data]
    assert types.count("فروش کالا") == 1, types
    assert types.count("خدمت") == 1, types
    assert types.count("پرداخت") == 1, types
    assert not any("خرید" in value or "مرجوع" in value for value in types), types
    assert len(data) == 3, data
    # The six-column CSV schema has no quantity, unit, product code, or
    # inventory balance fields and is therefore not a stock-migration source.
    assert len(rows[0]) == 6
    assert "phase2 CSV steel" in [row[2] for row in data if row[0] == "فروش کالا"]
    assert any(row[2] == "CSV synthetic service" for row in data)
    assert any(row[2] == "CSV synthetic expense" for row in data)
    print("PHASE 2 CSV EXPORT CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

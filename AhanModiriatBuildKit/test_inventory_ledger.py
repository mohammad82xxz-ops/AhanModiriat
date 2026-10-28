# -*- coding: utf-8 -*-
"""Regression tests for stock counts and chronological product movement cards."""
import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_inventory_ledger_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def main():
    app.init()
    with app.conn() as c:
        c.execute("""INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock,
                     purchase_unit,purchase_factor,sale_unit,sale_factor)
                     VALUES('test steel','kg',21,10,15,0,'bundle',10,'kg',1)""")
        pid = c.execute("SELECT id FROM products WHERE name='test steel'").fetchone()[0]
        c.execute("""INSERT INTO purchases(date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes)
                     VALUES('2026-01-01',?,2,100,0,'test supplier',200,'two bundles')""", (pid,))
        c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                     VALUES('2026-01-02',?,4,12,0,'test customer',48,'four kg sold',10)""", (pid,))

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        data = urllib.parse.urlencode({
            "date": "2026-01-03",
            "product_id": str(pid),
            "counted_qty": "7",
            "reason": "شمارش فیزیکی",
            "notes": "اختلاف پس از شمارش",
        }).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/inventory_adjust",
            data=data,
            headers={"Host": f"127.0.0.1:{port}", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            page = response.read().decode("utf-8")
            assert response.status == 200
            assert "انبارگردانی ثبت شد" in page
    finally:
        server.shutdown()
        server.server_close()

    with app.conn() as c:
        p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        assert p["stock"] == 7, p["stock"]
        assert p["avg_cost"] == 10, p["avg_cost"]
        adjustment = c.execute("SELECT * FROM inventory_adjustments WHERE product_id=?", (pid,)).fetchone()
        assert adjustment is not None
        assert adjustment["expected_qty"] == 21
        assert adjustment["counted_qty"] == 7
        assert adjustment["delta_qty"] == -14
        assert adjustment["reason"] == "شمارش فیزیکی"
        ledger = app.product_ledger_page(c, pid)
        assert "خرید" in ledger and "فروش" in ledger and "تعدیل انبار" in ledger
        assert "مانده پس از گردش" in ledger
        assert "25 kg" in ledger and "21 kg" in ledger and "7 kg" in ledger
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("INVENTORY ADJUSTMENT AND MOVEMENT LEDGER TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

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
        with app.conn() as c:
            token_markup = app.submission_token(c, "inventory_adjust")
            submission_token = token_markup.split('value="', 1)[1].split('"', 1)[0]
        data = urllib.parse.urlencode({
            "_submission_token": submission_token,
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
            assert "انبارگردانی و تعدیل موجودی" in page

        # Editing stock from the product form must also create an inventory movement.
        edit_data=urllib.parse.urlencode({
            "product_id":str(pid),"name":"test steel","code":"","unit":"kg","stock":"6",
            "avg_cost":"10","market_price":"15","min_stock":"0","notes":"manual correction",
            "category":"سایر","purchase_unit":"bundle","purchase_factor":"10",
            "sale_unit":"kg","sale_factor":"1","roll_weight":"0","sheet_area":"0"
        }).encode("utf-8")
        edit_request=urllib.request.Request(
            f"http://127.0.0.1:{port}/update_product",data=edit_data,
            headers={"Host":f"127.0.0.1:{port}","Content-Type":"application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(edit_request,timeout=5) as response:
            edit_page=response.read().decode("utf-8")
            assert response.status==200
            assert "کالاها" in edit_page
    finally:
        server.shutdown()
        server.server_close()

    with app.conn() as c:
        p = c.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
        assert p["stock"] == 6, p["stock"]  # 7 after physical count, then 6 via the product editor.
        assert p["avg_cost"] == 100, p["avg_cost"]
        adjustment = c.execute("SELECT * FROM inventory_adjustments WHERE product_id=?", (pid,)).fetchone()
        assert adjustment is not None
        assert adjustment["expected_qty"] == 21
        assert adjustment["counted_qty"] == 7
        assert adjustment["delta_qty"] == -14
        assert adjustment["reason"] == "شمارش فیزیکی"
        edit_adjustment=c.execute("SELECT * FROM inventory_adjustments WHERE product_id=? ORDER BY id DESC LIMIT 1",(pid,)).fetchone()
        assert edit_adjustment["expected_qty"]==7 and edit_adjustment["counted_qty"]==6
        assert edit_adjustment["delta_qty"]==-1
        assert edit_adjustment["reason"]=="اصلاح موجودی از فرم ویرایش کالا"
        assert c.execute("SELECT COUNT(*) FROM inventory_adjustments WHERE product_id=?",(pid,)).fetchone()[0]==2
        assert p["stock"]==6
        ledger = app.product_ledger_page(c, pid)
        assert "خرید" in ledger and "فروش" in ledger and "تعدیل انبار" in ledger
        assert "مانده پس از گردش" in ledger
        assert "25 kg" in ledger and "21 kg" in ledger and "7 kg" in ledger and "6 kg" in ledger
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("INVENTORY ADJUSTMENT AND MOVEMENT LEDGER TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

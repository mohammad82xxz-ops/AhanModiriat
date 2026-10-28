# -*- coding: utf-8 -*-
"""Tests for 30-day sales-based restock recommendations."""
import os
import sys
import tempfile
import datetime
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_purchase_advice_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def main():
    app.init()
    today = datetime.date.today().isoformat()
    with app.conn() as c:
        c.execute("""INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
                     VALUES('fast mover','kg',10,1,2,3)""")
        fast = c.execute("SELECT id FROM products WHERE name='fast mover'").fetchone()[0]
        c.execute("""INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
                     VALUES('low stock no sales','kg',1,1,2,4)""")
        low = c.execute("SELECT id FROM products WHERE name='low stock no sales'").fetchone()[0]
        c.execute("""INSERT INTO sales(date,product_id,qty,unit_price,extra_cost,customer,received,notes,cost_basis)
                     VALUES(?,?,60,2,0,'sample',120,'30-day demand',1)""", (today,fast))
        recs = {r["id"]:r for r in app.compute_purchase_advice(c,30)}
        assert recs[fast]["sold"] == 60
        assert recs[fast]["daily"] == 2
        assert recs[fast]["target"] == 63
        assert recs[fast]["recommend"] == 53
        assert recs[low]["recommend"] == 3
        assert recs[low]["priority"] == 0
        page = app.purchase_advice(c)
        assert "fast mover" in page and "low stock no sales" in page
        assert "مقدار پیشنهادی سفارش" in page
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    print("PURCHASE ADVICE TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

# -*- coding: utf-8 -*-
"""B1 characterization: purchase and sale quantities use different units.

These assertions freeze the current application behavior only. They are not
approval of the accounting policy, precision model, or future dual tracking.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_quantity_characterization_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def post(port: int, path: str, fields: dict[str, object]) -> str:
    payload = dict(fields)
    with app.conn() as c:
        markup = app.submission_token(c, path)
    payload["_submission_token"] = markup.split('value="', 1)[1].split('"', 1)[0]
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/{path}",
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers={
            "Host": f"127.0.0.1:{port}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        assert response.status == 200
        return response.read().decode("utf-8")


def main() -> None:
    app.init()
    with app.conn() as c:
        c.execute(
            """INSERT INTO products(
                   name,unit,stock,avg_cost,market_price,min_stock,
                   purchase_unit,purchase_factor,sale_unit,sale_factor
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            ("phase2 factor characterization", "kg", 0, 0, 100, 0,
             "bundle", 5, "box", 2),
        )
        product_id = c.execute(
            "SELECT id FROM products WHERE name=?",
            ("phase2 factor characterization",),
        ).fetchone()[0]

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        purchase_page = post(port, "add_purchase", {
            "date": "2026-01-01",
            "product_id": product_id,
            "qty": "3",
            "unit_cost": "40",
            "extra_cost": "6",
            "paid": "126",
            "supplier": "B1 fixture supplier",
            "notes": "synthetic purchase-unit characterization",
        })
        assert "خرید" in purchase_page

        with app.conn() as c:
            product = c.execute(
                "SELECT * FROM products WHERE id=?", (product_id,)
            ).fetchone()
            purchase = c.execute(
                "SELECT * FROM purchases WHERE product_id=?", (product_id,)
            ).fetchone()
            assert purchase["qty"] == 3, purchase["qty"]
            assert product["stock"] == 15, product["stock"]
            assert abs(product["avg_cost"] - 84) < 1e-9, product["avg_cost"]
            assert c.execute(
                """SELECT COUNT(*) FROM cash_movements
                   WHERE source_table='purchases' AND source_id=? AND amount=126""",
                (purchase["id"],),
            ).fetchone()[0] == 1

        sale_page = post(port, "add_sale", {
            "date": "2026-01-02",
            "product_id": product_id,
            "qty": "4",
            "unit_price": "30",
            "extra_cost": "0",
            "received": "120",
            "customer": "B1 fixture customer",
            "notes": "synthetic sale-unit characterization",
        })
        assert "فروش" in sale_page

        with app.conn() as c:
            product = c.execute(
                "SELECT * FROM products WHERE id=?", (product_id,)
            ).fetchone()
            purchase = c.execute(
                "SELECT * FROM purchases WHERE product_id=?", (product_id,)
            ).fetchone()
            sale = c.execute(
                "SELECT * FROM sales WHERE product_id=?", (product_id,)
            ).fetchone()

            # Current contract: purchases.qty is purchase units, while
            # sales.qty is stored after conversion to the product base unit.
            assert purchase["qty"] == 3, purchase["qty"]
            assert sale["qty"] == 8, sale["qty"]
            assert sale["unit_price"] == 300, sale["unit_price"]
            assert sale["line_total"] == 1200, sale["line_total"]
            assert abs(sale["cost_basis"] - 84) < 1e-9, sale["cost_basis"]
            assert product["stock"] == 7, product["stock"]
            assert c.execute(
                """SELECT COUNT(*) FROM cash_movements
                   WHERE source_table='sales' AND source_id=? AND amount=120""",
                (sale["id"],),
            ).fetchone()[0] == 1
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        TMP.cleanup()

    print("PHASE 2 QUANTITY CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

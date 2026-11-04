# -*- coding: utf-8 -*-
"""B1 characterization for purchase/sale edit quantity units.

Synthetic SQLite fixture and the real HTTP handlers are used. The assertions
record current route semantics only; they do not approve valuation policy.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_edit_quantity_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def request(port: int, path: str, fields: dict[str, object] | None = None) -> str:
    url = f"http://127.0.0.1:{port}/{path}"
    if fields is None:
        req = urllib.request.Request(url, headers={"Host": f"127.0.0.1:{port}"})
    else:
        payload = dict(fields)
        with app.conn() as c:
            markup = app.submission_token(c, path)
        payload["_submission_token"] = markup.split('value="', 1)[1].split('"', 1)[0]
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(payload).encode("utf-8"),
            headers={
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
    with urllib.request.urlopen(req, timeout=5) as response:
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
            ("phase2 edit fixture", "kg", 10, 200, 3000, 0,
             "bundle", 5, "box", 2),
        )
        product_id = c.execute(
            "SELECT id FROM products WHERE name='phase2 edit fixture'"
        ).fetchone()[0]
        purchase_id = c.execute(
            """INSERT INTO purchases(
                   date,product_id,qty,unit_cost,extra_cost,supplier,paid,notes
               ) VALUES(?,?,?,?,?,?,?,?)""",
            ("2026-02-01", product_id, 2, 1000, 0,
             "edit fixture supplier", 2000, "synthetic source purchase"),
        ).lastrowid
        app.ensure_person(c, "edit fixture supplier", "supplier")
        app.sync_cash_posting(
            c, "purchases", purchase_id, "2026-02-01", 2000,
            "out", "edit fixture supplier", "synthetic source purchase",
        )

    server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        purchase_form = request(port, f"edit_purchase?id={purchase_id}")
        assert "واحد خرید: bundle" in purchase_form
        assert "مقدار خرید" in purchase_form
        assert "مقدار خرید در واحد پایه" not in purchase_form

        request(port, "update_purchase", {
            "record_id": purchase_id,
            "qty": "3",
            "unit_cost": "100",
            "extra_cost": "0",
            "paid": "300",
            "supplier": "edit fixture supplier",
            "notes": "synthetic purchase edit",
        })
        with app.conn() as c:
            purchase = c.execute(
                "SELECT * FROM purchases WHERE id=?", (purchase_id,)
            ).fetchone()
            product = c.execute(
                "SELECT * FROM products WHERE id=?", (product_id,)
            ).fetchone()
            assert purchase["qty"] == 3, purchase["qty"]
            assert product["stock"] == 15, product["stock"]

            sale_id = c.execute(
                """INSERT INTO sales(
                       date,product_id,qty,unit_price,extra_cost,customer,
                       received,notes,cost_basis,line_total
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                ("2026-02-02", product_id, 2, 3000, 0,
                 "edit fixture customer", 6000, "synthetic source sale", 200, 6000),
            ).lastrowid
            app.ensure_person(c, "edit fixture customer", "customer")
            app.sync_cash_posting(
                c, "sales", sale_id, "2026-02-02", 6000,
                "in", "edit fixture customer", "synthetic source sale",
            )
            c.execute("UPDATE products SET stock=13 WHERE id=?", (product_id,))

        sale_form = request(port, f"edit_sale?id={sale_id}")
        assert "مقدار فروش در واحد پایه" in sale_form
        assert "واحد فروش" not in sale_form

        request(port, "update_sale", {
            "record_id": sale_id,
            "qty": "4",
            "unit_price": "300",
            "extra_cost": "0",
            "received": "1200",
            "customer": "edit fixture customer",
            "notes": "synthetic base-unit sale edit",
        })
        with app.conn() as c:
            sale = c.execute(
                "SELECT * FROM sales WHERE id=?", (sale_id,)
            ).fetchone()
            product = c.execute(
                "SELECT * FROM products WHERE id=?", (product_id,)
            ).fetchone()
            # sale_factor=2 is intentionally not applied again by the edit
            # endpoint: sales.qty and the edit form both use base units.
            assert sale["qty"] == 4, sale["qty"]
            assert product["stock"] == 11, product["stock"]
            assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    finally:
        server.shutdown()
        server.server_close()
        TMP.cleanup()

    print("PHASE 2 EDIT QUANTITY CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""B1 characterization of legacy recorded timestamps.

Synthetic SQLite fixture only. This test records the current naive localtime
storage contract; it does not choose a business timezone or reinterpret history.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_timestamp_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402

NAIVE_LOCAL_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def assert_legacy_timestamp(value: object, field: str) -> None:
    assert isinstance(value, str), (field, value)
    assert NAIVE_LOCAL_TIMESTAMP.fullmatch(value), (field, value)
    # The current stored representation has no UTC marker or numeric offset.
    assert not value.endswith("Z"), (field, value)
    assert "+" not in value[10:] and "-" not in value[10:], (field, value)


def main() -> None:
    app.init()
    with app.conn() as c:
        product_id = c.execute(
            """INSERT INTO products(name,unit,stock,avg_cost,market_price,min_stock)
               VALUES(?,?,?,?,?,?)""",
            ("timestamp fixture", "kg", 5, 10, 20, 0),
        ).lastrowid

        # Business document date is an independent date-only field.
        adjustment_id = c.execute(
            """INSERT INTO inventory_adjustments(
                   date,product_id,expected_qty,counted_qty,delta_qty,reason,notes
               ) VALUES(?,?,?,?,?,?,?)""",
            ("2020-01-02", product_id, 5, 4, -1,
             "synthetic timestamp characterization", "fixture only"),
        ).lastrowid

        adjustment = c.execute(
            "SELECT date,created_at,updated_at FROM inventory_adjustments WHERE id=?",
            (adjustment_id,),
        ).fetchone()
        assert adjustment["date"] == "2020-01-02"
        assert_legacy_timestamp(adjustment["created_at"], "inventory_adjustments.created_at")
        assert_legacy_timestamp(adjustment["updated_at"], "inventory_adjustments.updated_at")
        original_created_at = adjustment["created_at"]

        # The existing update trigger refreshes updated_at when callers do not
        # explicitly supply a different timestamp. Do not assume clock precision.
        c.execute(
            "UPDATE inventory_adjustments SET notes=? WHERE id=?",
            ("updated synthetic fixture", adjustment_id),
        )
        updated = c.execute(
            "SELECT date,created_at,updated_at FROM inventory_adjustments WHERE id=?",
            (adjustment_id,),
        ).fetchone()
        assert updated["date"] == "2020-01-02"
        assert updated["created_at"] == original_created_at
        assert_legacy_timestamp(updated["updated_at"], "inventory_adjustments.updated_at after update")

        c.execute(
            "INSERT INTO audit_log(action,details) VALUES(?,?)",
            ("timestamp fixture", "synthetic only"),
        )
        audit_created_at = c.execute(
            "SELECT created_at FROM audit_log WHERE action=?",
            ("timestamp fixture",),
        ).fetchone()["created_at"]
        assert_legacy_timestamp(audit_created_at, "audit_log.created_at")

        for trigger_name in (
            "trg_inventory_adjustments_stamp_insert",
            "trg_inventory_adjustments_stamp_update",
        ):
            trigger = c.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?",
                (trigger_name,),
            ).fetchone()
            assert trigger is not None, trigger_name
            assert "datetime('now','localtime')" in trigger["sql"], trigger["sql"]

        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    print("PHASE 2 TIMESTAMP CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

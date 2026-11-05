# -*- coding: utf-8 -*-
"""Regression test: invalid cash direction must not delete an existing mirror.

The test also verifies rollback when the error escapes a caller transaction.
"""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_invalid_cash_direction_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def main():
    app.init()
    source_table = "phase2_invalid_direction_probe"
    source_id = 9202602

    with app.conn() as c:
        app.sync_cash_posting(
            c, source_table, source_id, "2026-02-03", 1750,
            "in", "Invalid Direction Probe", "positive baseline",
        )
        rows = c.execute(
            "SELECT * FROM cash_movements WHERE source_table=? AND source_id=?",
            (source_table, source_id),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["amount"] == 1750

        raised = False
        try:
            app.sync_cash_posting(
                c, source_table, source_id, "2026-02-03", 800,
                "sideways", "Invalid Direction Probe", "invalid direction",
            )
        except ValueError as exc:
            raised = "جهت گردش نقدی نامعتبر" in str(exc)

        assert raised, "Invalid direction must raise ValueError"
        rows = c.execute(
            "SELECT * FROM cash_movements WHERE source_table=? AND source_id=?",
            (source_table, source_id),
        ).fetchall()

        # Invalid input must be rejected before mutating the previous cash mirror.
        assert len(rows) == 1, [dict(row) for row in rows]
        assert rows[0]["amount"] == 1750, [dict(row) for row in rows]
        assert rows[0]["kind"] == "deposit", [dict(row) for row in rows]
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    # When the same helper error escapes the SQLite connection context,
    # the caller's transaction rolls back and preserves the prior mirror.
    transactional_source_id = 9202603
    with app.conn() as c:
        app.sync_cash_posting(
            c, source_table, transactional_source_id, "2026-02-03", 2100,
            "in", "Invalid Direction Probe", "transaction baseline",
        )

    raised = False
    try:
        with app.conn() as c:
            app.sync_cash_posting(
                c, source_table, transactional_source_id, "2026-02-03", 700,
                "sideways", "Invalid Direction Probe", "transactional invalid direction",
            )
    except ValueError as exc:
        raised = "جهت گردش نقدی نامعتبر" in str(exc)
    assert raised, "Invalid direction must escape the transaction context"

    with app.conn() as c:
        rows = c.execute(
            "SELECT * FROM cash_movements WHERE source_table=? AND source_id=?",
            (source_table, transactional_source_id),
        ).fetchall()
        assert len(rows) == 1, [dict(row) for row in rows]
        assert rows[0]["amount"] == 2100, [dict(row) for row in rows]
        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    print("INVALID CASH DIRECTION CHARACTERIZATION PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

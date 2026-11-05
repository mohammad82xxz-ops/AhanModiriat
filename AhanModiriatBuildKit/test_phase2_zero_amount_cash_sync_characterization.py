# -*- coding: utf-8 -*-
"""Characterize zero/negative cash-sync cleanup using an isolated SQLite database."""
import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_zero_cash_sync_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: E402


def main():
    app.init()
    source_table = "phase2_zero_sync_probe"
    source_id = 9202601

    with app.conn() as c:
        # Establish a positive mirror for a synthetic source key.
        app.sync_cash_posting(
            c, source_table, source_id, "2026-02-03", 1250,
            "in", "Zero Sync Probe", "positive baseline",
        )
        rows = c.execute(
            "SELECT * FROM cash_movements WHERE source_table=? AND source_id=?",
            (source_table, source_id),
        ).fetchall()
        assert len(rows) == 1, [dict(row) for row in rows]
        assert rows[0]["kind"] == "deposit"
        assert rows[0]["amount"] == 1250

        # A zero amount removes the previous mirror and creates no replacement.
        app.sync_cash_posting(
            c, source_table, source_id, "2026-02-03", 0,
            "in", "Zero Sync Probe", "zero update",
        )
        rows = c.execute(
            "SELECT * FROM cash_movements WHERE source_table=? AND source_id=?",
            (source_table, source_id),
        ).fetchall()
        assert rows == [], [dict(row) for row in rows]

        # The same cleanup behavior applies to a negative amount.
        app.sync_cash_posting(
            c, source_table, source_id, "2026-02-03", 900,
            "in", "Zero Sync Probe", "positive again",
        )
        app.sync_cash_posting(
            c, source_table, source_id, "2026-02-03", -1,
            "in", "Zero Sync Probe", "negative update",
        )
        rows = c.execute(
            "SELECT * FROM cash_movements WHERE source_table=? AND source_id=?",
            (source_table, source_id),
        ).fetchall()
        assert rows == [], [dict(row) for row in rows]

        assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []

    print("ZERO/NEGATIVE CASH SYNC CHARACTERIZATION PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

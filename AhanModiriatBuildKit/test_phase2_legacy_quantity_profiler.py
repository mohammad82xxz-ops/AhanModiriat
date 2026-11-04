# -*- coding: utf-8 -*-
"""Synthetic tests for the read-only legacy quantity profiler."""
from __future__ import annotations
import hashlib
import importlib.util
import shutil
import json
import sqlite3
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "phase2_legacy_quantity_profiler", HERE / "phase2_legacy_quantity_profiler.py")
PROFILER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(PROFILER)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ahan_b0_profiler_test_") as tmp:
        root = Path(tmp)
        db = root / "synthetic.sqlite"
        out = root / "report"
        c = sqlite3.connect(db)
        c.execute("PRAGMA foreign_keys=ON")
        c.executescript("""
            CREATE TABLE products(
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, code TEXT DEFAULT '',
                unit TEXT, stock REAL NOT NULL, min_stock REAL NOT NULL,
                purchase_unit TEXT, purchase_factor REAL,
                sale_unit TEXT, sale_factor REAL, roll_weight REAL, sheet_area REAL
            );
            CREATE TABLE purchases(
                id INTEGER PRIMARY KEY, date TEXT, product_id INTEGER REFERENCES products(id),
                qty REAL NOT NULL
            );
            CREATE TABLE sales(
                id INTEGER PRIMARY KEY, date TEXT, product_id INTEGER REFERENCES products(id),
                qty REAL NOT NULL
            );
            CREATE TABLE purchase_returns(
                id INTEGER PRIMARY KEY, date TEXT, product_id INTEGER REFERENCES products(id),
                qty REAL NOT NULL
            );
            CREATE TABLE sales_returns(
                id INTEGER PRIMARY KEY, date TEXT, product_id INTEGER REFERENCES products(id),
                qty REAL NOT NULL
            );
            CREATE TABLE inventory_adjustments(
                id INTEGER PRIMARY KEY, date TEXT, product_id INTEGER REFERENCES products(id),
                delta_qty REAL NOT NULL
            );
            INSERT INTO products VALUES
                (1, 'synthetic steel', 'S-1', 'kg', 13, 1, 'bundle ', 5, 'piece', 2, 0, 0),
                (2, 'invalid factor', 'S-2', 'kg', -1, 0, 'bundle', 0, '', -2, -1, 0);
            INSERT INTO purchases VALUES (1, '2026-01-01', 1, 3);
            INSERT INTO purchases VALUES (2, '2026-01-01', 2, 1);
            INSERT INTO sales VALUES (1, '2026-01-02', 1, 4);
            INSERT INTO purchase_returns VALUES (1, '2026-01-03', 1, 2);
            INSERT INTO sales_returns VALUES (1, '2026-01-04', 1, 1);
            INSERT INTO inventory_adjustments VALUES (1, '2026-01-05', 1, 1);
        """)
        c.commit()
        c.close()
        # Simulate a legacy database with a missing FK declaration/enforcement:
        # the profiler must detect the orphan even when it cannot rely on FK constraints.
        orphan = sqlite3.connect(db)
        orphan.execute("PRAGMA foreign_keys=OFF")
        orphan.execute("INSERT INTO purchases VALUES (99, '2026-01-06', 999, 2)")
        orphan.commit()
        orphan.close()
        before = digest(db)
        read_only = PROFILER.connect_readonly(db)
        try:
            try:
                read_only.execute("UPDATE products SET stock=999 WHERE id=1")
                raise AssertionError("read-only connection unexpectedly accepted UPDATE")
            except sqlite3.OperationalError:
                pass
        finally:
            read_only.close()
        assert digest(db) == before
        result = PROFILER.audit(db, out, "synthetic-fixture")
        assert result["mode"] == "READ_ONLY"
        assert result["source_unchanged"] is True
        assert digest(db) == before
        assert result["product_count"] == 2
        assert result["result"] == "partial"  # orphan also triggers the SQLite FK diagnostic
        assert (out / "checksums.txt").is_file()
        assert (out / "audit_manifest.json").is_file()
        units = (out / "unit_value_counts.csv").read_text(encoding="utf-8-sig")
        assert "bundle " in units  # raw whitespace must remain visible
        reconciliation = (out / "product_reconciliation.csv").read_text(encoding="utf-8-sig")
        # 3*5 - 4 - 2 + 1 + 1 = 11; stock 13 -> arithmetic baseline 2.
        assert "11.0" in reconciliation and "2.0" in reconciliation
        manifest = json.loads((out / "audit_manifest.json").read_text(encoding="utf-8"))
        assert manifest["source_sha256_before"] == manifest["source_sha256_after"]
        exceptions = (out / "exceptions.csv").read_text(encoding="utf-8-sig")
        assert "FACTOR-001" in exceptions and "UNIT-002" in exceptions
        assert "LEDGER-002" in exceptions
        assert "FACTOR-003" in exceptions
        assert "REL-001" in exceptions  # SQLite FK diagnostic
        assert "REL-002" in exceptions  # explicit orphan scan, even without FK enforcement
        assert result["orphan_movement_count"] == 1

        # A bad factor on a product with purchases must not produce a baseline.
        assert "UNRECONCILED" in reconciliation

        # Reusing a non-empty output folder must be refused; stale artifacts cannot be
        # silently mixed into a new audit package.
        stale = root / "stale-report"
        stale.mkdir()
        (stale / "old.txt").write_text("stale", encoding="utf-8")
        try:
            PROFILER.audit(db, stale, "stale-output-fixture")
            raise AssertionError("non-empty output directory unexpectedly accepted")
        except ValueError as error:
            assert "خالی باشد" in str(error)
        assert digest(db) == before

        # Missing one movement table makes the entire movement reconstruction partial.
        incomplete_db = root / "incomplete.sqlite"
        shutil.copy2(db, incomplete_db)
        broken = sqlite3.connect(incomplete_db)
        broken.execute("DROP TABLE inventory_adjustments")
        broken.commit()
        broken.close()
        partial = PROFILER.audit(incomplete_db, root / "partial-report", "incomplete-fixture")
        assert partial["result"] == "partial"
        partial_csv = (root / "partial-report" / "product_reconciliation.csv").read_text(encoding="utf-8-sig")
        assert "UNRECONCILED" in partial_csv
        assert "LEDGER-001" in (root / "partial-report" / "exceptions.csv").read_text(encoding="utf-8-sig")
        print("PHASE 2 READ-ONLY LEGACY PROFILER TESTS PASSED")


if __name__ == "__main__":
    main()

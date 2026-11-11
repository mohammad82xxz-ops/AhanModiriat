# -*- coding: utf-8 -*-
"""SQLite contract tests for the isolated Gate-B valuation persistence adapter."""
import sqlite3
import unittest
from decimal import Decimal

from inventory_valuation import InventoryPosition, apply_purchase, apply_sale
from inventory_valuation_store import ensure_valuation_schema, post_valuation_result


class InventoryValuationStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("""
            CREATE TABLE products(
                id INTEGER PRIMARY KEY,
                stock REAL NOT NULL DEFAULT 0,
                avg_cost INTEGER NOT NULL DEFAULT 0
            )
        """)
        self.db.execute(
            "INSERT INTO products(id, stock, avg_cost) VALUES (1, 10, 100)"
        )
        ensure_valuation_schema(self.db)
        self.db.execute(
            "UPDATE products SET total_value_rial=1000 WHERE id=1"
        )

    def tearDown(self):
        self.db.close()

    def test_event_and_product_projection_commit_together(self):
        before = InventoryPosition(Decimal("10"), 1000)
        result = apply_purchase(before, "2", 500)
        after = post_valuation_result(
            self.db, 1, result, "purchases", 11, "2026-11-11"
        )
        row = self.db.execute(
            "SELECT stock, avg_cost, total_value_rial FROM products WHERE id=1"
        ).fetchone()
        event = self.db.execute(
            "SELECT quantity_delta, value_delta_rial, quantity_after, "
            "total_value_after_rial FROM inventory_valuation_events"
        ).fetchone()
        self.assertEqual(after, InventoryPosition(Decimal("12"), 1500))
        self.assertEqual(row, (12.0, 125, 1500))
        self.assertEqual(event, ("2", 500, "12", 1500))

    def test_duplicate_source_event_rolls_back_cache_change(self):
        result = apply_purchase(InventoryPosition(Decimal("10"), 1000), "1", 100)
        post_valuation_result(
            self.db, 1, result, "purchases", 12, "2026-11-11"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            post_valuation_result(
                self.db, 1, result, "purchases", 12, "2026-11-11"
            )
        self.assertEqual(
            self.db.execute(
                "SELECT stock, total_value_rial FROM products WHERE id=1"
            ).fetchone(),
            (11.0, 1100),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM inventory_valuation_events"
            ).fetchone()[0],
            1,
        )

    def test_stale_snapshot_is_rejected_without_writes(self):
        stale = InventoryPosition(Decimal("9"), 900)
        result = apply_purchase(stale, "1", 100)
        with self.assertRaisesRegex(ValueError, "stale"):
            post_valuation_result(
                self.db, 1, result, "purchases", 13, "2026-11-11"
            )
        self.assertEqual(
            self.db.execute(
                "SELECT stock, total_value_rial FROM products WHERE id=1"
            ).fetchone(),
            (10.0, 1000),
        )
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM inventory_valuation_events"
            ).fetchone()[0],
            0,
        )

    def test_missing_baseline_fails_closed(self):
        self.db.execute(
            "UPDATE products SET total_value_rial=NULL WHERE id=1"
        )
        result = apply_sale(InventoryPosition(Decimal("10"), 1000), "1")
        with self.assertRaisesRegex(ValueError, "baseline"):
            post_valuation_result(
                self.db, 1, result, "sales", 14, "2026-11-11"
            )
        self.assertEqual(
            self.db.execute(
                "SELECT stock FROM products WHERE id=1"
            ).fetchone()[0],
            10.0,
        )

    def test_schema_is_idempotent_and_foreign_keys_are_valid(self):
        ensure_valuation_schema(self.db)
        ensure_valuation_schema(self.db)
        self.assertEqual(
            self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
        )
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

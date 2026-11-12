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
        # Rebuild from the persisted snapshot so the duplicate-source
        # constraint, rather than the stale-snapshot guard, is exercised.
        persisted = self.db.execute(
            "SELECT stock, total_value_rial FROM products WHERE id=1"
        ).fetchone()
        retry_before = InventoryPosition(Decimal(str(persisted[0])), persisted[1])
        retry_result = apply_purchase(retry_before, "1", 100)
        with self.assertRaises(sqlite3.IntegrityError):
            post_valuation_result(
                self.db, 1, retry_result, "purchases", 12, "2026-11-11"
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

    def test_concurrent_compare_and_swap_failure_rolls_back_event(self):
        self.db.execute("""
            CREATE TRIGGER ignore_product_valuation_update
            BEFORE UPDATE OF stock, avg_cost, total_value_rial ON products
            BEGIN
                SELECT RAISE(IGNORE);
            END
        """)
        result = apply_purchase(InventoryPosition(Decimal("10"), 1000), "1", 100)
        with self.assertRaisesRegex(ValueError, "concurrent inventory update"):
            post_valuation_result(
                self.db, 1, result, "purchases", 18, "2026-11-11"
            )
        self.assertEqual(
            self.db.execute(
                "SELECT stock, avg_cost, total_value_rial FROM products WHERE id=1"
            ).fetchone(),
            (10.0, 100, 1000),
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

    def test_quantity_precision_loss_is_rejected_before_writes(self):
        before = InventoryPosition(Decimal("10"), 1000)
        result = apply_purchase(before, "0.123456789012345678901", 100)
        with self.assertRaisesRegex(ValueError, "lose decimal precision"):
            post_valuation_result(
                self.db, 1, result, "purchases", 15, "2026-11-11"
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

    def test_supported_fractional_quantity_round_trips_through_real(self):
        before = InventoryPosition(Decimal("10"), 1000)
        result = apply_purchase(before, "0.125", 100)
        after = post_valuation_result(
            self.db, 1, result, "purchases", 16, "2026-11-11"
        )
        stored = self.db.execute(
            "SELECT stock, total_value_rial FROM products WHERE id=1"
        ).fetchone()
        self.assertEqual(after.quantity, Decimal("10.125"))
        self.assertEqual(Decimal(str(stored[0])), Decimal("10.125"))
        self.assertEqual(stored[1], 1100)

    def test_rial_integer_overflow_is_rejected_before_writes(self):
        before = InventoryPosition(Decimal("10"), 1000)
        result = apply_purchase(before, "1", 9223372036854775807)
        with self.assertRaisesRegex(ValueError, "total_value_rial"):
            post_valuation_result(
                self.db, 1, result, "purchases", 23, "2026-11-11"
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

    def test_event_source_and_effective_date_require_strings(self):
        result = apply_purchase(InventoryPosition(Decimal("10"), 1000), "1", 100)
        for source_table, effective_date in (
            (123, "2026-11-11"),
            ("purchases", 20261111),
        ):
            with self.subTest(source_table=source_table, effective_date=effective_date):
                with self.assertRaisesRegex(ValueError, "source_table|effective_date"):
                    post_valuation_result(
                        self.db, 1, result, source_table, 24,
                        effective_date
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

    def test_source_id_must_be_a_positive_integral_sqlite_integer(self):
        before = InventoryPosition(Decimal("10"), 1000)
        invalid_ids = (
            True,
            False,
            0,
            -1,
            1.5,
            Decimal("1.5"),
            Decimal("NaN"),
            Decimal("Infinity"),
            9223372036854775808,
        )
        for source_id in invalid_ids:
            with self.subTest(source_id=source_id):
                result = apply_purchase(before, "1", 100)
                with self.assertRaisesRegex(ValueError, "source_id"):
                    post_valuation_result(
                        self.db, 1, result, "purchases", source_id, "2026-11-11"
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

    def test_integral_decimal_source_id_is_normalized(self):
        result = apply_purchase(InventoryPosition(Decimal("10"), 1000), "1", 100)
        post_valuation_result(
            self.db, 1, result, "purchases", Decimal("17.0"), "2026-11-11"
        )
        self.assertEqual(
            self.db.execute(
                "SELECT source_id FROM inventory_valuation_events"
            ).fetchone()[0],
            17,
        )

    def test_invalid_metadata_json_is_rejected_before_writes(self):
        before = InventoryPosition(Decimal("10"), 1000)
        invalid_values = (
            "not-json", "[]", '"text"', "null", "42",
            '{"amount": NaN}', '{"amount": Infinity}',
            '{"amount": 1, "amount": 2}',
        )
        for metadata in invalid_values:
            with self.subTest(metadata=metadata):
                result = apply_purchase(before, "1", 100)
                with self.assertRaisesRegex(ValueError, "metadata_json"):
                    post_valuation_result(
                        self.db, 1, result, "purchases", 21,
                        "2026-11-11", metadata_json=metadata
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

    def test_product_id_must_be_positive_integral_sqlite_integer(self):
        before = InventoryPosition(Decimal("10"), 1000)
        for product_id in (True, False, 0, -1, 1.5, Decimal("NaN"),
                           Decimal("Infinity"), 9223372036854775808):
            with self.subTest(product_id=product_id):
                result = apply_purchase(before, "1", 100)
                with self.assertRaisesRegex(ValueError, "product_id"):
                    post_valuation_result(
                        self.db, product_id, result, "purchases", 22,
                        "2026-11-11"
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

    def test_valuation_events_are_append_only(self):
        result = apply_purchase(InventoryPosition(Decimal("10"), 1000), "1", 100)
        post_valuation_result(
            self.db, 1, result, "purchases", 19, "2026-11-11"
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.db.execute(
                "UPDATE inventory_valuation_events SET value_delta_rial=999 "
                "WHERE source_id=19"
            )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.db.execute(
                "DELETE FROM inventory_valuation_events WHERE source_id=19"
            )
        event = self.db.execute(
            "SELECT value_delta_rial FROM inventory_valuation_events WHERE source_id=19"
        ).fetchone()
        self.assertEqual(event, (100,))

    def test_insert_or_replace_cannot_rewrite_valuation_history(self):
        result = apply_purchase(InventoryPosition(Decimal("10"), 1000), "1", 100)
        post_valuation_result(
            self.db, 1, result, "purchases", 26, "2026-11-11"
        )
        with self.assertRaisesRegex(sqlite3.IntegrityError, "append-only"):
            self.db.execute("""
                INSERT OR REPLACE INTO inventory_valuation_events(
                    product_id, source_table, source_id, event_type, effective_date,
                    quantity_delta, value_delta_rial, quantity_after,
                    total_value_after_rial, metadata_json
                ) VALUES (1, 'purchases', 26, 'purchase', '2026-11-12',
                          '999', 999, '999', 999, '{}')
            """)
        event = self.db.execute("""
            SELECT effective_date, quantity_delta, value_delta_rial,
                   quantity_after, total_value_after_rial
              FROM inventory_valuation_events
             WHERE source_table='purchases' AND source_id=26
               AND event_type='purchase'
        """).fetchone()
        self.assertEqual(event, ("2026-11-11", "1", 100, "11", 1100))
        self.assertEqual(
            self.db.execute(
                "SELECT stock, total_value_rial FROM products WHERE id=1"
            ).fetchone(),
            (11.0, 1100),
        )

    def test_schema_setup_requires_foreign_key_enforcement(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute(
                "CREATE TABLE products(id INTEGER PRIMARY KEY, stock REAL, avg_cost INTEGER)"
            )
            with self.assertRaisesRegex(RuntimeError, "foreign-key enforcement"):
                ensure_valuation_schema(connection)
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(products)")
            }
            self.assertNotIn("total_value_rial", columns)
        finally:
            connection.close()

    def test_valuation_write_requires_foreign_key_enforcement(self):
        self.db.commit()
        self.db.execute("PRAGMA foreign_keys=OFF")
        result = apply_purchase(InventoryPosition(Decimal("10"), 1000), "1", 100)
        with self.assertRaisesRegex(RuntimeError, "foreign-key enforcement"):
            post_valuation_result(
                self.db, 1, result, "purchases", 25, "2026-11-11"
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

    def test_schema_is_idempotent_and_foreign_keys_are_valid(self):
        ensure_valuation_schema(self.db)
        ensure_valuation_schema(self.db)
        self.assertEqual(
            self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok"
        )
        self.assertEqual(self.db.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

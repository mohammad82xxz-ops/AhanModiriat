# -*- coding: utf-8 -*-
"""Safety tests for the read-only legacy inventory baseline estimator."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from inventory_valuation_audit import (
    SQLITE_INT_MAX,
    audit_database_file,
    build_legacy_baseline_report,
)


class InventoryValuationAuditTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""
            CREATE TABLE products(
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                stock REAL NOT NULL,
                avg_cost INTEGER NOT NULL
            )
        """)

    def tearDown(self):
        self.db.close()

    def test_report_marks_all_values_as_non_authoritative_estimates(self):
        self.db.executemany(
            "INSERT INTO products(id,name,stock,avg_cost) VALUES(?,?,?,?)",
            [
                (1, "ورق", 2.5, 100),
                (2, "قوطی", 0, 0),
            ],
        )
        before_changes = self.db.total_changes
        report = build_legacy_baseline_report(self.db)

        self.assertTrue(report["read_only"])
        self.assertFalse(report["authoritative"])
        self.assertFalse(report["production_write_performed"])
        self.assertEqual(report["product_count"], 2)
        self.assertEqual(report["eligible_product_count"], 2)
        self.assertEqual(report["exception_product_count"], 0)
        self.assertEqual(
            report["estimated_total_value_rial_for_eligible_products"], 250
        )
        self.assertEqual(self.db.total_changes, before_changes)
        self.assertEqual(self.db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        json.dumps(report, ensure_ascii=False)

    def test_zero_cost_positive_stock_is_excluded_and_reported(self):
        self.db.execute(
            "INSERT INTO products VALUES(1,'کالای بدون بها',5,0)"
        )
        report = build_legacy_baseline_report(self.db)
        product = report["products"][0]

        self.assertFalse(report["complete"])
        self.assertEqual(report["eligible_product_count"], 0)
        self.assertIsNone(product["estimated_total_value_rial"])
        self.assertIn(
            "positive stock with zero average cost requires review",
            product["exceptions"],
        )

    def test_zero_stock_with_nonzero_average_cost_is_reported(self):
        self.db.execute(
            "INSERT INTO products VALUES(1,'مانده صفر',0,120)"
        )
        product = build_legacy_baseline_report(self.db)["products"][0]
        self.assertFalse(product["eligible_for_estimated_baseline"])
        self.assertIn(
            "zero stock with non-zero average cost requires review",
            product["exceptions"],
        )

    def test_negative_stock_and_cost_are_reported_not_silently_fixed(self):
        self.db.execute(
            "INSERT INTO products VALUES(1,'ناسازگار',-2,-10)"
        )
        product = build_legacy_baseline_report(self.db)["products"][0]
        self.assertIsNone(product["estimated_total_value_rial"])
        self.assertIn("negative stock requires manual review", product["exceptions"])
        self.assertIn(
            "negative average cost requires manual review", product["exceptions"]
        )

    def test_non_integer_average_cost_is_not_rounded_into_a_baseline(self):
        self.db.execute(
            "INSERT INTO products VALUES(1,'بهای کسری',2,10.5)"
        )
        product = build_legacy_baseline_report(self.db)["products"][0]
        self.assertIsNone(product["estimated_total_value_rial"])
        self.assertIn(
            "average cost is not an integer rial amount", product["exceptions"]
        )

    def test_signed_64_bit_overflow_is_reported(self):
        self.db.execute(
            "INSERT INTO products VALUES(1,'بزرگ',2,?)",
            (SQLITE_INT_MAX,),
        )
        product = build_legacy_baseline_report(self.db)["products"][0]
        self.assertIsNone(product["estimated_total_value_rial"])
        self.assertIn(
            "estimated value exceeds SQLite signed 64-bit INTEGER",
            product["exceptions"],
        )

    def test_missing_products_table_or_columns_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "products table is required"):
            build_legacy_baseline_report(sqlite3.connect(":memory:"))

        self.db.execute("DROP TABLE products")
        self.db.execute("CREATE TABLE products(id INTEGER PRIMARY KEY, name TEXT)")
        with self.assertRaisesRegex(ValueError, "missing required columns"):
            build_legacy_baseline_report(self.db)

    def test_database_file_is_opened_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "business.db"
            writable = sqlite3.connect(path)
            writable.execute("""
                CREATE TABLE products(
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    stock REAL NOT NULL,
                    avg_cost INTEGER NOT NULL
                )
            """)
            writable.execute("INSERT INTO products VALUES(1,'ورق',3,20)")
            writable.commit()
            before = writable.execute(
                "SELECT id,name,stock,avg_cost FROM products"
            ).fetchall()
            writable.close()

            report = audit_database_file(path)
            self.assertEqual(
                report["estimated_total_value_rial_for_eligible_products"], 60
            )

            readonly = sqlite3.connect(path)
            after = readonly.execute(
                "SELECT id,name,stock,avg_cost FROM products"
            ).fetchall()
            readonly.close()
            self.assertEqual(after, before)

            uri = path.as_uri() + "?mode=ro"
            check = sqlite3.connect(uri, uri=True)
            with self.assertRaises(sqlite3.OperationalError):
                check.execute("INSERT INTO products VALUES(2,'x',1,1)")
            check.close()

    def test_nonexistent_database_file_is_not_created(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.db"
            with self.assertRaises(FileNotFoundError):
                audit_database_file(path)
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

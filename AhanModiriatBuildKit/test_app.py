# -*- coding: utf-8 -*-
"""Focused regression tests for AhanModiriat helpers and isolated data paths."""
import os
import tempfile
import unittest
from pathlib import Path

_TEST_DATA = tempfile.TemporaryDirectory(prefix="ahanmodiriat-test-")
os.environ["AHAN_DATA_DIR"] = _TEST_DATA.name

import app


class AppHelperTests(unittest.TestCase):
    def test_jalali_date_converts_to_iso(self):
        self.assertEqual(app.to_iso_date("1405/07/02"), "2026-09-24")

    def test_persian_digits_are_accepted(self):
        self.assertEqual(app.to_iso_date("۱۴۰۵/۰۷/۰۲"), "2026-09-24")

    def test_gregorian_iso_input_is_accepted(self):
        self.assertEqual(app.to_iso_date("2026-09-24"), "2026-09-24")

    def test_date_display_is_jalali(self):
        self.assertEqual(app.show_date("2026-09-24"), "1405/07/02")

    def test_invalid_date_is_rejected(self):
        with self.assertRaises((ValueError, OverflowError)):
            app.to_iso_date("1405/13/40")

    def test_number_parser_handles_commas(self):
        self.assertEqual(app.num("1,250,000"), 1250000.0)

    def test_database_path_can_be_isolated(self):
        self.assertEqual(Path(app.DATA).resolve(), Path(_TEST_DATA.name).resolve())
        self.assertTrue(Path(app.DATA).is_dir())


if __name__ == "__main__":
    unittest.main()

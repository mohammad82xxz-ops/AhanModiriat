# -*- coding: utf-8 -*-
"""B1 characterization of the existing Jalali/Gregorian date contract.

These tests freeze the current parser behavior; they do not define timezone,
posting-period, backdating, or date-attribution policy.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

TMP = tempfile.TemporaryDirectory(prefix="ahan_phase2_date_characterization_")
os.environ["AHAN_DATA_DIR"] = str(Path(TMP.name) / "appdata")
os.environ["AHAN_NOBROWSER"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app


def expect_invalid(value):
    try:
        app.to_iso_date(value)
    except (ValueError, TypeError):
        return
    raise AssertionError(f"invalid date was accepted: {value!r}")


def main():
    app.init()

    # Jalali/Gregorian boundary and round-trip.
    assert app.to_iso_date("1403/01/01") == "2024-03-20"
    assert app.to_iso_date("1402-01-01") == "2023-03-21"
    assert app.gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)
    assert app.show_date("2024-03-20") == "1403/01/01"

    # Persian and Arabic-Indic digits are normalized identically.
    assert app.to_iso_date("۱۴۰۳/۰۱/۰۱") == "2024-03-20"
    assert app.to_iso_date("١٤٠٣/٠١/٠١") == "2024-03-20"

    # Leap-day handling in both calendars.
    assert app.to_iso_date("1403/12/30") == "2025-03-20"
    assert app.to_iso_date("2024/02/29") == "2024-02-29"
    expect_invalid("1402/12/30")
    expect_invalid("2023/02/29")

    # Invalid month/day, malformed and ambiguous input must not normalize.
    for value in (
        "1403/13/01", "1403/00/01", "1403/07/31",
        "1403/01/00", "1403/01/32", "1403/1", "1403/01/01/extra",
        "not-a-date",
    ):
        expect_invalid(value)

    # Empty input retains the legacy TODAY fallback; it is not a historical
    # timestamp and no timezone interpretation is asserted here.
    assert app.to_iso_date("") == app.TODAY

    print("PHASE 2 DATE CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

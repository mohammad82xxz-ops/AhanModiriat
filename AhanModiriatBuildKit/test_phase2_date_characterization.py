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

    # Leap-day handling across distinct Jalali and Gregorian leap rules.
    assert app.to_iso_date("1403/12/30") == "2025-03-20"
    assert app.to_iso_date("1399/12/30") == "2021-03-20"
    assert app.to_iso_date("2024/02/29") == "2024-02-29"
    assert app.to_iso_date("2000/02/29") == "2000-02-29"
    expect_invalid("1402/12/30")
    expect_invalid("1400/12/30")
    expect_invalid("2023/02/29")
    expect_invalid("1900/02/29")

    # Explicit Gregorian input also accepts ISO separators and normalized digits.
    assert app.to_iso_date(" 2024-02-29 ") == "2024-02-29"
    assert app.to_iso_date("۲۰۲۴-۰۲-۲۹") == "2024-02-29"
    assert app.to_iso_date("١٤٠٣-٠١-٠١") == "2024-03-20"

    # Invalid month/day, malformed and ambiguous input must not normalize.
    for value in (
        "1403/13/01", "1403/00/01", "1403/07/31",
        "1403/01/00", "1403/01/32", "1403/1", "1403/01/01/extra",
        "2024/13/01", "2024/00/01", "2024/04/31",
        "not-a-date",
    ):
        expect_invalid(value)

    # Exhaustive day-by-day round-trip over a deterministic Gregorian span.
    # This checks the conversion pair without imposing timezone/date policy.
    cursor = __import__("datetime").date(1999, 1, 1)
    end = __import__("datetime").date(2026, 1, 1)
    while cursor < end:
        jalali = app.gregorian_to_jalali(cursor.year, cursor.month, cursor.day)
        assert app.jalali_to_gregorian(*jalali) == (
            cursor.year, cursor.month, cursor.day
        ), f"calendar round-trip failed for {cursor.isoformat()} -> {jalali}"
        cursor += __import__("datetime").timedelta(days=1)

    # Empty input retains the legacy TODAY fallback; it is not a historical
    # timestamp and no timezone interpretation is asserted here.
    assert app.to_iso_date("") == app.TODAY

    print("PHASE 2 DATE CHARACTERIZATION TESTS PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        TMP.cleanup()

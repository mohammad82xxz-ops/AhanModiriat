# -*- coding: utf-8 -*-
"""Isolated tests for exact canonical weight conversion; no database is used."""
from decimal import Decimal

from weight_units import MAX_INT64, weight_to_grams, weighted_line_total_rial


def expect_error(error_type, value, unit):
    try:
        weight_to_grams(value, unit)
    except error_type:
        return
    raise AssertionError(f"expected {error_type.__name__} for {value!r} {unit!r}")


def main():
    assert weight_to_grams("0", "g") == 0
    assert weight_to_grams("125", "g") == 125
    assert weight_to_grams("1.25", "kg") == 1250
    assert weight_to_grams(Decimal("0.001"), "kg") == 1
    assert weight_to_grams("1", "t") == 1_000_000
    assert weight_to_grams(" 2.5 ", "KG") == 2500
    assert weight_to_grams(str(MAX_INT64), "g") == MAX_INT64
    assert weight_to_grams("9223372036854775.807", "kg") == MAX_INT64
    assert weight_to_grams(Decimal("0E+100000"), "g") == 0

    for value, unit in [
        ("", "kg"), ("abc", "kg"), ("NaN", "kg"), ("Infinity", "kg"),
        ("-1", "kg"), ("0.0005", "kg"), ("0.0001", "g"),
        ("0.999999999999999999999999999999", "kg"),
        ("1", "ton"), ("1", "کیلوگرم"), ("1", ""),
        (Decimal("1E-100000"), "kg"),
        (True, "kg"), (0.1, "kg"),
    ]:
        expect_error(ValueError, value, unit)

    expect_error(OverflowError, str(MAX_INT64 + 1), "g")
    expect_error(OverflowError, "9223372036854775.808", "kg")
    # Word golden case T02-B-01: 1,000 kg × 40,000 rial/kg.
    assert weighted_line_total_rial(1_000_000, 40_000) == 40_000_000

    # Integer-only ROUND_HALF_UP behavior at half-rial boundaries.
    assert weighted_line_total_rial(1, 499) == 0
    assert weighted_line_total_rial(1, 500) == 1
    assert weighted_line_total_rial(3, 500) == 2
    assert weighted_line_total_rial(0, MAX_INT64) == 0
    assert weighted_line_total_rial(MAX_INT64, 0) == 0

    for weight, price in [(-1, 1000), (1, -1), (True, 1000), (1000, False),
                          (1.0, 1000), (1000, 1.0), ("1000", 1000)]:
        try:
            weighted_line_total_rial(weight, price)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {weight!r} g at {price!r} rial/kg")

    for weight, price in [(MAX_INT64 + 1, 0), (0, MAX_INT64 + 1)]:
        try:
            weighted_line_total_rial(weight, price)
        except OverflowError:
            pass
        else:
            raise AssertionError("expected INTEGER input overflow")

    try:
        weighted_line_total_rial(MAX_INT64, 1001)
    except OverflowError:
        pass
    else:
        raise AssertionError("expected weighted line total overflow")

    # Exhaustive small-domain contract checks for the integer-only line
    # calculation. The independent quotient formula expresses ROUND_HALF_UP
    # for non-negative integer numerators without Decimal or float.
    for weight_g in range(0, 64):
        previous_total = -1
        for price_rial_per_kg in range(0, 128):
            numerator = weight_g * price_rial_per_kg
            expected = (numerator + 500) // 1000
            actual = weighted_line_total_rial(weight_g, price_rial_per_kg)
            assert actual == expected
            assert actual >= previous_total
            previous_total = actual

    for price_rial_per_kg in range(0, 128):
        previous_total = -1
        for weight_g in range(0, 64):
            actual = weighted_line_total_rial(weight_g, price_rial_per_kg)
            assert actual >= previous_total
            previous_total = actual

    # Rounding is per line, not after aggregating unlike document lines.
    assert weighted_line_total_rial(1, 500) + weighted_line_total_rial(1, 500) == 2
    assert weighted_line_total_rial(2, 500) == 1

    print("EXACT WEIGHT UNIT AND PRICING TESTS PASSED")


if __name__ == "__main__":
    main()

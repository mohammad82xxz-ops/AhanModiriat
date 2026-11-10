# -*- coding: utf-8 -*-
"""Isolated tests for exact canonical weight conversion; no database is used."""
from decimal import Decimal, ROUND_UP, localcontext

from weight_units import MAX_INT64, weight_to_grams


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

    # Conversion must not depend on the caller's Decimal precision or rounding.
    # The boundary value has more significant digits than this context permits.
    with localcontext() as context:
        context.prec = 2
        context.rounding = ROUND_UP
        assert weight_to_grams("9223372036854775.807", "kg") == MAX_INT64
        assert weight_to_grams("1.234", "kg") == 1234
        expect_error(ValueError, "0.0005", "kg")

    for value, unit in [
        ("", "kg"), ("abc", "kg"), ("NaN", "kg"), ("Infinity", "kg"),
        ("-1", "kg"), ("0.0005", "kg"), ("0.0001", "g"),
        ("0.999999999999999999999999999999", "kg"),
        ("1e-1000000", "kg"),
        ("1", "ton"), ("1", "کیلوگرم"), ("1", ""),
        (True, "kg"), (0.1, "kg"),
    ]:
        expect_error(ValueError, value, unit)

    expect_error(OverflowError, "1e+1000000", "kg")
    expect_error(OverflowError, str(MAX_INT64 + 1), "g")
    expect_error(OverflowError, "9223372036854775.808", "kg")
    print("EXACT WEIGHT UNIT TESTS PASSED")


if __name__ == "__main__":
    main()

"""Exact, opt-in weight-unit conversion primitives for the accounting rebuild.

Only canonical units are accepted. This module is deliberately not wired into
product or transaction persistence until the owner approves unit taxonomy and
the historical product/unit mapping has been audited.
"""
from decimal import Decimal, InvalidOperation, ROUND_DOWN

MAX_INT64 = 9_223_372_036_854_775_807
_UNIT_TO_GRAM_EXPONENT = {
    "g": 0,
    "kg": 3,
    "t": 6,
}


def weight_to_grams(value, unit):
    """Convert an exact decimal weight to integer grams.

    Args:
        value: Decimal, integer, or decimal text. Binary floats are rejected.
        unit: Canonical unit token: 'g', 'kg', or 't'.

    Raises:
        ValueError: malformed, negative, non-finite, unknown-unit, or
            sub-gram precision input.
        OverflowError: converted grams exceed signed SQLite INTEGER range.
    """
    if isinstance(value, (bool, float)):
        raise ValueError("وزن باید به‌صورت متن ده‌دهی یا Decimal ارسال شود.")
    if not isinstance(value, (str, int, Decimal)):
        raise ValueError("نوع ورودی وزن معتبر نیست.")

    raw = str(value).strip()
    if not raw:
        raise ValueError("وزن خالی است.")
    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError):
        raise ValueError("قالب وزن معتبر نیست.") from None

    if not amount.is_finite():
        raise ValueError("وزن باید عدد متناهی باشد.")
    if amount < 0:
        raise ValueError("وزن منفی مجاز نیست.")

    if not isinstance(unit, str):
        raise ValueError("واحد وزن معتبر نیست.")
    canonical_unit = unit.strip().lower()
    exponent_shift = _UNIT_TO_GRAM_EXPONENT.get(canonical_unit)
    if exponent_shift is None:
        raise ValueError("واحد وزن ناشناخته است؛ فقط g، kg و t پشتیبانی می‌شوند.")

    # Construct the scaled Decimal by shifting its exponent. This is exact
    # and independent of the active Decimal context, even for extreme
    # exponents or inputs with more than 28 significant digits.
    sign, digits, exponent = amount.as_tuple()
    grams = Decimal((sign, digits, exponent + exponent_shift))
    if grams > Decimal(MAX_INT64):
        raise OverflowError("وزن از محدودهٔ INTEGER علامت‌دار SQLite خارج است.")

    integral_grams = grams.to_integral_value(rounding=ROUND_DOWN)
    if grams != integral_grams:
        raise ValueError("وزن با دقت کمتر از یک گرم قابل ذخیره نیست.")
    return int(integral_grams)


def weighted_line_total_rial(weight_g, unit_price_rial_per_kg):
    """Calculate one weight-priced line from integer grams and rial/kg.

    The calculation is exact integer arithmetic. Half-rial ties round upward
    (ROUND_HALF_UP for non-negative amounts), and the result must fit SQLite's
    signed INTEGER range. This function does not aggregate document lines.
    """
    if type(weight_g) is not int or type(unit_price_rial_per_kg) is not int:
        raise ValueError("وزن گرم و قیمت ریال/کیلو باید عدد صحیح باشند.")
    if weight_g < 0:
        raise ValueError("وزن منفی مجاز نیست.")
    if unit_price_rial_per_kg < 0:
        raise ValueError("قیمت منفی مجاز نیست.")
    if weight_g > MAX_INT64 or unit_price_rial_per_kg > MAX_INT64:
        raise OverflowError("وزن یا قیمت از محدودهٔ INTEGER علامت‌دار SQLite خارج است.")

    whole, remainder = divmod(weight_g * unit_price_rial_per_kg, 1000)
    if remainder >= 500:
        whole += 1
    if whole > MAX_INT64:
        raise OverflowError("مبلغ سطر از محدودهٔ INTEGER علامت‌دار SQLite خارج است.")
    return whole

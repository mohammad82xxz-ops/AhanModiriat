"""Exact, opt-in weight-unit conversion primitives for the accounting rebuild.

Only canonical units are accepted. This module is deliberately not wired into
product or transaction persistence until the owner approves unit taxonomy and
the historical product/unit mapping has been audited.
"""
from decimal import Decimal, InvalidOperation, ROUND_DOWN, localcontext

MAX_INT64 = 9_223_372_036_854_775_807
_UNIT_TO_GRAMS = {
    "g": Decimal("1"),
    "kg": Decimal("1000"),
    "t": Decimal("1000000"),
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
    factor = _UNIT_TO_GRAMS.get(canonical_unit)
    if factor is None:
        raise ValueError("واحد وزن ناشناخته است؛ فقط g، kg و t پشتیبانی می‌شوند.")

    if amount > Decimal(MAX_INT64) / factor:
        raise OverflowError("وزن از محدودهٔ INTEGER علامت‌دار SQLite خارج است.")

    # Decimal multiplication obeys the active context. Raise precision to
    # preserve every input digit so a near-integral sub-gram value cannot be
    # rounded into a whole gram by the default 28-digit context.
    with localcontext() as context:
        context.prec = max(context.prec, len(amount.as_tuple().digits) + 4)
        grams = amount * factor

    integral_grams = grams.to_integral_value(rounding=ROUND_DOWN)
    if grams != integral_grams:
        raise ValueError("وزن با دقت کمتر از یک گرم قابل ذخیره نیست.")
    return int(integral_grams)

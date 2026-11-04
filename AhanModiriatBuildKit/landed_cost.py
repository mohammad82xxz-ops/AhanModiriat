"""Deterministic, opt-in allocation of shared freight by verified weight.

This pure helper is intentionally disconnected from SQL, Flask, inventory,
purchases, and production posting until the accounting policy and source data
mapping are approved.
"""

MAX_INT64 = 9_223_372_036_854_775_807


def allocate_shared_cost_by_weight(total_cost_rial, lines):
    """Allocate a non-negative shared cost exactly in proportion to grams.

    Args:
        total_cost_rial: Shared freight amount as an integer rial value.
        lines: Non-empty iterable of (stable_line_id, verified_weight_g).

    Returns:
        A list of dictionaries in input order. Each contains line_id,
        weight_g, and allocated_rial. Allocations sum exactly to total_cost_rial.

    Rounding:
        Uses the largest-remainder method. Initial shares are floored using
        integer arithmetic; remaining rial units go to descending fractional
        remainders, with stable line_id ascending as the tie-breaker.

    Raises:
        ValueError: invalid types, negative values, duplicate/blank IDs, or
            zero aggregate weight.
        OverflowError: any input or final allocation exceeds signed int64.
    """
    if type(total_cost_rial) is not int:
        raise ValueError("هزینهٔ مشترک باید عدد صحیح ریال باشد.")
    if total_cost_rial < 0:
        raise ValueError("هزینهٔ مشترک منفی مجاز نیست.")
    if total_cost_rial > MAX_INT64:
        raise OverflowError("هزینهٔ مشترک از محدودهٔ INTEGER خارج است.")
    try:
        source_lines = list(lines)
    except TypeError:
        raise ValueError("فهرست ردیف‌ها معتبر نیست.") from None
    if not source_lines:
        raise ValueError("برای تسهیم، حداقل یک ردیف لازم است.")

    normalized = []
    seen_ids = set()
    for item in source_lines:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError("هر ردیف باید شامل شناسه و وزن گرم باشد.")
        line_id, weight_g = item
        if not isinstance(line_id, str) or not line_id.strip():
            raise ValueError("شناسهٔ ردیف باید متن غیرخالی باشد.")
        if line_id in seen_ids:
            raise ValueError("شناسهٔ ردیف تکراری مجاز نیست.")
        seen_ids.add(line_id)
        if type(weight_g) is not int:
            raise ValueError("وزن هر ردیف باید عدد صحیح گرم باشد.")
        if weight_g < 0:
            raise ValueError("وزن منفی مجاز نیست.")
        if weight_g > MAX_INT64:
            raise OverflowError("وزن ردیف از محدودهٔ INTEGER خارج است.")
        normalized.append((line_id, weight_g))

    total_weight = sum(weight for _, weight in normalized)
    if total_weight <= 0:
        raise ValueError("مجموع وزن تأییدشده باید بیشتر از صفر باشد.")

    allocations = {}
    remainders = []
    allocated_sum = 0
    for line_id, weight_g in normalized:
        numerator = total_cost_rial * weight_g
        share, remainder = divmod(numerator, total_weight)
        if share > MAX_INT64:
            raise OverflowError("سهم هزینه از محدودهٔ INTEGER خارج است.")
        allocations[line_id] = share
        allocated_sum += share
        remainders.append((remainder, line_id))

    remaining_rial = total_cost_rial - allocated_sum
    # A stable tie-break makes results independent of input/database ordering.
    remainders.sort(key=lambda entry: (-entry[0], entry[1]))
    if remaining_rial > len(remainders):
        raise ArithmeticError("باقیماندهٔ تسهیم از حد ریاضی مورد انتظار بیشتر است.")
    for _, line_id in remainders[:remaining_rial]:
        allocations[line_id] += 1

    result = [
        {
            "line_id": line_id,
            "weight_g": weight_g,
            "allocated_rial": allocations[line_id],
        }
        for line_id, weight_g in normalized
    ]
    if sum(row["allocated_rial"] for row in result) != total_cost_rial:
        raise ArithmeticError("جمع سهم‌های تسهیم با هزینهٔ کل برابر نیست.")
    if any(row["allocated_rial"] < 0 or row["allocated_rial"] > MAX_INT64 for row in result):
        raise OverflowError("سهم نهایی از محدودهٔ INTEGER خارج است.")
    return result

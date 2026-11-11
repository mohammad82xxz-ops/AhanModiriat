# -*- coding: utf-8 -*-
"""Pure, integer-rial inventory valuation primitives.

This module deliberately has no database, UI, or application imports.  The
inventory total is the source of truth; unit average is a rounded projection.
It is a Gate-B candidate and is not wired to the live product cache or schema.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def _decimal_quantity(value, label="quantity"):
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a finite decimal quantity") from None
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError(f"{label} must be greater than zero and finite")
    return quantity


def _nonnegative_rial(value, label="value"):
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a non-negative integer rial amount")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} must be a non-negative integer rial amount") from None
    if not amount.is_finite() or amount < 0 or amount != amount.to_integral_value():
        raise ValueError(f"{label} must be a non-negative integer rial amount")
    return int(amount)


def _round_rial(value):
    return int(Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


@dataclass(frozen=True)
class InventoryPosition:
    """Exact quantity and total book value; average unit cost is derived."""

    quantity: Decimal = Decimal("0")
    total_value_rial: int = 0

    def __post_init__(self):
        try:
            quantity = Decimal(str(self.quantity))
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("quantity must be a finite non-negative decimal") from None
        if not quantity.is_finite() or quantity < 0:
            raise ValueError("quantity must be a finite non-negative decimal")
        value = _nonnegative_rial(self.total_value_rial, "total_value_rial")
        if quantity == 0 and value != 0:
            raise ValueError("zero quantity cannot retain inventory book value")
        object.__setattr__(self, "quantity", quantity)
        object.__setattr__(self, "total_value_rial", value)

    @property
    def avg_cost_rial(self):
        if self.quantity == 0:
            return 0
        return _round_rial(Decimal(self.total_value_rial) / self.quantity)


@dataclass(frozen=True)
class ValuationResult:
    event_type: str
    before: InventoryPosition
    after: InventoryPosition
    quantity_delta: Decimal
    value_delta_rial: int
    event_value_rial: int


def apply_purchase(position, quantity, purchase_value_rial):
    """Add received quantity and its complete landed value."""
    quantity = _decimal_quantity(quantity)
    value = _nonnegative_rial(purchase_value_rial, "purchase_value_rial")
    after = InventoryPosition(
        position.quantity + quantity,
        position.total_value_rial + value,
    )
    return ValuationResult("purchase", position, after, quantity, value, value)


def apply_sale(position, quantity):
    """Remove quantity and allocate current book value, exhausting exact residual on final issue."""
    quantity = _decimal_quantity(quantity)
    if quantity > position.quantity:
        raise ValueError("sale quantity exceeds available inventory")
    if quantity == position.quantity:
        issue_value = position.total_value_rial
    else:
        issue_value = _round_rial(
            Decimal(position.total_value_rial) * quantity / position.quantity
        )
    after = InventoryPosition(
        position.quantity - quantity,
        position.total_value_rial - issue_value,
    )
    return ValuationResult("sale", position, after, -quantity, -issue_value, issue_value)


def apply_purchase_return(position, quantity, historical_return_value_rial):
    """Remove quantity at the already-decided historical purchase return value.

    The caller owns source-purchase linkage and cumulative ancillary-cost
    allocation (DEC-01); this pure engine enforces inventory value invariants.
    """
    quantity = _decimal_quantity(quantity)
    value = _nonnegative_rial(historical_return_value_rial, "historical_return_value_rial")
    if quantity > position.quantity:
        raise ValueError("purchase return quantity exceeds available inventory")
    if value > position.total_value_rial:
        raise ValueError("purchase return value exceeds current inventory book value")
    remaining_quantity = position.quantity - quantity
    remaining_value = position.total_value_rial - value
    if remaining_quantity == 0 and remaining_value != 0:
        raise ValueError("purchase return would leave orphaned inventory value")
    after = InventoryPosition(remaining_quantity, remaining_value)
    return ValuationResult(
        "purchase_return", position, after, -quantity, -value, value
    )


def apply_sales_return(position, quantity, original_sale_cost_value_rial):
    """Restore returned quantity at the immutable cost basis of the original sale."""
    quantity = _decimal_quantity(quantity)
    value = _nonnegative_rial(
        original_sale_cost_value_rial, "original_sale_cost_value_rial"
    )
    after = InventoryPosition(
        position.quantity + quantity,
        position.total_value_rial + value,
    )
    return ValuationResult("sales_return", position, after, quantity, value, value)

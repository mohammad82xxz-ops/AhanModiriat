# -*- coding: utf-8 -*-
"""Golden tests for the pure Gate-B inventory valuation candidate."""
from decimal import Decimal
from dataclasses import FrozenInstanceError
import unittest

from inventory_valuation import (
    InventoryPosition,
    apply_purchase,
    apply_inventory_shortage,
    apply_purchase_return,
    apply_sale,
    apply_sales_return,
)


class InventoryValuationTests(unittest.TestCase):
    def test_average_cost_rounds_values_beyond_decimal_quantize_precision(self):
        position = InventoryPosition(Decimal("0.000000000000000001"), 9223372036854775807)
        self.assertEqual(
            position.avg_cost_rial,
            9223372036854775807000000000000000000,
        )

    def test_weighted_average_uses_exact_total_not_rounded_average(self):
        opening = InventoryPosition(Decimal("10"), 10_000)
        purchased = apply_purchase(opening, "10", 22_000).after
        self.assertEqual(purchased.quantity, Decimal("20"))
        self.assertEqual(purchased.total_value_rial, 32_000)
        self.assertEqual(purchased.avg_cost_rial, 1_600)

        issued = apply_sale(purchased, "5")
        self.assertEqual(issued.event_value_rial, 8_000)
        self.assertEqual(issued.after.quantity, Decimal("15"))
        self.assertEqual(issued.after.total_value_rial, 24_000)
        self.assertEqual(issued.after.avg_cost_rial, 1_600)

        returned = apply_purchase_return(issued.after, "2", 4_400)
        self.assertEqual(returned.after.quantity, Decimal("13"))
        self.assertEqual(returned.after.total_value_rial, 19_600)
        self.assertEqual(returned.after.avg_cost_rial, 1_508)

    def test_consecutive_partial_returns_preserve_one_rial_residual(self):
        # Initial stock: 3 units / 6 rial. Source purchase: 2 units / 2 rial.
        position = InventoryPosition(Decimal("3"), 6)
        position = apply_purchase(position, "2", 2).after
        self.assertEqual((position.quantity, position.total_value_rial),
                         (Decimal("5"), 8))

        first = apply_purchase_return(position, "1", 1)
        second = apply_purchase_return(first.after, "1", 1)
        self.assertEqual(first.after.total_value_rial, 7)
        self.assertEqual(second.after.quantity, Decimal("3"))
        self.assertEqual(second.after.total_value_rial, 6)
        self.assertEqual(second.after.avg_cost_rial, 2)

    def test_acc48_exact_two_consecutive_returns_preserve_total_value(self):
        # Exact ACC-48 fixture: opening stock is 3 units / 6 rial.
        # The source purchase being returned is 2 units / 2 rial, but the
        # current position already includes only 3 units / 6 rial in total.
        # Each partial return removes 1 unit and its 1-rial historical value.
        position = InventoryPosition(Decimal("3"), 6)

        first = apply_purchase_return(position, "1", 1)
        self.assertEqual(first.after.quantity, Decimal("2"))
        self.assertEqual(first.after.total_value_rial, 5)
        self.assertEqual(first.after.avg_cost_rial, 3)

        second = apply_purchase_return(first.after, "1", 1)
        self.assertEqual(second.after.quantity, Decimal("1"))
        self.assertEqual(second.after.total_value_rial, 4)
        self.assertEqual(second.after.avg_cost_rial, 4)

    def test_dec02_shortage_uses_authoritative_total_value_and_half_up_rounding(self):
        position = InventoryPosition(Decimal("3"), 101)

        first = apply_inventory_shortage(position, "1.5")
        self.assertEqual(first.event_type, "inventory_shortage")
        self.assertEqual(first.event_value_rial, 51)  # 50.5 -> 51 (ROUND_HALF_UP)
        self.assertEqual(first.quantity_delta, Decimal("-1.5"))
        self.assertEqual(first.value_delta_rial, -51)
        self.assertEqual(first.after, InventoryPosition(Decimal("1.5"), 50))

        final = apply_inventory_shortage(first.after, "1.5")
        self.assertEqual(final.event_value_rial, 50)  # consume exact residual
        self.assertEqual(final.after, InventoryPosition())

    def test_dec02_shortage_rejects_quantity_above_available_stock(self):
        position = InventoryPosition(Decimal("2"), 100)
        with self.assertRaisesRegex(ValueError, "exceeds available"):
            apply_inventory_shortage(position, "2.01")

    def test_dec02_shortage_rejects_zero_and_non_finite_quantity(self):
        position = InventoryPosition(Decimal("2"), 100)
        for quantity in ("0", "-1", "NaN", "Infinity", "invalid"):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    apply_inventory_shortage(position, quantity)

    def test_final_sale_consumes_exact_remaining_value(self):
        position = InventoryPosition(Decimal("3"), 6)
        first = apply_sale(position, "1")
        second = apply_sale(first.after, "1")
        final = apply_sale(second.after, "1")
        self.assertEqual(
            [first.event_value_rial, second.event_value_rial, final.event_value_rial],
            [2, 2, 2],
        )
        self.assertEqual(final.after, InventoryPosition())

    def test_rounding_can_leave_positive_zero_value_stock(self):
        position = InventoryPosition(Decimal("2"), 1)
        issued = apply_sale(position, "1")
        self.assertEqual(issued.event_value_rial, 1)
        self.assertEqual(issued.after, InventoryPosition(Decimal("1"), 0))
        final = apply_sale(issued.after, "1")
        self.assertEqual(final.after, InventoryPosition())

    def test_sales_return_restores_original_sale_cost_not_current_average(self):
        current = InventoryPosition(Decimal("4"), 9_000)
        returned = apply_sales_return(current, "2", 2_500)
        self.assertEqual(returned.after.quantity, Decimal("6"))
        self.assertEqual(returned.after.total_value_rial, 11_500)
        self.assertEqual(returned.event_value_rial, 2_500)

    def test_purchase_return_cannot_overdraw_quantity_or_value(self):
        position = InventoryPosition(Decimal("2"), 100)
        with self.assertRaisesRegex(ValueError, "quantity exceeds"):
            apply_purchase_return(position, "3", 10)
        with self.assertRaisesRegex(ValueError, "value exceeds"):
            apply_purchase_return(position, "1", 101)

    def test_zero_stock_cannot_retain_value(self):
        position = InventoryPosition(Decimal("2"), 100)
        with self.assertRaisesRegex(ValueError, "orphaned"):
            apply_purchase_return(position, "2", 99)
        exact = apply_purchase_return(position, "2", 100)
        self.assertEqual(exact.after, InventoryPosition())

    def test_invalid_money_and_quantities_are_rejected(self):
        for invalid in ("NaN", "Infinity", "-1", "1.5", True):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    apply_purchase(InventoryPosition(), "1", invalid)
        for invalid in ("0", "-1", "NaN", "Infinity", "not-a-number", True):
            with self.subTest(quantity=invalid):
                with self.assertRaises(ValueError):
                    apply_purchase(InventoryPosition(), invalid, 1)

    def test_positions_are_immutable_and_reject_invalid_state(self):
        position = InventoryPosition(Decimal("1.25"), 100)
        with self.assertRaises(FrozenInstanceError):
            position.total_value_rial = 101
        with self.assertRaisesRegex(ValueError, "zero quantity"):
            InventoryPosition(Decimal("0"), 1)
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            InventoryPosition(Decimal("1"), -1)
        for quantity in (True, False):
            with self.subTest(quantity=quantity):
                with self.assertRaisesRegex(ValueError, "non-negative decimal"):
                    InventoryPosition(quantity, 0)

    def test_boolean_shortage_quantity_is_rejected(self):
        position = InventoryPosition(Decimal("2"), 100)
        for quantity in (True, False):
            with self.subTest(quantity=quantity):
                with self.assertRaisesRegex(ValueError, "finite decimal quantity"):
                    apply_inventory_shortage(position, quantity)

    def test_all_public_quantity_operations_reject_boolean_quantities(self):
        position = InventoryPosition(Decimal("2"), 100)
        operations = (
            ("purchase", lambda quantity: apply_purchase(position, quantity, 10)),
            ("sale", lambda quantity: apply_sale(position, quantity)),
            ("inventory shortage", lambda quantity: apply_inventory_shortage(position, quantity)),
            ("purchase return", lambda quantity: apply_purchase_return(position, quantity, 10)),
            ("sales return", lambda quantity: apply_sales_return(position, quantity, 10)),
        )
        for operation_name, operation in operations:
            for quantity in (True, False):
                with self.subTest(operation=operation_name, quantity=quantity):
                    with self.assertRaisesRegex(ValueError, "finite decimal quantity"):
                        operation(quantity)

    def test_all_public_money_inputs_reject_boolean_values(self):
        position = InventoryPosition(Decimal("2"), 100)
        operations = (
            ("position book value", lambda amount: InventoryPosition(Decimal("1"), amount)),
            ("purchase value", lambda amount: apply_purchase(position, "1", amount)),
            ("purchase return value", lambda amount: apply_purchase_return(position, "1", amount)),
            ("sales return cost", lambda amount: apply_sales_return(position, "1", amount)),
        )
        for operation_name, operation in operations:
            for amount in (True, False):
                with self.subTest(operation=operation_name, amount=amount):
                    with self.assertRaisesRegex(ValueError, "non-negative integer"):
                        operation(amount)


if __name__ == "__main__":
    unittest.main(verbosity=2)

# -*- coding: utf-8 -*-
"""Read-only legacy inventory baseline estimator for Gate B.

The report is deliberately conservative: stock × rounded avg_cost is only a
legacy estimate, never an authoritative historical inventory valuation.
This module performs SELECTs only and opens database files in SQLite read-only
mode when using audit_database_file().
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
import sqlite3

SQLITE_INT_MAX = 9223372036854775807
SQLITE_INT_MIN = -9223372036854775808
REQUIRED_PRODUCT_COLUMNS = {"id", "name", "stock", "avg_cost"}


def _decimal_value(value, label):
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{label} is not a finite numeric value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{label} is not a finite numeric value") from None
    if not result.is_finite():
        raise ValueError(f"{label} is not a finite numeric value")
    return result


def _product_row_report(row):
    product_id = row["id"]
    product_name = str(row["name"] or "")
    exceptions = []
    try:
        quantity = _decimal_value(row["stock"], "stock")
    except ValueError as exc:
        quantity = None
        exceptions.append(str(exc))
    try:
        average = _decimal_value(row["avg_cost"], "avg_cost")
    except ValueError as exc:
        average = None
        exceptions.append(str(exc))

    if quantity is not None and quantity < 0:
        exceptions.append("negative stock requires manual review")
    if average is not None and average < 0:
        exceptions.append("negative average cost requires manual review")
    if average is not None and average != average.to_integral_value():
        exceptions.append("average cost is not an integer rial amount")

    estimated_value = None
    if quantity is not None and average is not None:
        if quantity == 0 and average != 0:
            exceptions.append("zero stock with non-zero average cost requires review")
        elif quantity > 0 and average == 0:
            exceptions.append("positive stock with zero average cost requires review")
        elif quantity >= 0 and average >= 0 and average == average.to_integral_value():
            with localcontext() as context:
                context.prec = 80
                estimated_decimal = (quantity * average).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            if estimated_decimal > SQLITE_INT_MAX:
                exceptions.append("estimated value exceeds SQLite signed 64-bit INTEGER")
            else:
                estimated_value = int(estimated_decimal)

    return {
        "product_id": product_id,
        "product_name": product_name,
        "quantity": format(quantity, "f") if quantity is not None else None,
        "avg_cost_rial": int(average) if average is not None and average == average.to_integral_value() else (
            format(average, "f") if average is not None else None
        ),
        "estimated_total_value_rial": estimated_value,
        "eligible_for_estimated_baseline": not exceptions,
        "exceptions": exceptions,
    }


def build_legacy_baseline_report(connection):
    """Build an in-memory report without changing schema or data."""
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if "products" not in tables:
        raise ValueError("products table is required for a legacy baseline report")

    columns = {
        row[1] for row in connection.execute('PRAGMA table_info("products")')
    }
    missing = sorted(REQUIRED_PRODUCT_COLUMNS - columns)
    if missing:
        raise ValueError("products table is missing required columns: " + ", ".join(missing))

    cursor = connection.execute(
        "SELECT id, name, stock, avg_cost FROM products ORDER BY id"
    )
    column_names = [item[0] for item in cursor.description]
    rows = [
        dict(row) if hasattr(row, "keys") else dict(zip(column_names, row))
        for row in cursor.fetchall()
    ]
    products = [_product_row_report(row) for row in rows]
    eligible = [
        item for item in products if item["eligible_for_estimated_baseline"]
    ]
    exceptions = [
        item for item in products if not item["eligible_for_estimated_baseline"]
    ]
    estimated_total = sum(
        item["estimated_total_value_rial"] for item in eligible
    )

    return {
        "report_type": "legacy_inventory_baseline_estimate",
        "valuation_basis": "stock_times_rounded_avg_cost",
        "authoritative": False,
        "read_only": True,
        "production_write_performed": False,
        "product_count": len(products),
        "eligible_product_count": len(eligible),
        "exception_product_count": len(exceptions),
        "estimated_total_value_rial_for_eligible_products": estimated_total,
        "complete": not exceptions,
        "products": products,
    }


def audit_database_file(database_path):
    """Open an existing SQLite database read-only and return its baseline report."""
    path = Path(database_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError("database file does not exist: " + str(path))
    uri = path.as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        return build_legacy_baseline_report(connection)
    finally:
        connection.close()

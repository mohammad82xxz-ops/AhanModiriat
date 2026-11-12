# -*- coding: utf-8 -*-
"""SQLite persistence adapter for the Gate-B inventory valuation candidate.

This adapter is intentionally not imported by app.py yet.  Its schema helper
must only be called by an explicit, reviewed migration on a disposable copy.
"""
from decimal import Decimal
import json
import sqlite3

from inventory_valuation import InventoryPosition, ValuationResult


def _reject_json_constant(value):
    raise ValueError("non-standard JSON numeric constant: " + value)


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key: " + key)
        result[key] = value
    return result


def _sqlite_real_quantity(quantity):
    """Return a REAL-compatible quantity only when its decimal value round-trips."""
    quantity = Decimal(str(quantity))
    try:
        stored = float(quantity)
    except (OverflowError, ValueError):
        raise ValueError("quantity cannot be represented safely by SQLite REAL") from None
    if not Decimal(str(stored)).is_finite() or Decimal(str(stored)) != quantity:
        raise ValueError("quantity would lose decimal precision in SQLite REAL")
    return stored


def ensure_valuation_schema(connection):
    """Create the event ledger and nullable total-value cache on a test/migration DB."""
    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(products)")
    }
    if not columns:
        raise ValueError("products table is required before valuation schema setup")
    if "total_value_rial" not in columns:
        connection.execute(
            "ALTER TABLE products ADD COLUMN total_value_rial INTEGER"
        )
    connection.execute("""
        CREATE TABLE IF NOT EXISTS inventory_valuation_events (
            id INTEGER PRIMARY KEY,
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            source_table TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            quantity_delta TEXT NOT NULL,
            value_delta_rial INTEGER NOT NULL,
            quantity_after TEXT NOT NULL,
            total_value_after_rial INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            UNIQUE(source_table, source_id, event_type),
            CHECK(value_delta_rial = CAST(value_delta_rial AS INTEGER)),
            CHECK(total_value_after_rial >= 0)
        )
    """)
    connection.execute("""
        CREATE INDEX IF NOT EXISTS ix_inventory_valuation_product_date
        ON inventory_valuation_events(product_id, effective_date, id)
    """)

    # Valuation history is an audit ledger, not an editable cache. Corrections
    # must be represented by compensating events, never UPDATE/DELETE.
    connection.execute("""
        CREATE TRIGGER IF NOT EXISTS inventory_valuation_events_no_update
        BEFORE UPDATE ON inventory_valuation_events
        BEGIN
            SELECT RAISE(ABORT, 'inventory valuation events are append-only');
        END
    """)
    connection.execute("""
        CREATE TRIGGER IF NOT EXISTS inventory_valuation_events_no_delete
        BEFORE DELETE ON inventory_valuation_events
        BEGIN
            SELECT RAISE(ABORT, 'inventory valuation events are append-only');
        END
    """)


def post_valuation_result(
    connection,
    product_id,
    result,
    source_table,
    source_id,
    effective_date,
    metadata_json="{}",
):
    """Persist one pure-engine result and product projection atomically.

    Caller must provide a connection with the application's products schema.
    The SAVEPOINT makes event + cache update all-or-nothing even when called
    inside a larger application transaction. Duplicate source events fail
    closed; this function never silently treats a retry as a successful post.
    """
    if not isinstance(result, ValuationResult):
        raise TypeError("result must be a ValuationResult")
    if isinstance(product_id, bool):
        raise ValueError("product_id must be a positive SQLite integer")
    try:
        product_id_decimal = Decimal(str(product_id))
    except Exception:
        raise ValueError("product_id must be a positive SQLite integer") from None
    if (
        not product_id_decimal.is_finite()
        or product_id_decimal != product_id_decimal.to_integral_value()
        or product_id_decimal <= 0
        or product_id_decimal > 9223372036854775807
    ):
        raise ValueError("product_id must be a positive SQLite integer")
    product_id = int(product_id_decimal)
    if not isinstance(metadata_json, str):
        raise ValueError("metadata_json must be a JSON object string")
    try:
        metadata = json.loads(
            metadata_json,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (TypeError, ValueError):
        raise ValueError("metadata_json must be strict JSON without duplicate keys") from None
    if not isinstance(metadata, dict):
        raise ValueError("metadata_json must encode a JSON object")
    if not source_table or not str(source_table).strip():
        raise ValueError("source_table is required")
    if isinstance(source_id, bool):
        raise ValueError("source_id must be a positive SQLite integer")
    try:
        source_id_decimal = Decimal(str(source_id))
    except Exception:
        raise ValueError("source_id must be a positive SQLite integer") from None
    if (
        not source_id_decimal.is_finite()
        or source_id_decimal != source_id_decimal.to_integral_value()
        or source_id_decimal <= 0
        or source_id_decimal > 9223372036854775807
    ):
        raise ValueError("source_id must be a positive SQLite integer")
    source_id = int(source_id_decimal)
    if not effective_date or not str(effective_date).strip():
        raise ValueError("effective_date is required")

    # products.stock is currently declared REAL. Refuse quantities whose
    # decimal representation cannot survive that legacy projection exactly.
    stored_quantity = _sqlite_real_quantity(result.after.quantity)

    savepoint = "inventory_valuation_post"
    connection.execute("SAVEPOINT " + savepoint)
    try:
        row = connection.execute(
            "SELECT stock, avg_cost, total_value_rial FROM products WHERE id=?",
            (product_id,),
        ).fetchone()
        if row is None:
            raise ValueError("product does not exist")
        current_quantity = Decimal(str(row[0] or 0))
        current_total = row[2]
        if current_total is None:
            raise ValueError("product has no approved valuation baseline")
        current = InventoryPosition(current_quantity, current_total)
        if current != result.before:
            raise ValueError("stale valuation snapshot; reload and recalculate")

        connection.execute("""
            INSERT INTO inventory_valuation_events(
                product_id, source_table, source_id, event_type, effective_date,
                quantity_delta, value_delta_rial, quantity_after,
                total_value_after_rial, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            product_id, str(source_table), int(source_id), result.event_type,
            str(effective_date), str(result.quantity_delta),
            result.value_delta_rial, str(result.after.quantity),
            result.after.total_value_rial, str(metadata_json),
        ))
        cursor = connection.execute("""
            UPDATE products
               SET stock=?, avg_cost=?, total_value_rial=?
             WHERE id=? AND stock=? AND total_value_rial=?
        """, (
            stored_quantity, result.after.avg_cost_rial,
            result.after.total_value_rial, product_id, row[0], current_total,
        ))
        if cursor.rowcount != 1:
            raise ValueError(
                "concurrent inventory update detected; reload and recalculate"
            )
        connection.execute("RELEASE SAVEPOINT " + savepoint)
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT " + savepoint)
        connection.execute("RELEASE SAVEPOINT " + savepoint)
        raise
    return result.after

# -*- coding: utf-8 -*-
"""SQLite persistence adapter for the Gate-B inventory valuation candidate.

This adapter is intentionally not imported by app.py yet.  Its schema helper
must only be called by an explicit, reviewed migration on a disposable copy.
"""
from decimal import Decimal
import sqlite3

from inventory_valuation import InventoryPosition, ValuationResult


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
    if not source_table or not str(source_table).strip():
        raise ValueError("source_table is required")
    if isinstance(source_id, bool) or int(source_id) <= 0:
        raise ValueError("source_id must be a positive integer")
    if not effective_date or not str(effective_date).strip():
        raise ValueError("effective_date is required")

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
        connection.execute("""
            UPDATE products
               SET stock=?, avg_cost=?, total_value_rial=?
             WHERE id=?
        """, (
            float(result.after.quantity), result.after.avg_cost_rial,
            result.after.total_value_rial, product_id,
        ))
        connection.execute("RELEASE SAVEPOINT " + savepoint)
    except Exception:
        connection.execute("ROLLBACK TO SAVEPOINT " + savepoint)
        connection.execute("RELEASE SAVEPOINT " + savepoint)
        raise
    return result.after

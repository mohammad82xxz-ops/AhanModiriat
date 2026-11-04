# -*- coding: utf-8 -*-
"""Independent tests for deterministic weight-based shared-cost allocation."""
from itertools import product

from landed_cost import MAX_INT64, allocate_shared_cost_by_weight


def expect_error(error_type, *args):
    try:
        allocate_shared_cost_by_weight(*args)
    except error_type:
        return
    raise AssertionError(f"expected {error_type.__name__}")


def as_map(rows):
    return {row["line_id"]: row["allocated_rial"] for row in rows}


def main():
    # Word golden case: 1,000 kg + 500 kg, shared freight 3,000,000 rial.
    rows = allocate_shared_cost_by_weight(
        3_000_000, [("A", 1_000_000), ("B", 500_000)]
    )
    assert as_map(rows) == {"A": 2_000_000, "B": 1_000_000}
    assert sum(row["allocated_rial"] for row in rows) == 3_000_000

    # One rial among equal weights: stable ID, not input order, wins the tie.
    first = allocate_shared_cost_by_weight(1, [("B", 1), ("A", 1)])
    second = allocate_shared_cost_by_weight(1, [("A", 1), ("B", 1)])
    assert as_map(first) == {"B": 0, "A": 1}
    assert as_map(second) == {"A": 1, "B": 0}

    # Largest remainder distributes every residual rial deterministically.
    rows = allocate_shared_cost_by_weight(
        2, [("C", 1), ("B", 1), ("A", 1)]
    )
    assert as_map(rows) == {"C": 0, "B": 1, "A": 1}
    assert sum(row["allocated_rial"] for row in rows) == 2

    # Zero-weight rows are retained but receive no shared cost.
    rows = allocate_shared_cost_by_weight(17, [("zero", 0), ("weighted", 5)])
    assert as_map(rows) == {"zero": 0, "weighted": 17}

    # Zero cost is valid when the allocation basis is valid.
    rows = allocate_shared_cost_by_weight(0, [("A", 2), ("B", 3)])
    assert as_map(rows) == {"A": 0, "B": 0}

    # Integer/range/type validation.
    expect_error(ValueError, True, [("A", 1)])
    expect_error(ValueError, -1, [("A", 1)])
    expect_error(OverflowError, MAX_INT64 + 1, [("A", 1)])
    expect_error(ValueError, 10, [])
    expect_error(ValueError, 10, [("A", 0), ("B", 0)])
    expect_error(ValueError, 10, [("A", -1)])
    expect_error(ValueError, 10, [("A", True)])
    expect_error(OverflowError, 10, [("A", MAX_INT64 + 1)])
    expect_error(ValueError, 10, [("", 1)])
    expect_error(ValueError, 10, [("A", 1), ("A", 2)])
    expect_error(ValueError, 10, [("A", 1.0)])
    expect_error(ValueError, 10, [("A", 1), ("B",)])
    expect_error(ValueError, 10, [("A", 1), ("B", 2, 3)])

    # Large but valid values must still allocate exactly with integer math.
    rows = allocate_shared_cost_by_weight(
        MAX_INT64, [("heavy", MAX_INT64), ("light", 1)]
    )
    assert sum(row["allocated_rial"] for row in rows) == MAX_INT64
    assert all(0 <= row["allocated_rial"] <= MAX_INT64 for row in rows)

    # Exhaustive small-domain invariants: conservation, floor/ceil bounds,
    # and allocation invariance under a different input ordering.
    line_ids = ("A", "B", "C")
    for weights in product(range(4), repeat=3):
        if sum(weights) == 0:
            continue
        for cost in range(10):
            source = list(zip(line_ids, weights))
            forward = allocate_shared_cost_by_weight(cost, source)
            reversed_rows = allocate_shared_cost_by_weight(cost, list(reversed(source)))
            forward_map = as_map(forward)
            assert forward_map == as_map(reversed_rows)
            assert sum(forward_map.values()) == cost
            total_weight = sum(weights)
            for line_id, weight_g in source:
                floor_share, remainder = divmod(cost * weight_g, total_weight)
                assert forward_map[line_id] in (floor_share, floor_share + (remainder > 0))
                assert 0 <= forward_map[line_id] <= MAX_INT64

    print("SHARED LANDED-COST ALLOCATION TESTS PASSED")


if __name__ == "__main__":
    main()

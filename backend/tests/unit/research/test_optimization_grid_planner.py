"""Tests for the optimization grid planner."""

from __future__ import annotations

import pytest

from backend.app.research.optimization.grid_planner import (
    GRID_HARD_LIMIT,
    OptimizationGridError,
    expand_candidate_grid,
)


def test_grid_mode_expands_full_cartesian_product() -> None:
    candidates = expand_candidate_grid(
        method="grid",
        parameters=[
            {"field": "risk_per_trade_pct", "values": [0.5, 1.0, 1.5]},
            {"field": "max_positions", "values": [3, 5]},
        ],
        max_candidates=200,
    )
    assert len(candidates) == 6
    fields = {tuple(sorted(c.keys())) for c in candidates}
    assert fields == {("max_positions", "risk_per_trade_pct")}


def test_grid_mode_trims_to_max_candidates_deterministically() -> None:
    candidates = expand_candidate_grid(
        method="grid",
        parameters=[{"field": "fixed_shares", "values": list(range(20))}],
        max_candidates=5,
    )
    assert len(candidates) == 5
    assert [c["fixed_shares"] for c in candidates] == [0, 1, 2, 3, 4]


def test_grid_mode_rejects_above_hard_limit() -> None:
    """Operator-protection: a 6-parameter grid (5⁶ = 15,625) should refuse to run."""
    with pytest.raises(OptimizationGridError):
        expand_candidate_grid(
            method="grid",
            parameters=[{"field": f"f{i}", "values": [1, 2, 3, 4, 5]} for i in range(6)],
            max_candidates=None,
        )


def test_random_mode_samples_uniformly_without_replacement() -> None:
    candidates = expand_candidate_grid(
        method="random",
        parameters=[{"field": "fixed_shares", "values": list(range(50))}],
        max_candidates=10,
        seed=42,
    )
    assert len(candidates) == 10
    seen = {c["fixed_shares"] for c in candidates}
    assert len(seen) == 10  # without replacement


def test_random_mode_returns_full_grid_when_cap_exceeds_size() -> None:
    candidates = expand_candidate_grid(
        method="random",
        parameters=[{"field": "fixed_shares", "values": [1, 2, 3]}],
        max_candidates=100,
        seed=42,
    )
    assert len(candidates) == 3


def test_random_mode_seed_is_reproducible() -> None:
    a = expand_candidate_grid(
        method="random",
        parameters=[{"field": "fixed_shares", "values": list(range(50))}],
        max_candidates=10,
        seed=42,
    )
    b = expand_candidate_grid(
        method="random",
        parameters=[{"field": "fixed_shares", "values": list(range(50))}],
        max_candidates=10,
        seed=42,
    )
    assert a == b


def test_empty_parameters_returns_single_no_op_candidate() -> None:
    candidates = expand_candidate_grid(method="grid", parameters=[])
    assert candidates == [{}]


def test_empty_values_list_raises() -> None:
    with pytest.raises(OptimizationGridError):
        expand_candidate_grid(method="grid", parameters=[{"field": "x", "values": []}])


def test_grid_hard_limit_is_1000() -> None:
    assert GRID_HARD_LIMIT == 1000

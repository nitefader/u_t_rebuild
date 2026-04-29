"""Expand a parameter sweep into the candidate list (grid or random)."""

from __future__ import annotations

import random
from typing import Any, Literal


SearchMethod = Literal["grid", "random"]
DEFAULT_MAX_CANDIDATES = 200
GRID_HARD_LIMIT = 1000  # grid mode rejects above this; random mode is uncapped


class OptimizationGridError(ValueError):
    """Raised when the requested grid cannot generate a valid candidate set."""


def _full_grid(parameters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grid: list[dict[str, Any]] = [{}]
    for parameter in parameters:
        field = str(parameter["field"])
        values = list(parameter["values"])
        if not values:
            raise OptimizationGridError(f"parameter '{field}' has empty values list")
        next_grid: list[dict[str, Any]] = []
        for existing in grid:
            for value in values:
                merged = dict(existing)
                merged[field] = value
                next_grid.append(merged)
        grid = next_grid
    return grid


def expand_candidate_grid(
    *,
    method: SearchMethod,
    parameters: list[dict[str, Any]],
    max_candidates: int | None = DEFAULT_MAX_CANDIDATES,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Return the list of parameter dicts to evaluate.

    ``grid`` mode enumerates the full Cartesian product, then trims to
    ``max_candidates`` deterministically (head-of-list); rejects above
    ``GRID_HARD_LIMIT`` even when uncapped.

    ``random`` mode draws ``max_candidates`` samples uniformly from the
    Cartesian product (with replacement avoided). ``max_candidates=None`` in
    random mode falls back to the default (avoids unbounded runs).
    """
    if not parameters:
        return [{}]
    cap = max_candidates if max_candidates is not None else DEFAULT_MAX_CANDIDATES
    if cap <= 0:
        raise OptimizationGridError("max_candidates must be > 0")

    full = _full_grid(parameters)
    if not full:
        return [{}]

    if method == "grid":
        if len(full) > GRID_HARD_LIMIT and (max_candidates is None or max_candidates > GRID_HARD_LIMIT):
            raise OptimizationGridError(
                f"grid mode rejects candidate counts above {GRID_HARD_LIMIT}; "
                f"use random search or narrow the grid (got {len(full)})"
            )
        return full[:cap]

    if method == "random":
        rng = random.Random(seed)
        if cap >= len(full):
            return full[:]
        # uniform without replacement
        indices = rng.sample(range(len(full)), cap)
        return [full[i] for i in sorted(indices)]

    raise OptimizationGridError(f"unsupported search method '{method}'")

"""Landscape summary stats + heatmap projection for the optimization detail UI."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


HEATMAP_AUTO = "_auto"


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if pct <= 0:
        return ordered[0]
    if pct >= 1:
        return ordered[-1]
    idx = (len(ordered) - 1) * pct
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    weight = idx - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def build_landscape_summary(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Return min/p25/p50/p75/p95/max bands for score, sharpe, max_dd."""
    if not candidates:
        return {}
    scores = [float(c.get("score", 0) or 0) for c in candidates]
    sharpes = [float(c.get("metrics", {}).get("sharpe", 0) or 0) for c in candidates]
    max_dds = [float(c.get("metrics", {}).get("max_drawdown", 0) or 0) for c in candidates]
    return {
        "score_min": round(min(scores), 6),
        "score_p25": round(_percentile(scores, 0.25), 6),
        "score_p50": round(_percentile(scores, 0.5), 6),
        "score_p75": round(_percentile(scores, 0.75), 6),
        "score_p95": round(_percentile(scores, 0.95), 6),
        "score_max": round(max(scores), 6),
        "sharpe_min": round(min(sharpes), 6),
        "sharpe_max": round(max(sharpes), 6),
        "max_dd_best": round(max(max_dds), 6),  # least negative = best
        "max_dd_worst": round(min(max_dds), 6),  # most negative = worst
    }


def runners_up_within(
    *,
    candidates: list[dict[str, Any]],
    threshold_pct: float = 0.05,
) -> list[dict[str, Any]]:
    """Candidates whose score is within ``threshold_pct`` of the winner.

    ``threshold_pct=0.05`` (default) returns rows with score >= 0.95 × winner.
    """
    if not candidates:
        return []
    sorted_candidates = sorted(candidates, key=lambda c: float(c.get("score", 0) or 0), reverse=True)
    winner_score = float(sorted_candidates[0].get("score", 0) or 0)
    if winner_score <= 0:
        # All-or-most negative scores: just return top-N=10
        return sorted_candidates[:10]
    floor = winner_score * (1 - threshold_pct)
    return [c for c in sorted_candidates if float(c.get("score", 0) or 0) >= floor]


def pick_heatmap_dimensions(
    *,
    candidates: list[dict[str, Any]],
    parameter_fields: list[str],
    override: tuple[str, str] | None = None,
) -> tuple[str, str] | None:
    """Auto-pick the two parameters with the highest score variance.

    Returns ``None`` when fewer than 2 parameters are swept (heatmap inapplicable).
    """
    if override is not None:
        a, b = override
        if a in parameter_fields and b in parameter_fields and a != b:
            return (a, b)
    if len(parameter_fields) < 2:
        return None
    if len(parameter_fields) == 2:
        return (parameter_fields[0], parameter_fields[1])

    # For 3+ dimensions, pick the two with the highest best-per-axis variance.
    variances: list[tuple[str, float]] = []
    for field in parameter_fields:
        best_score_per_value: dict[Any, float] = {}
        for candidate in candidates:
            params = candidate.get("parameters", {})
            if field not in params:
                continue
            value = params[field]
            score = float(candidate.get("score", 0) or 0)
            best_score_per_value[value] = max(best_score_per_value.get(value, score), score)
        scores = list(best_score_per_value.values())
        if len(scores) < 2:
            variances.append((field, 0.0))
            continue
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)
        variances.append((field, variance))
    variances.sort(key=lambda item: item[1], reverse=True)
    if variances[0][1] == 0 and variances[1][1] == 0:
        # No discriminating dimensions; fall back to first two.
        return (parameter_fields[0], parameter_fields[1])
    return (variances[0][0], variances[1][0])


def project_heatmap(
    *,
    candidates: list[dict[str, Any]],
    x_field: str,
    y_field: str,
) -> dict[str, Any]:
    """Aggregate candidate scores into a 2D heatmap grid.

    For 3+-dim sweeps where (x, y) is a slice, multiple candidates share the
    same (x, y); the cell value is the **best score** at that (x, y) coord.
    """
    cells: dict[tuple[Any, Any], float] = defaultdict(lambda: float("-inf"))
    x_values: list[Any] = []
    y_values: list[Any] = []
    for candidate in candidates:
        params = candidate.get("parameters", {})
        if x_field not in params or y_field not in params:
            continue
        x = params[x_field]
        y = params[y_field]
        score = float(candidate.get("score", 0) or 0)
        cells[(x, y)] = max(cells[(x, y)], score)
        if x not in x_values:
            x_values.append(x)
        if y not in y_values:
            y_values.append(y)
    x_values.sort(key=lambda v: (isinstance(v, str), v))
    y_values.sort(key=lambda v: (isinstance(v, str), v))
    grid = [
        [
            None if cells.get((x, y), float("-inf")) == float("-inf") else round(cells[(x, y)], 6)
            for x in x_values
        ]
        for y in y_values
    ]
    return {
        "x_field": x_field,
        "y_field": y_field,
        "x_values": x_values,
        "y_values": y_values,
        "cells": grid,
    }

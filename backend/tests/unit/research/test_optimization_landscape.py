"""Tests for optimization landscape stats + heatmap projection."""

from __future__ import annotations

from backend.app.research.optimization.landscape import (
    build_landscape_summary,
    pick_heatmap_dimensions,
    project_heatmap,
    runners_up_within,
)


def _candidate(score: float, sharpe: float, max_dd: float, **params: object) -> dict:
    return {
        "parameters": params,
        "metrics": {"sharpe": sharpe, "max_drawdown": max_dd},
        "score": score,
    }


def test_landscape_summary_returns_percentiles() -> None:
    candidates = [_candidate(score=v / 10, sharpe=v / 10, max_dd=-0.05) for v in range(1, 11)]
    summary = build_landscape_summary(candidates)
    assert summary["score_min"] == 0.1
    assert summary["score_max"] == 1.0
    assert summary["score_p50"] > 0.4 and summary["score_p50"] < 0.7
    assert summary["max_dd_best"] == -0.05  # least negative


def test_runners_up_within_5_pct_default() -> None:
    candidates = [
        _candidate(score=1.0, sharpe=1.0, max_dd=-0.05),
        _candidate(score=0.97, sharpe=0.9, max_dd=-0.06),
        _candidate(score=0.94, sharpe=0.8, max_dd=-0.07),  # 6% off — excluded
        _candidate(score=0.5, sharpe=0.4, max_dd=-0.1),
    ]
    runners = runners_up_within(candidates=candidates, threshold_pct=0.05)
    assert len(runners) == 2  # winner + the 0.97 candidate (within 5%)


def test_pick_heatmap_dimensions_returns_pair_for_2d_sweep() -> None:
    candidates = [_candidate(score=0.5, sharpe=0.5, max_dd=-0.1, a=1, b=2)]
    pair = pick_heatmap_dimensions(candidates=candidates, parameter_fields=["a", "b"])
    assert pair == ("a", "b")


def test_pick_heatmap_dimensions_returns_none_for_1d_sweep() -> None:
    candidates = [_candidate(score=0.5, sharpe=0.5, max_dd=-0.1, a=1)]
    assert pick_heatmap_dimensions(candidates=candidates, parameter_fields=["a"]) is None


def test_pick_heatmap_dimensions_picks_highest_variance_for_3d_sweep() -> None:
    # `a` varies score; `b` and `c` do not. `a` must appear; the second pick
    # is ambiguous so just assert `a` is one of the chosen dimensions.
    candidates = [
        _candidate(score=0.1, sharpe=0.1, max_dd=-0.1, a=1, b=1, c=1),
        _candidate(score=0.9, sharpe=0.9, max_dd=-0.1, a=2, b=1, c=1),
        _candidate(score=0.5, sharpe=0.5, max_dd=-0.1, a=3, b=1, c=1),
    ]
    pair = pick_heatmap_dimensions(candidates=candidates, parameter_fields=["a", "b", "c"])
    assert pair is not None
    assert "a" in pair


def test_project_heatmap_aggregates_by_best_score_per_cell() -> None:
    candidates = [
        _candidate(score=0.5, sharpe=0.5, max_dd=-0.1, x=1, y=10, other=99),
        _candidate(score=0.9, sharpe=0.9, max_dd=-0.1, x=1, y=10, other=42),  # same (x,y), better score
        _candidate(score=0.3, sharpe=0.3, max_dd=-0.1, x=2, y=10),
        _candidate(score=0.7, sharpe=0.7, max_dd=-0.1, x=2, y=20),
    ]
    heatmap = project_heatmap(candidates=candidates, x_field="x", y_field="y")
    assert heatmap["x_field"] == "x"
    assert heatmap["y_field"] == "y"
    assert heatmap["x_values"] == [1, 2]
    assert heatmap["y_values"] == [10, 20]
    # cells[y_index][x_index]; (1,10) cell takes the best score 0.9
    cells = heatmap["cells"]
    assert cells[0][0] == 0.9
    assert cells[0][1] == 0.3
    assert cells[1][0] is None
    assert cells[1][1] == 0.7

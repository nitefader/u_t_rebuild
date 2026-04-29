"""Tests for the walk-forward recommendation aggregator."""

from __future__ import annotations

from backend.app.research.walk_forward.recommendation import build_recommendation
from backend.app.research.walk_forward.selector import score_candidate, select_winner


def _fold(*, fold_index: int, oos_sharpe: float, is_sharpe: float, max_dd: float = -0.1, params: dict | None = None) -> dict:
    return {
        "fold_index": fold_index,
        "is_metrics": {"sharpe": is_sharpe, "max_drawdown": max_dd, "cagr": 0.1, "hit_rate": 0.55},
        "oos_metrics": {"sharpe": oos_sharpe, "max_drawdown": max_dd, "cagr": 0.05, "hit_rate": 0.5},
        "selected_parameters": params or {"risk_per_trade_pct": 0.75},
        "candidate_scores": [
            (params or {"risk_per_trade_pct": 0.75}, {"sharpe": oos_sharpe, "max_drawdown": max_dd, "cagr": 0.05, "hit_rate": 0.5}),
        ],
    }


def test_max_dd_bounded_sharpe_penalises_deep_drawdown() -> None:
    shallow = score_candidate(metrics={"sharpe": 1.0, "max_drawdown": -0.05}, criterion="max_dd_bounded_sharpe")
    deep = score_candidate(metrics={"sharpe": 1.0, "max_drawdown": -0.50}, criterion="max_dd_bounded_sharpe")
    assert shallow.raw_score > deep.raw_score
    assert deep.raw_score > 0  # still positive, just penalised


def test_select_winner_returns_highest_raw_score() -> None:
    candidates = [
        ({"a": 1}, score_candidate(metrics={"sharpe": 0.5, "max_drawdown": -0.1}, criterion="max_dd_bounded_sharpe")),
        ({"a": 2}, score_candidate(metrics={"sharpe": 1.5, "max_drawdown": -0.1}, criterion="max_dd_bounded_sharpe")),
        ({"a": 3}, score_candidate(metrics={"sharpe": 1.0, "max_drawdown": -0.1}, criterion="max_dd_bounded_sharpe")),
    ]
    params, _ = select_winner(candidate_scores=candidates)
    assert params == {"a": 2}


def test_ship_recommended_thresholds() -> None:
    folds = [
        _fold(fold_index=i, oos_sharpe=1.2, is_sharpe=1.4)
        for i in range(5)
    ]
    payload = build_recommendation(fold_results=folds)
    assert payload["recommendation"] == "ship_recommended"
    assert payload["recommended_risk_plan"] is not None
    assert payload["metrics"]["folds_passed_ratio"] == 1.0
    assert payload["metrics"]["oos_sharpe_p25"] >= 0.5


def test_do_not_ship_when_oos_median_negative() -> None:
    folds = [
        _fold(fold_index=i, oos_sharpe=-0.4, is_sharpe=1.5)
        for i in range(5)
    ]
    payload = build_recommendation(fold_results=folds)
    assert payload["recommendation"] == "do_not_ship"
    assert payload["metrics"]["median_oos_sharpe"] < 0


def test_do_not_ship_when_decay_is_huge() -> None:
    folds = [
        _fold(fold_index=i, oos_sharpe=0.4, is_sharpe=2.5)  # decay ≈ 2.1 > 1.5
        for i in range(5)
    ]
    payload = build_recommendation(fold_results=folds)
    assert payload["recommendation"] == "do_not_ship"
    assert payload["metrics"]["is_oos_decay"]["sharpe"] > 1.5


def test_do_not_ship_when_max_dd_breaches_floor() -> None:
    """Max-DD criterion: a strategy with -45% drawdown can't ship even with great Sharpe."""
    folds = [
        _fold(fold_index=i, oos_sharpe=2.0, is_sharpe=2.1, max_dd=-0.45)
        for i in range(5)
    ]
    payload = build_recommendation(fold_results=folds)
    assert payload["recommendation"] == "do_not_ship"
    assert payload["metrics"]["oos_max_dd"] <= -0.40


def test_ship_blocked_by_max_dd_even_with_strong_sharpe() -> None:
    """A strategy with great Sharpe but DD between ship and do_not_ship floors → needs_more_data."""
    folds = [
        _fold(fold_index=i, oos_sharpe=1.5, is_sharpe=1.6, max_dd=-0.30)
        for i in range(5)
    ]
    payload = build_recommendation(fold_results=folds)
    # Sharpe + decay + folds_passed all pass, but max_dd -30% is worse than the
    # ship floor of -25% and better than the do_not_ship ceiling of -40%.
    assert payload["recommendation"] == "needs_more_data"


def test_score_weights_default_is_50_50() -> None:
    folds = [_fold(fold_index=i, oos_sharpe=1.0, is_sharpe=1.1) for i in range(3)]
    payload = build_recommendation(fold_results=folds)
    assert payload["score_weights"] == {"oos_sharpe_p25": 0.5, "stability": 0.5}
    assert payload["default_score_weights"] == {"oos_sharpe_p25": 0.5, "stability": 0.5}


def test_score_weights_overridable_per_run() -> None:
    folds = [_fold(fold_index=i, oos_sharpe=1.0, is_sharpe=1.1) for i in range(3)]
    payload = build_recommendation(
        fold_results=folds,
        score_weights={"oos_sharpe_p25": 0.7, "stability": 0.3},
    )
    assert payload["score_weights"] == {"oos_sharpe_p25": 0.7, "stability": 0.3}
    # Default reference still surfaces so the UI can offer a Reset.
    assert payload["default_score_weights"] == {"oos_sharpe_p25": 0.5, "stability": 0.5}


def test_default_thresholds_are_surfaced_for_reset() -> None:
    folds = [_fold(fold_index=i, oos_sharpe=1.0, is_sharpe=1.1) for i in range(3)]
    payload = build_recommendation(fold_results=folds)
    defaults = payload["default_thresholds"]
    assert defaults["ship_oos_max_dd_min"] == -0.25
    assert defaults["do_not_ship_oos_max_dd_max"] == -0.40


def test_needs_more_data_when_in_between() -> None:
    folds = [
        _fold(fold_index=i, oos_sharpe=0.3, is_sharpe=0.5)
        for i in range(5)
    ]
    payload = build_recommendation(fold_results=folds)
    assert payload["recommendation"] == "needs_more_data"


def test_recommended_candidate_is_marked_in_landscape() -> None:
    # Two candidates: one stable, one volatile. Stable wins.
    folds = [
        {
            "fold_index": i,
            "is_metrics": {"sharpe": 1.0, "max_drawdown": -0.1, "cagr": 0.05, "hit_rate": 0.5},
            "oos_metrics": {"sharpe": 1.0, "max_drawdown": -0.1, "cagr": 0.05, "hit_rate": 0.5},
            "selected_parameters": {"risk_per_trade_pct": 0.5},
            "candidate_scores": [
                ({"risk_per_trade_pct": 0.5}, {"sharpe": 1.0 + (0.1 if i % 2 == 0 else -0.1), "max_drawdown": -0.1, "cagr": 0.05, "hit_rate": 0.5}),
                ({"risk_per_trade_pct": 1.5}, {"sharpe": (3.0 if i == 0 else -1.0), "max_drawdown": -0.3, "cagr": 0.05, "hit_rate": 0.5}),
            ],
        }
        for i in range(4)
    ]
    payload = build_recommendation(fold_results=folds)
    candidates = payload["candidates"]
    recommended = [c for c in candidates if c["recommended"]]
    assert len(recommended) == 1
    # Stable risk_per_trade_pct=0.5 should beat volatile risk_per_trade_pct=1.5.
    assert recommended[0]["parameters"] == {"risk_per_trade_pct": 0.5}

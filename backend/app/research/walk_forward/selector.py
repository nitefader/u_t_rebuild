"""IS scoring + OOS-stability-aware winner selection.

Default selection criterion is ``max_dd_bounded_sharpe`` — Sharpe penalised by
drawdown so high-Sharpe-but-deep-DD candidates lose to steadier ones. Override
via ``criterion`` on ``score_candidate``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


SelectionCriterion = Literal[
    "sharpe",
    "sortino",
    "calmar",
    "expectancy",
    "max_dd_bounded_sharpe",
    "hit_rate",
]


@dataclass(frozen=True)
class SelectorScore:
    """Score breakdown for one candidate parameter set within one IS fold."""

    criterion: str
    raw_score: float
    sharpe: float
    sortino: float
    calmar: float
    expectancy: float
    hit_rate: float
    max_dd: float


def score_candidate(
    *,
    metrics: dict[str, Any],
    criterion: SelectionCriterion = "max_dd_bounded_sharpe",
) -> SelectorScore:
    """Reduce a metrics dict (Backtest's 11 + drawdown) to one score under criterion."""
    sharpe = float(metrics.get("sharpe", 0) or 0)
    sortino = float(metrics.get("sortino", 0) or 0)
    calmar = float(metrics.get("calmar", 0) or 0)
    expectancy = float(metrics.get("expectancy", 0) or 0)
    hit_rate = float(metrics.get("hit_rate", 0) or 0)
    max_dd = float(metrics.get("max_drawdown", 0) or 0)

    if criterion == "sharpe":
        raw = sharpe
    elif criterion == "sortino":
        raw = sortino
    elif criterion == "calmar":
        raw = calmar
    elif criterion == "expectancy":
        raw = expectancy
    elif criterion == "hit_rate":
        raw = hit_rate
    elif criterion == "max_dd_bounded_sharpe":
        # Sharpe scaled by drawdown penalty: 1.0 when DD == 0, asymptotes to 0
        # as |DD| grows. 5% DD ≈ ~0.95, 20% DD ≈ ~0.83, 50% DD ≈ ~0.67.
        dd_penalty = 1.0 / (1.0 + abs(max_dd) * 2.0)
        raw = sharpe * dd_penalty
    else:
        raise ValueError(f"unsupported selection criterion '{criterion}'")

    return SelectorScore(
        criterion=criterion,
        raw_score=round(raw, 6),
        sharpe=round(sharpe, 6),
        sortino=round(sortino, 6),
        calmar=round(calmar, 6),
        expectancy=round(expectancy, 6),
        hit_rate=round(hit_rate, 6),
        max_dd=round(max_dd, 6),
    )


def select_winner(
    *,
    candidate_scores: list[tuple[dict[str, Any], SelectorScore]],
) -> tuple[dict[str, Any], SelectorScore] | None:
    """Pick the highest raw_score among IS candidates. Ties broken by Sharpe then -|max_dd|."""
    if not candidate_scores:
        return None
    return max(
        candidate_scores,
        key=lambda item: (item[1].raw_score, item[1].sharpe, -abs(item[1].max_dd)),
    )

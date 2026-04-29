"""Walk-Forward analysis service.

Doctrine: walk-forward separates fitting from forwarding. Each fold is one
HistoricalReplayEngine.run() against in-sample bars (where parameters are
selected) and one against the immediately-following out-of-sample bars (where
the chosen parameters must live with what they chose). Same spine as Backtest;
no spine changes here, only orchestration + recommendation.

Recommended risk plan defaults (per operator authorization 2026-04-27):
- Selection criterion: ``max_dd_bounded_sharpe`` (penalises high-Sharpe but
  high-drawdown candidates).
- Recommendation score: ``0.6 * oos_sharpe_p25 + 0.4 * stability_score`` so
  consistent-across-folds beats brilliant-in-a-few.
- Ship thresholds: ``oos_sharpe_p25 >= 0.5`` AND ``is_oos_decay.sharpe < 0.5``
  AND ``folds_passed_ratio >= 0.6``. Do-not-ship: ``oos_sharpe_p50 < 0`` OR
  ``is_oos_decay.sharpe > 1.5``. Everything else: needs_more_data.
"""

from .recommendation import RecommendationOutcome, build_recommendation
from .selector import SelectorScore, score_candidate, select_winner
from .service import (
    WalkForwardExecutionRequest,
    WalkForwardExecutionService,
    WalkForwardFoldResult,
)
from .window_planner import FoldWindow, WindowPlannerError, plan_fold_windows

__all__ = [
    "FoldWindow",
    "RecommendationOutcome",
    "SelectorScore",
    "WalkForwardExecutionRequest",
    "WalkForwardExecutionService",
    "WalkForwardFoldResult",
    "WindowPlannerError",
    "build_recommendation",
    "plan_fold_windows",
    "score_candidate",
    "select_winner",
]

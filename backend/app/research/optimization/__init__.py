"""Optimization research service.

Doctrine: hypothesis generation, NOT ship-readiness. Optimization searches a
parameter space on one window and returns the landscape + the winner. The
detail page warns operators loudly that the winner is curve-fit until proven
otherwise — recommended workflow is Backtest → Optimization → Walk-Forward
(validate forward) → Sim Lab → Deploy. Skipping WF is the operator's call;
the UI surfaces the risk.

Same spine as Backtest + Walk-Forward; ``mode = optimization`` on every
emitted RiskDecisionCard.
"""

from .grid_planner import (
    DEFAULT_MAX_CANDIDATES,
    GRID_HARD_LIMIT,
    OptimizationGridError,
    expand_candidate_grid,
)
from .landscape import (
    HEATMAP_AUTO,
    build_landscape_summary,
    pick_heatmap_dimensions,
    project_heatmap,
    runners_up_within,
)
from .service import (
    OptimizationCandidateResult,
    OptimizationExecutionRequest,
    OptimizationExecutionService,
    OptimizationSweepConfig,
    OptimizationSweepParameter,
)

__all__ = [
    "DEFAULT_MAX_CANDIDATES",
    "GRID_HARD_LIMIT",
    "HEATMAP_AUTO",
    "OptimizationCandidateResult",
    "OptimizationExecutionRequest",
    "OptimizationExecutionService",
    "OptimizationGridError",
    "OptimizationSweepConfig",
    "OptimizationSweepParameter",
    "build_landscape_summary",
    "expand_candidate_grid",
    "pick_heatmap_dimensions",
    "project_heatmap",
    "runners_up_within",
]

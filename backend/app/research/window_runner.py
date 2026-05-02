"""Shared per-window runner: drives the unified spine over one bar window.

Walk-Forward and Optimization both compose runs out of "evaluate this
parameter set on this window" calls. This helper isolates the loop:
run HistoricalReplayEngine → compute metrics → return.

Doctrine: same spine as Backtest. ``mode`` is supplied per call so emitted
``RiskDecisionCard`` rows are tagged correctly (``walk_forward`` vs
``optimization`` vs ``backtest``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from backend.app.domain import RiskDecisionMode
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.research.backtests.metrics_service import BacktestMetricsService, CostModel
from backend.app.simulation import HistoricalReplayEngine, SimulationReplayResult


def replay_window(
    *,
    components: ResolvedDeploymentComponents,
    bars: list[NormalizedBar],
    start: datetime,
    end: datetime,
    initial_capital: float,
    cost_model: CostModel,
    timeframe: str,
    mode: RiskDecisionMode,
    risk_decision_sink: Any | None = None,
    metrics_service: BacktestMetricsService | None = None,
    run_id: UUID | None = None,
) -> tuple[SimulationReplayResult, dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Run one HistoricalReplayEngine + metrics pass.

    Returns ``(replay_result, metrics_dict, equity_curve, trade_ledger, risk_decision_card_ids)``.

    Caller is responsible for slicing bars to the window; this helper does not
    re-slice. Caller is also responsible for persisting the SimulationRunEvidence
    when desired; the engine is run with ``evidence_recorder=None`` so per-window
    runs are transient by default.
    """
    engine = HistoricalReplayEngine(
        mode=mode,
        risk_decision_sink=risk_decision_sink,
        evidence_recorder=None,
    )
    replay = engine.run(
        components=components,
        bars=bars,
        start=start,
        end=end,
        initial_cash=initial_capital,
        run_id=run_id or uuid4(),
    )
    service = metrics_service or BacktestMetricsService()
    bundle = service.compute(
        replay=replay,
        cost_model=cost_model,
        initial_capital=initial_capital,
        timeframe=timeframe,
    )
    return (
        replay,
        dict(bundle.metrics),
        list(bundle.equity_curve),
        list(bundle.trade_ledger),
        [str(c.risk_decision_id) for c in engine.risk_decision_cards()],
    )

"""OptimizationExecutionService — sweep parameter space on one window.

Doctrine: hypothesis generation, NOT ship-readiness. The output ALWAYS carries
``needs_walk_forward_validation: true`` and a pre-baked ``follow_up_walk_forward_request``
payload so operators can click "Validate with Walk-Forward" and have the WF
drawer open with the top-K candidates as the WF sweep grid.

Same spine as Backtest + Walk-Forward; ``mode = optimization`` on every emitted
RiskDecisionCard. Each candidate = one HistoricalReplayEngine.run() over the
full window, scored via the same ``score_candidate`` selector WF uses.

RiskPlan belongs to the Account or selected research run. SignalPlan describes
the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan,
and current account or simulated account state to produce a RiskDecisionCard.
No simulated or real order may be created without that RiskDecisionCard.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from backend.app.data_center.ingest_service import (
    HistoricalBarIngestRequest,
    HistoricalBarIngestService,
)
from backend.app.domain import (
    OptimizationRun,
    RiskDecisionMode,
    RiskProfileVersion,
    StrategyVersion,
)
from backend.app.domain._base import JsonDict, utc_now
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.features import NormalizedBar
from backend.app.research.backtests.metrics_service import BacktestMetricsService, CostModel
from backend.app.research.backtests.monte_carlo import MonteCarloAnalyzer, MonteCarloConfig
from backend.app.research.progress import NULL_REPORTER, ProgressReporter, check_cancel
from backend.app.research.risk_plan_lookup import load_risk_profile_from_plan_version
from backend.app.research.walk_forward.selector import (
    SelectionCriterion,
    score_candidate,
)
from backend.app.research.window_runner import build_research_components, replay_window

from .grid_planner import (
    DEFAULT_MAX_CANDIDATES,
    OptimizationGridError,
    SearchMethod,
    expand_candidate_grid,
)
from .landscape import (
    build_landscape_summary,
    pick_heatmap_dimensions,
    project_heatmap,
    runners_up_within,
)


class StrategyVersionLookup(Protocol):
    def get_version(self, strategy_version_id: UUID) -> Any: ...


@dataclass(frozen=True)
class OptimizationSweepParameter:
    field: str
    values: tuple[float, ...]


@dataclass(frozen=True)
class OptimizationSweepConfig:
    base_risk_plan_version_id: UUID | None
    parameters: tuple[OptimizationSweepParameter, ...]


@dataclass(frozen=True)
class OptimizationExecutionRequest:
    strategy_id: UUID
    strategy_version_id: UUID
    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    initial_capital: float
    cost_model: JsonDict
    sweep: OptimizationSweepConfig
    timeframe: str = "1d"
    source: Literal["alpaca", "yahoo"] = "yahoo"
    adjustment_policy: Literal[
        "split_dividend_adjusted", "split_only", "raw"
    ] = "split_dividend_adjusted"
    method: SearchMethod = "grid"
    selection_criterion: SelectionCriterion = "max_dd_bounded_sharpe"
    max_candidates: int | None = DEFAULT_MAX_CANDIDATES
    seed: int = 42
    monte_carlo: MonteCarloConfig | None = None
    runners_up_threshold_pct: float = 0.05
    walk_forward_handoff_top_k: int = 3
    heatmap_dimensions: tuple[str, str] | None = None
    progress_reporter: ProgressReporter | None = None


@dataclass(frozen=True)
class OptimizationCandidateResult:
    candidate_index: int
    parameters: dict[str, Any]
    metrics: dict[str, Any]
    score: float
    trade_count: int
    risk_decision_card_ids: list[str]


def _normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s:
        raise ValueError("optimization universe symbols must be non-empty")
    return s


def _apply_sweep(base: RiskProfileVersion, parameters: dict[str, Any]) -> RiskProfileVersion:
    if not parameters:
        return base
    update: dict[str, Any] = {}
    for key, value in parameters.items():
        if key == "fixed_shares":
            update["fixed_shares"] = int(value) if value is not None else None
            update["sizing_method"] = PositionSizingMethod.FIXED_SHARES
        elif key == "fixed_notional":
            update["fixed_notional"] = float(value)
            update["sizing_method"] = PositionSizingMethod.FIXED_DOLLAR
        elif key == "risk_per_trade_pct":
            update["risk_per_trade_pct"] = float(value)
            update["sizing_method"] = PositionSizingMethod.RISK_PERCENT_EQUITY
        elif key in {
            "max_positions",
            "max_symbol_exposure_pct",
            "max_daily_loss_pct",
            "max_drawdown_pct",
        }:
            update[key] = value
    return base.model_copy(update=update)


class OptimizationExecutionService:
    def __init__(
        self,
        *,
        strategy_lookup: StrategyVersionLookup | None = None,
        ingest_service: HistoricalBarIngestService | None = None,
        store: Any = None,
        risk_decision_sink: Any = None,
    ) -> None:
        self._strategy_lookup = strategy_lookup
        self._ingest_service = ingest_service
        self._store = store
        self._risk_decision_sink = risk_decision_sink

    def create_run(self, request: OptimizationExecutionRequest) -> OptimizationRun:
        symbols = tuple(_normalize_symbol(s) for s in request.symbols)
        if not symbols:
            raise ValueError("optimization run requires at least one symbol")
        if request.initial_capital <= 0:
            raise ValueError("optimization initial capital must be positive")
        if request.start >= request.end:
            raise ValueError("optimization run start must be before end")

        sweep = request.sweep
        parameter_payload = [
            {"field": p.field, "values": list(p.values)} for p in sweep.parameters
        ]
        try:
            candidates_grid = expand_candidate_grid(
                method=request.method,
                parameters=parameter_payload,
                max_candidates=request.max_candidates,
                seed=request.seed,
            )
        except OptimizationGridError as exc:
            raise ValueError(str(exc)) from exc

        # Resolve strategy + base risk plan once
        strategy_payload = self._resolve_strategy_version(request.strategy_version_id)
        base_risk_plan = self._resolve_base_risk_plan(sweep)
        cost_model = CostModel(
            commission_per_trade=float(request.cost_model.get("commission_per_trade", 0.0)),
            slippage_bps=float(request.cost_model.get("slippage_bps", 0.0)),
        )
        metrics_service = BacktestMetricsService()

        # Ingest bars once; every candidate replays the same series.
        bars = self._ingest_full_window(request=request, symbols=symbols)
        if not bars:
            raise ValueError("no bars available for optimization window")

        # Score every candidate
        candidate_results: list[OptimizationCandidateResult] = []
        reporter = request.progress_reporter or NULL_REPORTER
        reporter.update(
            current=0,
            total=len(candidates_grid),
            label="candidates",
            message=f"optimization starting; {len(candidates_grid)} candidate(s)",
        )
        for index, parameters in enumerate(candidates_grid):
            check_cancel(reporter)
            risk_plan = _apply_sweep(base_risk_plan, parameters)
            components = build_research_components(
                strategy_payload=strategy_payload,
                risk_plan=risk_plan,
                symbols=symbols,
                timeframe=request.timeframe,
                name_hint="Optimization",
            )
            _, metrics, _, trade_ledger, card_ids = replay_window(
                components=components,
                bars=list(bars),
                start=request.start,
                end=request.end,
                initial_capital=request.initial_capital,
                cost_model=cost_model,
                timeframe=request.timeframe,
                mode=RiskDecisionMode.OPTIMIZATION,
                risk_decision_sink=self._risk_decision_sink,
                metrics_service=metrics_service,
                run_id=uuid4(),
            )
            score_obj = score_candidate(metrics=metrics, criterion=request.selection_criterion)
            candidate_results.append(
                OptimizationCandidateResult(
                    candidate_index=index,
                    parameters=parameters,
                    metrics=metrics,
                    score=score_obj.raw_score,
                    trade_count=len(trade_ledger),
                    risk_decision_card_ids=card_ids,
                )
            )
            reporter.update(
                current=index + 1,
                total=len(candidates_grid),
                label="candidates",
                message=f"completed candidate {index + 1} of {len(candidates_grid)}",
            )

        # Sort by score descending; pick winner + runners-up + landscape
        sorted_candidates = sorted(candidate_results, key=lambda c: c.score, reverse=True)
        winner = sorted_candidates[0] if sorted_candidates else None
        candidate_payloads = [
            {
                "candidate_index": c.candidate_index,
                "parameters": c.parameters,
                "metrics": c.metrics,
                "score": round(c.score, 6),
                "trade_count": c.trade_count,
                "risk_decision_card_ids": c.risk_decision_card_ids,
                "recommended": False,
            }
            for c in sorted_candidates
        ]
        if candidate_payloads:
            candidate_payloads[0]["recommended"] = True

        landscape_summary = build_landscape_summary(candidate_payloads)
        runners_up = runners_up_within(
            candidates=candidate_payloads,
            threshold_pct=request.runners_up_threshold_pct,
        )
        parameter_fields = [p.field for p in sweep.parameters]
        heatmap_dims = pick_heatmap_dimensions(
            candidates=candidate_payloads,
            parameter_fields=parameter_fields,
            override=request.heatmap_dimensions,
        )
        heatmap = (
            project_heatmap(
                candidates=candidate_payloads,
                x_field=heatmap_dims[0],
                y_field=heatmap_dims[1],
            )
            if heatmap_dims is not None
            else None
        )

        # Monte Carlo on the winner's trade ledger (re-run the winner so we can
        # capture per-trade pnls; cheap relative to the whole sweep)
        monte_carlo_payload: JsonDict | None = None
        if winner is not None and request.monte_carlo and request.monte_carlo.enabled:
            risk_plan = _apply_sweep(base_risk_plan, winner.parameters)
            components = build_research_components(
                strategy_payload=strategy_payload,
                risk_plan=risk_plan,
                symbols=symbols,
                timeframe=request.timeframe,
                name_hint="Optimization MC",
            )
            _, _, _, winner_trades, _ = replay_window(
                components=components,
                bars=list(bars),
                start=request.start,
                end=request.end,
                initial_capital=request.initial_capital,
                cost_model=cost_model,
                timeframe=request.timeframe,
                mode=RiskDecisionMode.OPTIMIZATION,
                risk_decision_sink=None,
                metrics_service=metrics_service,
                run_id=uuid4(),
            )
            mc = MonteCarloAnalyzer().run(
                trade_pnls=[float(t.get("net_pnl", 0)) for t in winner_trades],
                bar_returns=[],
                initial_capital=request.initial_capital,
                config=request.monte_carlo,
            )
            monte_carlo_payload = {
                "method": mc.method,
                "replications": mc.replications,
                "seed": mc.seed,
                "terminal_equity": mc.terminal_equity,
                "sharpe": mc.sharpe,
                "max_drawdown": mc.max_drawdown,
                "final_equity_histogram": mc.final_equity_histogram,
            }

        # Pre-bake the WF handoff request — top-K candidates feed the WF sweep.
        top_k = max(1, request.walk_forward_handoff_top_k)
        top_for_wf = sorted_candidates[:top_k]
        wf_handoff = self._build_wf_handoff(
            request=request,
            symbols=symbols,
            top_candidates=top_for_wf,
            sweep=sweep,
        )

        created_at = utc_now()
        best_parameters = winner.parameters if winner else {}
        best_metrics = winner.metrics if winner else {}
        metrics_payload: JsonDict = {
            "status": "completed",
            "status_updated_at": created_at.isoformat(),
            "method": request.method,
            "selection_criterion": request.selection_criterion,
            "seed": request.seed,
            "max_candidates": request.max_candidates,
            "candidate_count": len(candidate_results),
            "candidates": candidate_payloads,
            "landscape_summary": landscape_summary,
            "runners_up": runners_up,
            "heatmap": heatmap,
            "sweep_grid_shape": {
                "parameters": parameter_fields,
                "shape": [len(p.values) for p in sweep.parameters],
            },
            "monte_carlo": monte_carlo_payload,
            "risk_plan_id": str(base_risk_plan.risk_profile_id),
            "risk_plan_version_id": str(base_risk_plan.id),
            "base_risk_plan_version_id": str(base_risk_plan.id),
            "needs_walk_forward_validation": True,
            "follow_up_walk_forward_request": wf_handoff,
            "best_parameters": best_parameters,
            "best_metrics": best_metrics,
            "winner_score": round(winner.score, 6) if winner else None,
        }

        return OptimizationRun(
            run_id=uuid4(),
            strategy_id=request.strategy_id,
            strategy_version_id=request.strategy_version_id,
            objective=request.selection_criterion,
            candidate_count=len(candidate_results),
            best_parameters=best_parameters,
            best_metrics={**best_metrics, **metrics_payload},
            created_at=created_at,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_strategy_version(self, strategy_version_id: UUID) -> StrategyVersion:
        if self._strategy_lookup is None:
            raise ValueError(
                "OptimizationExecutionService requires a strategy lookup; configure via runtime"
            )
        record = self._strategy_lookup.get_version(strategy_version_id)
        payload = getattr(record, "payload", record)
        if not isinstance(payload, StrategyVersion):
            raise ValueError(f"strategy version {strategy_version_id} is not a StrategyVersion")
        return payload

    def _resolve_base_risk_plan(self, sweep: OptimizationSweepConfig) -> RiskProfileVersion:
        return load_risk_profile_from_plan_version(
            store=self._store,
            risk_plan_version_id=sweep.base_risk_plan_version_id,
            purpose="OptimizationExecutionService",
        )

    def _ingest_full_window(
        self,
        *,
        request: OptimizationExecutionRequest,
        symbols: tuple[str, ...],
    ) -> tuple[NormalizedBar, ...]:
        if self._ingest_service is None:
            raise ValueError(
                "OptimizationExecutionService requires an ingest service; configure via runtime"
            )
        warmup = timedelta(days=14)
        merged: list[NormalizedBar] = []
        for symbol in symbols:
            result = self._ingest_service.ensure_bars(
                HistoricalBarIngestRequest(
                    provider=request.source,
                    symbol=symbol,
                    timeframe=request.timeframe,
                    start=request.start - warmup,
                    end=request.end,
                    adjustment_policy=request.adjustment_policy,
                )
            )
            merged.extend(result.bars)
        merged.sort(key=lambda b: (b.timestamp, b.symbol))
        return tuple(merged)

    @staticmethod
    def _build_wf_handoff(
        *,
        request: OptimizationExecutionRequest,
        symbols: tuple[str, ...],
        top_candidates: list[OptimizationCandidateResult],
        sweep: OptimizationSweepConfig,
    ) -> JsonDict:
        # WF sweep grid = the union of unique values used by the top-K
        # candidates, per-parameter. Narrower than the original optimization
        # grid so WF folds stay tractable.
        narrowed: dict[str, list[Any]] = {}
        for candidate in top_candidates:
            for field, value in candidate.parameters.items():
                bucket = narrowed.setdefault(field, [])
                if value not in bucket:
                    bucket.append(value)
        # Fall back to the full grid if narrowing yielded nothing
        if not narrowed:
            narrowed = {p.field: list(p.values) for p in sweep.parameters}
        return {
            "strategy_id": str(request.strategy_id),
            "strategy_version_id": str(request.strategy_version_id),
            "symbols": list(symbols),
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
            "timeframe": request.timeframe,
            "initial_capital": request.initial_capital,
            "cost_model": dict(request.cost_model),
            "source": request.source,
            "adjustment_policy": request.adjustment_policy,
            "window_mode": "rolling",
            "is_length": {"unit": "days", "value": 180},
            "oos_length": {"unit": "days", "value": 60},
            "step": {"unit": "days", "value": 60},
            "max_folds": 12,
            "selection_criterion": request.selection_criterion,
            "sweep": {
                "enabled": True,
                "base_risk_plan_version_id": (
                    str(sweep.base_risk_plan_version_id) if sweep.base_risk_plan_version_id else None
                ),
                "parameters": [{"field": k, "values": v} for k, v in narrowed.items()],
            },
        }

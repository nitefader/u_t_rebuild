"""WalkForwardExecutionService — orchestrate per-fold IS+OOS replays.

Doctrine: same spine as Backtest. Each fold runs HistoricalReplayEngine twice:
1. IS portion — for each parameter candidate (risk-plan sweep), run a replay,
   score the IS metrics, pick the IS-best candidate using ``selector``.
2. OOS portion — replay the picked candidate against the immediately-following
   bars; record OOS metrics and the trade ledger with full RiskDecisionCard
   lineage.

Aggregated across folds, the recommendation module emits the operator's
ship/no-ship decision and the recommended risk plan.

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
    ExecutionStyleVersion,
    OrderType,
    RiskDecisionMode,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    UniverseSnapshot,
    UniverseSymbol,
    WalkForwardRun,
)
from backend.app.domain._base import JsonDict, utc_now
from backend.app.domain.execution_style import BracketSpec
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.research.backtests.metrics_service import BacktestMetricsService, CostModel
from backend.app.research.backtests.monte_carlo import MonteCarloAnalyzer, MonteCarloConfig
from backend.app.research.risk_plan_lookup import load_risk_profile_from_plan_version
from backend.app.simulation import HistoricalReplayEngine

from backend.app.research.progress import NULL_REPORTER, ProgressReporter, check_cancel

from .recommendation import build_recommendation
from .selector import SelectionCriterion, score_candidate, select_winner
from .window_planner import FoldWindow, LengthSpec, plan_fold_windows


class StrategyVersionLookup(Protocol):
    def get_version(self, strategy_version_id: UUID) -> Any: ...


@dataclass(frozen=True)
class WalkForwardSweepParameter:
    field: Literal[
        "risk_per_trade_pct",
        "fixed_shares",
        "fixed_notional",
        "max_positions",
        "max_symbol_exposure_pct",
        "max_daily_loss_pct",
        "max_drawdown_pct",
    ]
    values: tuple[float, ...]


@dataclass(frozen=True)
class WalkForwardSweepConfig:
    enabled: bool
    base_risk_plan_version_id: UUID | None
    parameters: tuple[WalkForwardSweepParameter, ...]


@dataclass(frozen=True)
class WalkForwardExecutionRequest:
    strategy_id: UUID
    strategy_version_id: UUID
    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    initial_capital: float
    cost_model: JsonDict
    timeframe: str = "1d"
    source: Literal["alpaca", "yahoo"] = "yahoo"
    adjustment_policy: Literal[
        "split_dividend_adjusted", "split_only", "raw"
    ] = "split_dividend_adjusted"
    window_mode: Literal["rolling", "anchored"] = "rolling"
    is_length: LengthSpec = field(default_factory=lambda: LengthSpec(unit="days", value=180))
    oos_length: LengthSpec = field(default_factory=lambda: LengthSpec(unit="days", value=60))
    step: LengthSpec | None = None
    max_folds: int | None = None
    selection_criterion: SelectionCriterion = "max_dd_bounded_sharpe"
    sweep: WalkForwardSweepConfig | None = None
    monte_carlo: MonteCarloConfig | None = None
    fold_pass_threshold_sharpe: float = 0.0
    score_weights: dict[str, float] | None = None
    ship_thresholds: dict[str, float] | None = None
    progress_reporter: ProgressReporter | None = None


@dataclass(frozen=True)
class WalkForwardFoldResult:
    fold_index: int
    is_start: datetime
    is_end: datetime
    oos_start: datetime
    oos_end: datetime
    selected_parameters: dict[str, Any] | None
    is_metrics: dict[str, Any]
    oos_metrics: dict[str, Any]
    candidate_scores: list[tuple[dict[str, Any], dict[str, Any]]]
    oos_trade_ledger: list[dict[str, Any]]
    oos_equity_curve: list[dict[str, Any]]
    risk_decision_card_ids: list[str]


def _normalize_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not s:
        raise ValueError("walk-forward universe symbols must be non-empty")
    return s


class WalkForwardExecutionService:
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

    def create_run(self, request: WalkForwardExecutionRequest) -> WalkForwardRun:
        symbols = tuple(_normalize_symbol(s) for s in request.symbols)
        if not symbols:
            raise ValueError("walk-forward run requires at least one symbol")
        if request.initial_capital <= 0:
            raise ValueError("walk-forward initial capital must be positive")
        if request.start >= request.end:
            raise ValueError("walk-forward run start must be before end")

        # Plan folds first; if the config can't yield any fold, fail fast.
        step = request.step or request.oos_length
        folds = plan_fold_windows(
            window_mode=request.window_mode,
            start=request.start,
            end=request.end,
            is_length=request.is_length,
            oos_length=request.oos_length,
            step=step,
            timeframe=request.timeframe,
            max_folds=request.max_folds,
        )

        # Ingest the full bar window once; folds slice from this set.
        all_bars = self._ingest_full_window(request=request, symbols=symbols)
        bars_by_symbol: dict[str, list[NormalizedBar]] = {}
        for bar in all_bars:
            bars_by_symbol.setdefault(bar.symbol, []).append(bar)

        # Resolve the StrategyVersion + base components once.
        strategy_payload = self._resolve_strategy_version(request.strategy_version_id)
        base_risk_plan = self._resolve_base_risk_plan(request)
        sweep_grid = _expand_sweep_grid(request.sweep)
        if not sweep_grid:
            sweep_grid = [{}]  # one no-op candidate ⇒ pure fixed-RiskPlan forward test

        cost_model = CostModel(
            commission_per_trade=float(request.cost_model.get("commission_per_trade", 0.0)),
            slippage_bps=float(request.cost_model.get("slippage_bps", 0.0)),
        )
        metrics_service = BacktestMetricsService()

        fold_results: list[WalkForwardFoldResult] = []
        all_oos_trades: list[dict[str, Any]] = []
        all_card_ids: list[str] = []

        reporter = request.progress_reporter or NULL_REPORTER
        reporter.update(
            current=0,
            total=len(folds),
            label="folds",
            message=f"walk-forward starting; {len(folds)} fold(s)",
        )

        for fold in folds:
            check_cancel(reporter)
            fold_record = self._run_fold(
                fold=fold,
                strategy_payload=strategy_payload,
                base_risk_plan=base_risk_plan,
                sweep_grid=sweep_grid,
                symbols=symbols,
                bars_by_symbol=bars_by_symbol,
                request=request,
                cost_model=cost_model,
                metrics_service=metrics_service,
                selection_criterion=request.selection_criterion,
            )
            fold_results.append(fold_record)
            all_oos_trades.extend(fold_record.oos_trade_ledger)
            all_card_ids.extend(fold_record.risk_decision_card_ids)
            reporter.update(
                current=fold_record.fold_index + 1,
                total=len(folds),
                label="folds",
                message=f"completed fold {fold_record.fold_index + 1} of {len(folds)}",
            )

        # Build aggregate metrics + recommendation
        recommendation_payload = build_recommendation(
            fold_results=[
                {
                    "fold_index": fr.fold_index,
                    "is_metrics": fr.is_metrics,
                    "oos_metrics": fr.oos_metrics,
                    "selected_parameters": fr.selected_parameters,
                    "candidate_scores": fr.candidate_scores,
                }
                for fr in fold_results
            ],
            folds_passed_threshold_sharpe=request.fold_pass_threshold_sharpe,
            score_weights=request.score_weights,
            ship_thresholds=request.ship_thresholds,
        )

        monte_carlo_payload: JsonDict | None = None
        if request.monte_carlo and request.monte_carlo.enabled:
            mc = MonteCarloAnalyzer().run(
                trade_pnls=[float(t.get("net_pnl", 0)) for t in all_oos_trades],
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

        created_at = utc_now()
        metrics_payload: JsonDict = {
            "status": "completed",
            "status_updated_at": created_at.isoformat(),
            "selection_criterion": request.selection_criterion,
            "window_mode": request.window_mode,
            "fold_count": len(fold_results),
            "folds": [
                {
                    "fold_index": fr.fold_index,
                    "is_start": fr.is_start.isoformat(),
                    "is_end": fr.is_end.isoformat(),
                    "oos_start": fr.oos_start.isoformat(),
                    "oos_end": fr.oos_end.isoformat(),
                    "selected_parameters": fr.selected_parameters,
                    "is_metrics": fr.is_metrics,
                    "oos_metrics": fr.oos_metrics,
                }
                for fr in fold_results
            ],
            "recommended_risk_plan": recommendation_payload["recommended_risk_plan"],
            "recommendation": recommendation_payload["recommendation"],
            "thresholds_applied": recommendation_payload["thresholds_applied"],
            "default_thresholds": recommendation_payload.get("default_thresholds"),
            "score_weights": recommendation_payload.get("score_weights"),
            "default_score_weights": recommendation_payload.get("default_score_weights"),
            "candidates": recommendation_payload["candidates"],
            "monte_carlo": monte_carlo_payload,
            "risk_plan_id": str(base_risk_plan.risk_profile_id),
            "risk_plan_version_id": str(base_risk_plan.id),
            "base_risk_plan_version_id": str(base_risk_plan.id),
            "risk_decision_card_ids": all_card_ids,
            "oos_trade_count": len(all_oos_trades),
            **recommendation_payload["metrics"],
        }
        if metrics_payload["recommended_risk_plan"] is not None:
            metrics_payload["recommended_risk_plan"] = {
                **metrics_payload["recommended_risk_plan"],
                "candidate_risk_plan_version_id": str(base_risk_plan.id),
                "base_risk_plan_version_id": str(base_risk_plan.id),
            }

        passed = recommendation_payload["metrics"].get("folds_passed_count", 0)
        run = WalkForwardRun(
            run_id=uuid4(),
            strategy_id=request.strategy_id,
            strategy_version_id=request.strategy_version_id,
            window_count=len(fold_results),
            passed_window_count=int(passed),
            metrics=metrics_payload,
            created_at=created_at,
        )
        return run

    # ------------------------------------------------------------------
    # Fold execution
    # ------------------------------------------------------------------

    def _run_fold(
        self,
        *,
        fold: FoldWindow,
        strategy_payload: StrategyVersion,
        base_risk_plan: RiskProfileVersion,
        sweep_grid: list[dict[str, Any]],
        symbols: tuple[str, ...],
        bars_by_symbol: dict[str, list[NormalizedBar]],
        request: WalkForwardExecutionRequest,
        cost_model: CostModel,
        metrics_service: BacktestMetricsService,
        selection_criterion: SelectionCriterion,
    ) -> WalkForwardFoldResult:
        is_bars = self._slice_bars(bars_by_symbol, fold.is_start, fold.is_end)
        oos_bars = self._slice_bars(bars_by_symbol, fold.oos_start, fold.oos_end)
        if not is_bars or not oos_bars:
            return WalkForwardFoldResult(
                fold_index=fold.fold_index,
                is_start=fold.is_start,
                is_end=fold.is_end,
                oos_start=fold.oos_start,
                oos_end=fold.oos_end,
                selected_parameters=None,
                is_metrics={},
                oos_metrics={},
                candidate_scores=[],
                oos_trade_ledger=[],
                oos_equity_curve=[],
                risk_decision_card_ids=[],
            )

        # Score every sweep candidate on the IS portion.
        is_results: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for parameters in sweep_grid:
            candidate_risk_plan = _apply_sweep(base_risk_plan, parameters)
            components = self._build_components(
                request=request,
                strategy_payload=strategy_payload,
                risk_plan=candidate_risk_plan,
                symbols=symbols,
            )
            is_metrics = self._replay_window(
                components=components,
                bars=is_bars,
                start=fold.is_start,
                end=fold.is_end,
                request=request,
                cost_model=cost_model,
                metrics_service=metrics_service,
            )
            is_results.append((parameters, is_metrics))

        scores = [(params, score_candidate(metrics=metrics, criterion=selection_criterion)) for params, metrics in is_results]
        winner = select_winner(candidate_scores=scores)
        if winner is None:
            return WalkForwardFoldResult(
                fold_index=fold.fold_index,
                is_start=fold.is_start,
                is_end=fold.is_end,
                oos_start=fold.oos_start,
                oos_end=fold.oos_end,
                selected_parameters=None,
                is_metrics={},
                oos_metrics={},
                candidate_scores=[],
                oos_trade_ledger=[],
                oos_equity_curve=[],
                risk_decision_card_ids=[],
            )
        winner_parameters, _ = winner
        winner_is_metrics = next(m for p, m in is_results if p == winner_parameters)
        winner_risk_plan = _apply_sweep(base_risk_plan, winner_parameters)

        # OOS replay with the winner candidate.
        winner_components = self._build_components(
            request=request,
            strategy_payload=strategy_payload,
            risk_plan=winner_risk_plan,
            symbols=symbols,
        )
        oos_engine = HistoricalReplayEngine(
            mode=RiskDecisionMode.WALK_FORWARD,
            risk_decision_sink=self._risk_decision_sink,
            evidence_recorder=None,  # WF persists aggregate evidence; per-fold replays are transient
        )
        oos_replay = oos_engine.run(
            components=winner_components,
            bars=oos_bars,
            start=fold.oos_start,
            end=fold.oos_end,
            initial_cash=request.initial_capital,
            run_id=uuid4(),
        )
        oos_bundle = metrics_service.compute(
            replay=oos_replay,
            cost_model=cost_model,
            initial_capital=request.initial_capital,
            timeframe=request.timeframe,
        )

        # Score every candidate on the OOS portion too — operators want to see
        # the full landscape, not just the winner's OOS line.
        oos_candidate_scores: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for parameters in sweep_grid:
            if parameters == winner_parameters:
                oos_candidate_scores.append((parameters, oos_bundle.metrics))
                continue
            candidate_risk_plan = _apply_sweep(base_risk_plan, parameters)
            components = self._build_components(
                request=request,
                strategy_payload=strategy_payload,
                risk_plan=candidate_risk_plan,
                symbols=symbols,
            )
            cand_metrics = self._replay_window(
                components=components,
                bars=oos_bars,
                start=fold.oos_start,
                end=fold.oos_end,
                request=request,
                cost_model=cost_model,
                metrics_service=metrics_service,
            )
            oos_candidate_scores.append((parameters, cand_metrics))

        return WalkForwardFoldResult(
            fold_index=fold.fold_index,
            is_start=fold.is_start,
            is_end=fold.is_end,
            oos_start=fold.oos_start,
            oos_end=fold.oos_end,
            selected_parameters=winner_parameters,
            is_metrics=winner_is_metrics,
            oos_metrics=oos_bundle.metrics,
            candidate_scores=oos_candidate_scores,
            oos_trade_ledger=list(oos_bundle.trade_ledger),
            oos_equity_curve=list(oos_bundle.equity_curve),
            risk_decision_card_ids=[str(c.risk_decision_id) for c in oos_engine.risk_decision_cards()],
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _replay_window(
        self,
        *,
        components: ResolvedDeploymentComponents,
        bars: list[NormalizedBar],
        start: datetime,
        end: datetime,
        request: WalkForwardExecutionRequest,
        cost_model: CostModel,
        metrics_service: BacktestMetricsService,
    ) -> dict[str, Any]:
        engine = HistoricalReplayEngine(
            mode=RiskDecisionMode.WALK_FORWARD,
            risk_decision_sink=None,
            evidence_recorder=None,
        )
        replay = engine.run(
            components=components,
            bars=bars,
            start=start,
            end=end,
            initial_cash=request.initial_capital,
            run_id=uuid4(),
        )
        bundle = metrics_service.compute(
            replay=replay,
            cost_model=cost_model,
            initial_capital=request.initial_capital,
            timeframe=request.timeframe,
        )
        return dict(bundle.metrics)

    def _resolve_strategy_version(self, strategy_version_id: UUID) -> StrategyVersion:
        if self._strategy_lookup is None:
            raise ValueError(
                "WalkForwardExecutionService requires a strategy lookup; configure via runtime"
            )
        record = self._strategy_lookup.get_version(strategy_version_id)
        payload = getattr(record, "payload", record)
        if not isinstance(payload, StrategyVersion):
            raise ValueError(f"strategy version {strategy_version_id} is not a StrategyVersion")
        return payload

    def _resolve_base_risk_plan(
        self,
        request: WalkForwardExecutionRequest,
    ) -> RiskProfileVersion:
        sweep = request.sweep
        return load_risk_profile_from_plan_version(
            store=self._store,
            risk_plan_version_id=sweep.base_risk_plan_version_id if sweep else None,
            purpose="WalkForwardExecutionService",
        )

    def _build_components(
        self,
        *,
        request: WalkForwardExecutionRequest,
        strategy_payload: StrategyVersion,
        risk_plan: RiskProfileVersion,
        symbols: tuple[str, ...],
    ) -> ResolvedDeploymentComponents:
        return ResolvedDeploymentComponents(
            strategy=strategy_payload,
            strategy_controls=StrategyControlsVersion(
                id=uuid4(),
                strategy_controls_id=uuid4(),
                version=1,
                name=f"WF {request.timeframe} controls",
                timeframe=request.timeframe,
            ),
            risk_profile=risk_plan,
            execution_style=ExecutionStyleVersion(
                id=uuid4(),
                execution_style_id=uuid4(),
                version=1,
                name="WF market entry, signal-driven exit",
                entry_order_type=OrderType.MARKET,
                bracket=BracketSpec(enabled=False),
            ),
            universe=UniverseSnapshot(
                id=uuid4(),
                universe_id=uuid4(),
                version=1,
                name="Walk-Forward universe",
                symbols=[UniverseSymbol(symbol=s) for s in symbols],
            ),
        )

    def _ingest_full_window(
        self,
        *,
        request: WalkForwardExecutionRequest,
        symbols: tuple[str, ...],
    ) -> tuple[NormalizedBar, ...]:
        if self._ingest_service is None:
            raise ValueError(
                "WalkForwardExecutionService requires an ingest service; configure via runtime"
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
    def _slice_bars(
        bars_by_symbol: dict[str, list[NormalizedBar]],
        window_start: datetime,
        window_end: datetime,
    ) -> list[NormalizedBar]:
        # Look-back tail: include bars before window_start so feature warmup
        # has values when the window opens. We include all earlier bars from
        # ingest (feature engine handles WARMUP gracefully), then up to window_end.
        out: list[NormalizedBar] = []
        for sym_bars in bars_by_symbol.values():
            for bar in sym_bars:
                if bar.timestamp <= window_end:
                    out.append(bar)
        out.sort(key=lambda b: (b.timestamp, b.symbol))
        return out


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


def _expand_sweep_grid(
    sweep: WalkForwardSweepConfig | None,
) -> list[dict[str, Any]]:
    if sweep is None or not sweep.enabled or not sweep.parameters:
        return []
    grid: list[dict[str, Any]] = [{}]
    for parameter in sweep.parameters:
        next_grid: list[dict[str, Any]] = []
        for existing in grid:
            for value in parameter.values:
                merged = dict(existing)
                merged[parameter.field] = value
                next_grid.append(merged)
        grid = next_grid
    return grid

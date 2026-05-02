"""BacktestExecutionService — drive the unified spine on historical bars.

RiskPlan belongs to the Account or selected research run. SignalPlan describes
the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan,
and current account or simulated account state to produce a RiskDecisionCard.
No simulated or real order may be created without that RiskDecisionCard.

This service replaces the prior synthetic ``_simulate()`` engine. It:

1. Resolves the saved StrategyVersion, Strategy Control, Execution Plan, and
   Risk Plan versions, then assembles ``ResolvedDeploymentComponents``.
2. Calls ``HistoricalBarIngestService.ensure_bars`` for each requested symbol;
   matching cache hits short-circuit the provider call.
3. Calls ``HistoricalReplayEngine.run`` (mode=``backtest``) — the same spine
   Sim Lab uses, so FeatureEngine + SignalEngine + SignalPlanBuilder +
   RiskResolver + RiskDecisionCard all run against historical bars.
4. Hands the replay result to ``BacktestMetricsService`` for the post-fill
   cost model + the 11 standard metrics.
5. Optionally runs Monte Carlo on the realised trade ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from backend.app.data_center.ingest_service import (
    AlpacaBarsSource,
    HistoricalBarIngestRequest,
    HistoricalBarIngestService,
    HistoricalDatasetStore,
    YahooBarsSource,
)
from backend.app.domain import (
    BacktestRun,
    ResearchDataPolicy,
    ResearchRunKind,
    RiskDecisionMode,
    StrategyVersion,
)
from backend.app.domain._base import JsonDict, utc_now
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.simulation import HistoricalReplayEngine

from backend.app.research.artifacts import artifact_lineage_payload, build_research_run_artifact
from backend.app.research.components import load_research_components

from .metrics_service import BacktestMetricsService, CostModel
from .monte_carlo import MonteCarloAnalyzer, MonteCarloConfig


REQUIRED_BACKTEST_METRICS = (
    "cagr",
    "sharpe",
    "sortino",
    "calmar",
    "max_drawdown",
    "hit_rate",
    "profit_factor",
    "expectancy",
    "exposure",
    "turnover",
    "time_in_market",
)


class StrategyVersionLookup(Protocol):
    """Resolves a saved StrategyVersion by id."""

    def get_version(self, strategy_version_id: UUID) -> Any: ...


@dataclass(frozen=True)
class BacktestExecutionRequest:
    strategy_id: UUID
    strategy_version_id: UUID
    symbols: tuple[str, ...]
    start: datetime
    end: datetime
    initial_capital: float
    cost_model: JsonDict
    risk_plan_version_id: UUID | None = None
    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    source: Literal["alpaca", "yahoo"] = "yahoo"
    timeframe: str = "1d"
    adjustment_policy: Literal[
        "split_dividend_adjusted", "split_only", "raw"
    ] = "split_dividend_adjusted"
    monte_carlo: JsonDict | None = None
    watchlist_snapshot_id: UUID | None = None
    universe: tuple[str, ...] = field(default=())  # legacy alias for symbols


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("backtest universe symbols must be non-empty")
    return normalized


class BacktestExecutionService:
    """Build real backtest evidence by driving the unified research spine.

    Spine:
        FeatureSnapshot → SignalEngine → CandidateTradeIntent
            → SignalPlanBuilder → SignalPlan
            → RiskResolver(SignalPlan + RiskPlan + state) → RiskDecisionCard
            → SimulatedBroker (research-only; Governor is bypassed by design).
    """

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

    def create_run(self, request: BacktestExecutionRequest) -> BacktestRun:
        symbols = self._normalize_request(request)

        components = self._build_components(request=request, symbols=symbols)

        ingest_results = self._ingest_bars(request=request, symbols=symbols)
        bars = self._merge_bar_windows(ingest_results)

        warmup = max(1, components.strategy.warmup_bars or 1) if hasattr(components.strategy, "warmup_bars") else 1
        if not bars:
            raise ValueError("no bars available for backtest window")

        replay_engine = HistoricalReplayEngine(
            mode=RiskDecisionMode.BACKTEST,
            risk_decision_sink=self._risk_decision_sink,
            evidence_recorder=self._store,
        )
        run_id = uuid4()
        artifact = build_research_run_artifact(
            run_id=run_id,
            run_kind=ResearchRunKind.BACKTEST,
            components=components,
            data_policy=ResearchDataPolicy(
                provider=request.source,
                timeframe=request.timeframe,
                adjustment_policy=request.adjustment_policy,
                start=request.start,
                end=request.end,
                warmup_start=min((bar.timestamp for bar in bars), default=request.start),
            ),
            historical_dataset_ids=(result.dataset_id for result in ingest_results),
            data_quality_warnings=(
                warning
                for result in ingest_results
                for warning in result.data_quality_warnings
            ),
            watchlist_snapshot_ids=(
                (request.watchlist_snapshot_id,) if request.watchlist_snapshot_id else ()
            ),
        )
        replay = replay_engine.run(
            components=components,
            bars=bars,
            start=request.start,
            end=request.end,
            initial_cash=request.initial_capital,
            run_id=run_id,
        )

        metrics_service = BacktestMetricsService()
        cost_model = CostModel(
            commission_per_trade=float(request.cost_model.get("commission_per_trade", 0.0)),
            slippage_bps=float(request.cost_model.get("slippage_bps", 0.0)),
        )
        metrics_bundle = metrics_service.compute(
            replay=replay,
            cost_model=cost_model,
            initial_capital=request.initial_capital,
            timeframe=request.timeframe,
        )

        monte_carlo_payload: JsonDict | None = None
        if request.monte_carlo and request.monte_carlo.get("enabled"):
            mc_config = MonteCarloConfig(**request.monte_carlo)
            mc_result = MonteCarloAnalyzer().run(
                trade_pnls=[float(t["net_pnl"]) for t in metrics_bundle.trade_ledger],
                bar_returns=self._bar_returns_from_curve(metrics_bundle.equity_curve),
                initial_capital=request.initial_capital,
                config=mc_config,
            )
            monte_carlo_payload = {
                "method": mc_result.method,
                "replications": mc_result.replications,
                "seed": mc_result.seed,
                "terminal_equity": mc_result.terminal_equity,
                "sharpe": mc_result.sharpe,
                "max_drawdown": mc_result.max_drawdown,
                "final_equity_histogram": mc_result.final_equity_histogram,
            }

        created_at = utc_now()
        status_history = (
            {"status": "queued", "at": created_at.isoformat()},
            {"status": "running", "at": created_at.isoformat()},
            {"status": "completed", "at": utc_now().isoformat()},
        )
        cards = replay_engine.risk_decision_cards()
        risk_decision_card_ids = tuple(str(card.risk_decision_id) for card in cards)

        metrics_payload = dict(metrics_bundle.metrics)
        metrics_payload.update(
            {
                "status": "completed",
                "status_updated_at": created_at.isoformat(),
                "status_history": status_history,
                "cost_model": metrics_bundle.cost_model,
                "result_summary": {
                    "equity_points": len(metrics_bundle.equity_curve),
                    "trade_count": len(metrics_bundle.trade_ledger),
                    "symbol_count": len(symbols),
                    "risk_decision_card_count": len(risk_decision_card_ids),
                },
                "per_regime_metrics": metrics_bundle.per_regime_metrics,
                "risk_plan_version_id": (
                    str(request.risk_plan_version_id) if request.risk_plan_version_id else None
                ),
                "feature_plan_id": str(replay.session.feature_plan_id) if replay.session.feature_plan_id else None,
                "historical_dataset_ids": [str(r.dataset_id) for r in ingest_results],
                "risk_decision_card_ids": list(risk_decision_card_ids),
                "monte_carlo": monte_carlo_payload,
                "research_artifact": artifact_lineage_payload(artifact),
            }
        )
        if self._store is not None and hasattr(self._store, "save_research_run_artifact"):
            self._store.save_research_run_artifact(artifact)

        return BacktestRun(
            run_id=run_id,
            artifact_id=artifact.artifact_id,
            deployment_snapshot_id=artifact.deployment_snapshot.snapshot_id,
            deployment_snapshot=artifact.deployment_snapshot,
            strategy_id=request.strategy_id,
            strategy_version_id=request.strategy_version_id,
            watchlist_snapshot_id=request.watchlist_snapshot_id,
            universe=symbols,
            timeframe=request.timeframe,
            start=request.start,
            end=request.end,
            initial_capital=request.initial_capital,
            cost_model=metrics_bundle.cost_model,
            status="completed",
            status_history=status_history,
            bar_count=len(bars),
            signal_plan_count=len(cards),
            simulated_trade_count=len(replay.trades),
            metrics=metrics_payload,
            results={
                "equity_curve": list(metrics_bundle.equity_curve),
                "trade_ledger": list(metrics_bundle.trade_ledger),
                "per_symbol_breakdown": list(metrics_bundle.per_symbol_breakdown),
                "drawdown_series": list(metrics_bundle.drawdown_series),
                "regime_tags": list(metrics_bundle.regime_tags),
                "per_regime_metrics": metrics_bundle.per_regime_metrics,
                "risk_decision_card_ids": list(risk_decision_card_ids),
                "monte_carlo": monte_carlo_payload,
            },
            created_at=created_at,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_request(self, request: BacktestExecutionRequest) -> tuple[str, ...]:
        provided = request.symbols or request.universe
        symbols = tuple(_normalize_symbol(symbol) for symbol in provided)
        if not symbols:
            raise ValueError("backtest universe must include at least one symbol")
        if request.initial_capital <= 0:
            raise ValueError("backtest initial capital must be positive")
        if request.start >= request.end:
            raise ValueError("backtest run start must be before end")
        return symbols

    def _build_components(
        self,
        *,
        request: BacktestExecutionRequest,
        symbols: tuple[str, ...],
    ) -> ResolvedDeploymentComponents:
        strategy_payload = self._resolve_strategy_version(request.strategy_version_id)
        if request.strategy_controls_version_id is None:
            raise ValueError("backtest requires strategy_controls_version_id")
        if request.execution_plan_version_id is None:
            raise ValueError("backtest requires execution_plan_version_id")
        return load_research_components(
            strategy_lookup=self._strategy_lookup,
            store=self._store,
            strategy_version_id=strategy_payload.id,
            expected_strategy_id=request.strategy_id,
            strategy_controls_version_id=request.strategy_controls_version_id,
            execution_plan_version_id=request.execution_plan_version_id,
            risk_plan_version_id=request.risk_plan_version_id,
            symbols=symbols,
            timeframe=request.timeframe,
            universe_name="Backtest universe",
            purpose="BacktestExecutionService",
        )

    def _resolve_strategy_version(self, strategy_version_id: UUID) -> StrategyVersion:
        if self._strategy_lookup is None:
            raise ValueError(
                "BacktestExecutionService requires a strategy lookup; configure via runtime"
            )
        record = self._strategy_lookup.get_version(strategy_version_id)
        payload = getattr(record, "payload", record)
        if not isinstance(payload, StrategyVersion):
            raise ValueError(f"strategy version {strategy_version_id} is not a StrategyVersion")
        return payload

    def _ingest_bars(
        self,
        *,
        request: BacktestExecutionRequest,
        symbols: tuple[str, ...],
    ) -> list[Any]:
        if self._ingest_service is None:
            raise ValueError(
                "BacktestExecutionService requires an ingest service; configure via runtime"
            )
        warmup_window = timedelta(days=14)  # over-fetch; cheap when cached
        results = []
        for symbol in symbols:
            results.append(
                self._ingest_service.ensure_bars(
                    HistoricalBarIngestRequest(
                        provider=request.source,
                        symbol=symbol,
                        timeframe=request.timeframe,
                        start=request.start - warmup_window,
                        end=request.end,
                        adjustment_policy=request.adjustment_policy,
                    )
                )
            )
        return results

    @staticmethod
    def _merge_bar_windows(results: list[Any]) -> tuple[NormalizedBar, ...]:
        merged: list[NormalizedBar] = []
        for result in results:
            merged.extend(result.bars)
        merged.sort(key=lambda bar: (bar.timestamp, bar.symbol))
        return tuple(merged)

    @staticmethod
    def _bar_returns_from_curve(equity_curve: tuple[dict[str, Any], ...]) -> list[float]:
        if len(equity_curve) < 2:
            return []
        returns: list[float] = []
        for previous, current in zip(equity_curve, equity_curve[1:]):
            prev_eq = float(previous.get("equity", 0))
            cur_eq = float(current.get("equity", 0))
            if prev_eq <= 0:
                returns.append(0.0)
            else:
                returns.append((cur_eq - prev_eq) / prev_eq)
        return returns

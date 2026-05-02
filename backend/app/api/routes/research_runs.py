"""Evidence-backed research run APIs.

These routes give the frontend first-class research surfaces without creating
alternate trading runtimes. They persist/query research evidence only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.data_center.historical_catalog import configure_persistence as configure_data_center_persistence
from backend.app.data_center.ingest_service import (
    AlpacaBarsSource,
    HistoricalBarIngestService,
    YahooBarsSource,
    alpaca_bars_source_from_runtime,
)
from backend.app.domain import (
    BacktestRun,
    OptimizationRun,
    ResearchDataPolicy,
    ResearchRunKind,
    RiskPlan,
    RiskPlanConfig,
    RiskPlanSource,
    RiskPlanStatus,
    RiskPlanTier,
    RiskPlanVersion,
    RiskPlanVersionStatus,
    SimulationRunEvidence,
    WalkForwardRun,
)
from backend.app.domain._base import JsonDict, utc_now
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.research.artifacts import artifact_lineage_payload, build_research_run_artifact
from backend.app.research.backtests import BacktestExecutionRequest, BacktestExecutionService
from backend.app.research.components import load_research_components
from backend.app.research.sim_lab import SimLabBatchRunRequest, SimLabBatchRunService
from backend.app.simulation import HistoricalReplayEngine
from backend.app.simulation.models import (
    EquityPoint,
    SimulatedFill,
    SimulatedOrder,
    SimulatedPosition,
    SimulatedTrade,
    SimulationEvent,
)


router = APIRouter(tags=["research-runs"])


class ResearchRunCommandResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool = True
    action: str
    run_id: UUID
    message: str


class BacktestRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: tuple[BacktestRun, ...] = ()


class SimulationSessionListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sessions: tuple[SimulationRunEvidence, ...] = ()


class OptimizationRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: tuple[OptimizationRun, ...] = ()


class WalkForwardRunListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: tuple[WalkForwardRun, ...] = ()


class SaveRiskPlanDraftRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    created_by: str | None = None


class SaveRiskPlanDraftResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    risk_plan: RiskPlan
    risk_plan_version: RiskPlanVersion
    source_run_id: UUID


class BacktestRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    strategy_id: UUID
    strategy_version_id: UUID
    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    risk_plan_version_id: UUID | None = None
    watchlist_snapshot_id: UUID | None = None
    universe: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    timeframe: str = "1d"
    start: datetime
    end: datetime
    initial_capital: float = Field(default=0, ge=0)
    cost_model: JsonDict = Field(default_factory=dict)
    source: str = "yahoo"
    adjustment_policy: str = "split_dividend_adjusted"
    monte_carlo: JsonDict | None = None
    bar_count: int = Field(default=0, ge=0)
    signal_plan_count: int = Field(default=0, ge=0)
    simulated_trade_count: int = Field(default=0, ge=0)
    metrics: JsonDict = Field(default_factory=dict)


class SimulationSessionRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: UUID
    strategy_version_id: UUID
    scenario_name: str = Field(min_length=1)
    start: datetime
    end: datetime
    signal_plan_count: int = Field(default=0, ge=0)
    simulated_order_count: int = Field(default=0, ge=0)
    simulated_fill_count: int = Field(default=0, ge=0)
    metrics: JsonDict = Field(default_factory=dict)


class SimulationRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    signal_plan_count: int = Field(default=0, ge=0)
    simulated_order_count: int = Field(default=0, ge=0)
    simulated_fill_count: int = Field(default=0, ge=0)
    metrics: JsonDict = Field(default_factory=dict)


class SimLabBatchRunApiRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy_id: UUID
    strategy_version_id: UUID
    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    risk_plan_version_id: UUID | None = None
    scenario_name: str = Field(min_length=1)
    universe: tuple[str, ...] = Field(min_length=1)
    timeframe: str = "5m"
    start: datetime
    end: datetime
    initial_cash: float = Field(default=100_000, gt=0)
    bar_count: int = Field(default=12, ge=2)


class SimLabBatchRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run: SimulationRunEvidence
    events: tuple[SimulationEvent, ...] = ()
    orders: tuple[SimulatedOrder, ...] = ()
    fills: tuple[SimulatedFill, ...] = ()
    positions: tuple[SimulatedPosition, ...] = ()
    trades: tuple[SimulatedTrade, ...] = ()
    equity_curve: tuple[EquityPoint, ...] = ()


class OptimizationRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    strategy_id: UUID
    strategy_version_id: UUID
    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    # Spine-driven optimization: when symbols + sweep are supplied, the service
    # runs a parameter search on one window via HistoricalReplayEngine and
    # produces a candidate landscape + recommended-with-WF-validation winner.
    symbols: tuple[str, ...] = ()
    start: datetime | None = None
    end: datetime | None = None
    timeframe: str = "1d"
    initial_capital: float = Field(default=0, ge=0)
    cost_model: JsonDict = Field(default_factory=dict)
    source: str = "yahoo"
    adjustment_policy: str = "split_dividend_adjusted"
    method: str = "grid"
    max_candidates: int | None = 200
    seed: int = 42
    selection_criterion: str = "max_dd_bounded_sharpe"
    sweep: JsonDict | None = None
    monte_carlo: JsonDict | None = None
    runners_up_threshold_pct: float = 0.05
    walk_forward_handoff_top_k: int = 3
    heatmap_dimensions: tuple[str, str] | None = None
    # Legacy placeholder fields for the read-only path
    objective: str = "max_dd_bounded_sharpe"
    candidate_count: int = Field(default=0, ge=0)
    best_parameters: JsonDict = Field(default_factory=dict)
    best_metrics: JsonDict = Field(default_factory=dict)


class WalkForwardRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="allow")

    strategy_id: UUID
    strategy_version_id: UUID
    strategy_controls_version_id: UUID | None = None
    execution_plan_version_id: UUID | None = None
    # Spine-driven WF: when symbols are supplied, the service runs IS+OOS
    # folds via HistoricalReplayEngine and produces a real recommendation.
    symbols: tuple[str, ...] = ()
    start: datetime | None = None
    end: datetime | None = None
    timeframe: str = "1d"
    initial_capital: float = Field(default=0, ge=0)
    cost_model: JsonDict = Field(default_factory=dict)
    source: str = "yahoo"
    adjustment_policy: str = "split_dividend_adjusted"
    window_mode: str = "rolling"
    is_length: JsonDict = Field(default_factory=lambda: {"unit": "days", "value": 180})
    oos_length: JsonDict = Field(default_factory=lambda: {"unit": "days", "value": 60})
    step: JsonDict | None = None
    max_folds: int | None = None
    selection_criterion: str = "max_dd_bounded_sharpe"
    sweep: JsonDict | None = None
    monte_carlo: JsonDict | None = None
    fold_pass_threshold_sharpe: float = 0.0
    score_weights: JsonDict | None = None
    ship_thresholds: JsonDict | None = None
    # Legacy placeholder fields for the read-only path
    window_count: int = Field(default=0, ge=0)
    passed_window_count: int = Field(default=0, ge=0)
    metrics: JsonDict = Field(default_factory=dict)


class CancelRunRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1)


class BacktestResultsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    status: str
    equity_curve: tuple[JsonDict, ...] = ()
    trade_ledger: tuple[JsonDict, ...] = ()
    per_symbol_breakdown: tuple[JsonDict, ...] = ()
    drawdown_series: tuple[JsonDict, ...] = ()
    regime_tags: tuple[JsonDict, ...] = ()
    per_regime_metrics: JsonDict = Field(default_factory=dict)


class BacktestMetricsResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: UUID
    status: str
    metrics: JsonDict
    cost_model: JsonDict


def get_research_store() -> SQLiteRuntimeStore:
    return SQLiteRuntimeStore(get_runtime_db_path())


def _dependency(default: object) -> object:
    return Depends(default)


ResearchStoreDependency = Annotated[Any, _dependency(get_research_store)]
CancelBody = Annotated[CancelRunRequest, Body(...)]


@router.get("/api/v1/backtests", response_model=BacktestRunListResponse)
@router.get("/api/v1/research/backtests", response_model=BacktestRunListResponse)
def list_backtests(store: ResearchStoreDependency) -> BacktestRunListResponse:
    return BacktestRunListResponse(runs=_list_typed(store, "backtest_run", BacktestRun))


@router.post("/api/v1/backtests", response_model=BacktestRun)
@router.post("/api/v1/research/backtests", response_model=BacktestRun)
def create_backtest_run(request: BacktestRunRequest, store: ResearchStoreDependency) -> BacktestRun:
    symbols = tuple(s for s in (request.symbols or request.universe) if s)
    if symbols:
        if request.initial_capital <= 0:
            raise HTTPException(
                status_code=422,
                detail="initial_capital must be positive when symbols are provided",
            )
        if request.risk_plan_version_id is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "risk_plan_version_id is required for spine-driven backtests "
                    "(per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §6.1)"
                ),
            )
        configure_data_center_persistence(store)
        ingest_service = HistoricalBarIngestService(
            store=store,
            sources={"yahoo": YahooBarsSource(), "alpaca": alpaca_bars_source_from_runtime(store)},
        )
        backtest_service = BacktestExecutionService(
            strategy_lookup=_get_strategy_lookup(),
            ingest_service=ingest_service,
            store=store,
            risk_decision_sink=store,
        )
        try:
            run = backtest_service.create_run(
                BacktestExecutionRequest(
                    strategy_id=request.strategy_id,
                    strategy_version_id=request.strategy_version_id,
                    strategy_controls_version_id=_required_component_id(
                        request.strategy_controls_version_id,
                        "strategy_controls_version_id",
                        "backtest",
                    ),
                    execution_plan_version_id=_required_component_id(
                        request.execution_plan_version_id,
                        "execution_plan_version_id",
                        "backtest",
                    ),
                    risk_plan_version_id=request.risk_plan_version_id,
                    watchlist_snapshot_id=request.watchlist_snapshot_id,
                    symbols=symbols,
                    timeframe=request.timeframe,
                    start=request.start,
                    end=request.end,
                    initial_capital=request.initial_capital,
                    cost_model=request.cost_model,
                    source=request.source,  # type: ignore[arg-type]
                    adjustment_policy=request.adjustment_policy,  # type: ignore[arg-type]
                    monte_carlo=request.monte_carlo,
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    else:
        raise HTTPException(
            status_code=422,
            detail=(
                "backtest research evidence must be produced by the research spine; "
                "provide symbols/watchlist input instead of client-authored counts"
            ),
        )
    return store.save_research_evidence(run)


def _get_strategy_lookup() -> Any:
    from backend.app.api.routes.strategies import get_strategy_service

    return get_strategy_service()


def _required_component_id(value: UUID | None, field_name: str, run_kind: str) -> UUID:
    if value is None:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} is required for spine-driven {run_kind} runs",
        )
    return value


@router.get("/api/v1/backtests/{run_id}", response_model=BacktestRun)
@router.get("/api/v1/research/backtests/{run_id}", response_model=BacktestRun)
def get_backtest_run(run_id: UUID, store: ResearchStoreDependency) -> BacktestRun:
    return _load_typed(store, run_id, BacktestRun)


@router.post("/api/v1/backtests/{run_id}/cancel", response_model=BacktestRun)
@router.post("/api/v1/research/backtests/{run_id}/cancel", response_model=BacktestRun)
def cancel_backtest_run(run_id: UUID, request: CancelBody, store: ResearchStoreDependency) -> BacktestRun:
    run = _load_typed(store, run_id, BacktestRun)
    canceled = run.model_copy(
        update={
            "status": "canceled",
            "metrics": _with_status(run.metrics, "canceled", reason=request.reason),
            "status_history": (*run.status_history, {"status": "canceled", "at": utc_now().isoformat(), "reason": request.reason}),
        }
    )
    return store.save_research_evidence(canceled)


@router.get("/api/v1/research/backtests/{run_id}/results", response_model=BacktestResultsResponse)
def get_backtest_results(run_id: UUID, store: ResearchStoreDependency) -> BacktestResultsResponse:
    run = _load_typed(store, run_id, BacktestRun)
    return BacktestResultsResponse(
        run_id=run.run_id,
        status=run.status,
        equity_curve=tuple(run.results.get("equity_curve", ())),
        trade_ledger=tuple(run.results.get("trade_ledger", ())),
        per_symbol_breakdown=tuple(run.results.get("per_symbol_breakdown", ())),
        drawdown_series=tuple(run.results.get("drawdown_series", ())),
        regime_tags=tuple(run.results.get("regime_tags", ())),
        per_regime_metrics=dict(run.results.get("per_regime_metrics", {})),
    )


@router.get("/api/v1/research/backtests/{run_id}/metrics", response_model=BacktestMetricsResponse)
def get_backtest_metrics(run_id: UUID, store: ResearchStoreDependency) -> BacktestMetricsResponse:
    run = _load_typed(store, run_id, BacktestRun)
    return BacktestMetricsResponse(
        run_id=run.run_id,
        status=run.status,
        metrics=run.metrics,
        cost_model=run.cost_model,
    )


@router.get("/api/v1/sim-lab/sessions", response_model=SimulationSessionListResponse)
def list_sim_lab_sessions(store: ResearchStoreDependency) -> SimulationSessionListResponse:
    return SimulationSessionListResponse(sessions=_list_typed(store, "simulation_run", SimulationRunEvidence))


@router.post("/api/v1/sim-lab/sessions", response_model=SimulationRunEvidence)
def create_sim_lab_session(request: SimulationSessionRequest, store: ResearchStoreDependency) -> SimulationRunEvidence:
    raise HTTPException(
        status_code=422,
        detail=(
            "sim lab evidence must be produced by the research spine; "
            "use /api/v1/research/sim_lab/runs instead of client-authored sessions"
        ),
    )


@router.get("/api/v1/sim-lab/sessions/{session_id}", response_model=SimulationRunEvidence)
def get_sim_lab_session(session_id: UUID, store: ResearchStoreDependency) -> SimulationRunEvidence:
    return _load_typed(store, session_id, SimulationRunEvidence)


@router.delete("/api/v1/sim-lab/sessions/{session_id}", response_model=SimulationRunEvidence)
def archive_sim_lab_session(session_id: UUID, store: ResearchStoreDependency) -> SimulationRunEvidence:
    evidence = _load_typed(store, session_id, SimulationRunEvidence)
    archived = evidence.model_copy(update={"metrics": _with_status(evidence.metrics, "archived")})
    return store.save_research_evidence(archived)


@router.post("/api/v1/sim-lab/sessions/{session_id}/run", response_model=SimulationRunEvidence)
def run_sim_lab_session(
    session_id: UUID,
    request: SimulationRunRequest,
    store: ResearchStoreDependency,
) -> SimulationRunEvidence:
    raise HTTPException(
        status_code=422,
        detail=(
            "sim lab evidence must be produced by the research spine; "
            "use /api/v1/research/sim_lab/runs instead of client-authored sessions"
        ),
    )


@router.get("/api/v1/sim-lab/sessions/{session_id}/results", response_model=SimulationRunEvidence)
def get_sim_lab_results(session_id: UUID, store: ResearchStoreDependency) -> SimulationRunEvidence:
    return _load_typed(store, session_id, SimulationRunEvidence)


@router.post("/api/v1/research/sim_lab/runs", response_model=SimLabBatchRunResponse)
def create_sim_lab_batch_run(
    request: SimLabBatchRunApiRequest,
    store: ResearchStoreDependency,
) -> SimLabBatchRunResponse:
    try:
        run_id = uuid4()
        components = load_research_components(
            strategy_lookup=_get_strategy_lookup(),
            store=store,
            strategy_version_id=request.strategy_version_id,
            expected_strategy_id=request.strategy_id,
            strategy_controls_version_id=_required_component_id(
                request.strategy_controls_version_id,
                "strategy_controls_version_id",
                "sim lab",
            ),
            execution_plan_version_id=_required_component_id(
                request.execution_plan_version_id,
                "execution_plan_version_id",
                "sim lab",
            ),
            risk_plan_version_id=_required_component_id(
                request.risk_plan_version_id,
                "risk_plan_version_id",
                "sim lab",
            ),
            symbols=tuple(symbol.strip().upper() for symbol in request.universe if symbol.strip()),
            timeframe=request.timeframe,
            universe_name="Sim Lab universe",
            purpose="SimLabBatchRunService",
        )
        result = SimLabBatchRunService(
            replay_engine=HistoricalReplayEngine(evidence_recorder=store)
        ).create_run(
            SimLabBatchRunRequest(
                strategy_id=request.strategy_id,
                strategy_version_id=request.strategy_version_id,
                scenario_name=request.scenario_name,
                start=request.start,
                end=request.end,
                universe=request.universe,
                timeframe=request.timeframe,
                initial_cash=request.initial_cash,
                bar_count=request.bar_count,
            ),
            components=components,
            run_id=run_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.evidence is None:  # pragma: no cover - engine always returns evidence.
        raise HTTPException(status_code=500, detail="sim lab batch run did not produce evidence")
    artifact = build_research_run_artifact(
        run_id=result.evidence.run_id,
        run_kind=ResearchRunKind.SIM_LAB,
        components=components,
        data_policy=ResearchDataPolicy(
            provider="simulated",
            timeframe=request.timeframe,
            adjustment_policy="raw",
            start=request.start,
            end=request.end,
        ),
        producer="historical_replay",
    )
    store.save_research_run_artifact(artifact)
    evidence = result.evidence.model_copy(
        update={
            "artifact_id": artifact.artifact_id,
            "deployment_snapshot_id": artifact.deployment_snapshot.snapshot_id,
            "deployment_snapshot": artifact.deployment_snapshot,
            "metrics": {
                **result.evidence.metrics,
                "research_artifact": artifact_lineage_payload(artifact),
            },
        }
    )
    store.save_research_evidence(evidence)
    result = result.model_copy(update={"evidence": evidence})
    return SimLabBatchRunResponse(
        run=evidence,
        events=result.events,
        orders=result.orders,
        fills=result.fills,
        positions=result.positions,
        trades=result.trades,
        equity_curve=result.equity_curve,
    )


@router.websocket("/api/v1/research/sim_lab/stream")
async def stream_sim_lab_batch_run(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        api_request = _sim_lab_stream_request(websocket)
        request = SimLabBatchRunRequest(
            strategy_id=api_request.strategy_id,
            strategy_version_id=api_request.strategy_version_id,
            scenario_name=api_request.scenario_name,
            start=api_request.start,
            end=api_request.end,
            universe=api_request.universe,
            timeframe=api_request.timeframe,
            initial_cash=api_request.initial_cash,
            bar_count=api_request.bar_count,
        )
        store = SQLiteRuntimeStore(get_runtime_db_path())
        components = load_research_components(
            strategy_lookup=_get_strategy_lookup(),
            store=store,
            strategy_version_id=api_request.strategy_version_id,
            expected_strategy_id=api_request.strategy_id,
            strategy_controls_version_id=_required_stream_component_id(
                api_request.strategy_controls_version_id,
                "strategy_controls_version_id",
            ),
            execution_plan_version_id=_required_stream_component_id(
                api_request.execution_plan_version_id,
                "execution_plan_version_id",
            ),
            risk_plan_version_id=_required_stream_component_id(
                api_request.risk_plan_version_id,
                "risk_plan_version_id",
            ),
            symbols=api_request.universe,
            timeframe=api_request.timeframe,
            universe_name="Sim Lab stream universe",
            purpose="SimLabBatchRunService",
        )
        run_id = uuid4()
        messages, result = SimLabBatchRunService(
            replay_engine=HistoricalReplayEngine(evidence_recorder=store)
        ).stream_result(
            request,
            components=components,
            run_id=run_id,
        )
        if result.evidence is None:  # pragma: no cover
            raise ValueError("sim lab stream run did not produce evidence")
        artifact = build_research_run_artifact(
            run_id=result.evidence.run_id,
            run_kind=ResearchRunKind.SIM_LAB,
            components=components,
            data_policy=ResearchDataPolicy(
                provider="simulated",
                timeframe=request.timeframe,
                adjustment_policy="raw",
                start=request.start,
                end=request.end,
            ),
            producer="historical_replay",
        )
        store.save_research_run_artifact(artifact)
        evidence = result.evidence.model_copy(
            update={
                "artifact_id": artifact.artifact_id,
                "deployment_snapshot_id": artifact.deployment_snapshot.snapshot_id,
                "deployment_snapshot": artifact.deployment_snapshot,
                "metrics": {
                    **result.evidence.metrics,
                    "research_artifact": artifact_lineage_payload(artifact),
                },
            }
        )
        store.save_research_evidence(evidence)
    except ValueError as exc:
        await websocket.send_json({"type": "error", "code": "invalid_sim_lab_stream_request", "message": str(exc)})
        await websocket.close(code=1008)
        return

    for message in messages:
        await websocket.send_json(message.model_dump(mode="json"))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        return


@router.get("/api/v1/optimization/runs", response_model=OptimizationRunListResponse)
def list_optimization_runs(store: ResearchStoreDependency) -> OptimizationRunListResponse:
    return OptimizationRunListResponse(runs=_list_typed(store, "optimization_run", OptimizationRun))


@router.post("/api/v1/optimization/runs", response_model=OptimizationRun)
def create_optimization_run(request: OptimizationRunRequest, store: ResearchStoreDependency) -> OptimizationRun:
    symbols = tuple(s for s in request.symbols if s)
    if symbols and request.sweep:
        if request.start is None or request.end is None:
            raise HTTPException(
                status_code=422,
                detail="start and end are required for spine-driven optimization runs",
            )
        if request.initial_capital <= 0:
            raise HTTPException(
                status_code=422,
                detail="initial_capital must be positive when symbols are provided",
            )
        configure_data_center_persistence(store)
        ingest_service = HistoricalBarIngestService(
            store=store,
            sources={"yahoo": YahooBarsSource(), "alpaca": alpaca_bars_source_from_runtime(store)},
        )
        from backend.app.research.optimization import (
            OptimizationExecutionRequest,
            OptimizationExecutionService,
            OptimizationSweepConfig,
            OptimizationSweepParameter,
        )
        from backend.app.research.backtests.monte_carlo import MonteCarloConfig

        sweep_payload = request.sweep or {}
        params = tuple(
            OptimizationSweepParameter(field=p["field"], values=tuple(p["values"]))
            for p in sweep_payload.get("parameters", [])
        )
        if not params:
            raise HTTPException(
                status_code=422,
                detail="optimization sweep must declare at least one parameter",
            )
        base_id = sweep_payload.get("base_risk_plan_version_id")
        sweep_config = OptimizationSweepConfig(
            base_risk_plan_version_id=UUID(base_id) if base_id else None,
            parameters=params,
        )
        opt_request = OptimizationExecutionRequest(
            strategy_id=request.strategy_id,
            strategy_version_id=request.strategy_version_id,
            strategy_controls_version_id=_required_component_id(
                request.strategy_controls_version_id,
                "strategy_controls_version_id",
                "optimization",
            ),
            execution_plan_version_id=_required_component_id(
                request.execution_plan_version_id,
                "execution_plan_version_id",
                "optimization",
            ),
            symbols=symbols,
            start=request.start,
            end=request.end,
            initial_capital=request.initial_capital,
            cost_model=request.cost_model,
            sweep=sweep_config,
            timeframe=request.timeframe,
            source=request.source,  # type: ignore[arg-type]
            adjustment_policy=request.adjustment_policy,  # type: ignore[arg-type]
            method=request.method,  # type: ignore[arg-type]
            selection_criterion=request.selection_criterion,  # type: ignore[arg-type]
            max_candidates=request.max_candidates,
            seed=request.seed,
            monte_carlo=MonteCarloConfig(**request.monte_carlo) if request.monte_carlo else None,
            runners_up_threshold_pct=request.runners_up_threshold_pct,
            walk_forward_handoff_top_k=request.walk_forward_handoff_top_k,
            heatmap_dimensions=request.heatmap_dimensions,
        )
        try:
            run = OptimizationExecutionService(
                strategy_lookup=_get_strategy_lookup(),
                ingest_service=ingest_service,
                store=store,
                risk_decision_sink=store,
            ).create_run(opt_request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return store.save_research_evidence(run)
    raise HTTPException(
        status_code=422,
        detail=(
            "optimization research evidence must be produced by the research spine; "
            "provide symbols and a sweep instead of client-authored counts"
        ),
    )


@router.get("/api/v1/optimization/runs/{run_id}", response_model=OptimizationRun)
def get_optimization_run(run_id: UUID, store: ResearchStoreDependency) -> OptimizationRun:
    return _load_typed(store, run_id, OptimizationRun)


@router.post("/api/v1/optimization/runs/{run_id}/save-risk-plan", response_model=SaveRiskPlanDraftResponse)
def save_optimization_winner_as_risk_plan(
    run_id: UUID,
    request: SaveRiskPlanDraftRequest,
    store: ResearchStoreDependency,
) -> SaveRiskPlanDraftResponse:
    run = _load_typed(store, run_id, OptimizationRun)
    metrics = run.best_metrics
    parameters = dict(metrics.get("best_parameters") or run.best_parameters)
    if not parameters:
        raise HTTPException(status_code=422, detail="optimization run has no winner parameters to save")
    return _save_recommended_risk_plan(
        store=store,
        source_run_id=run_id,
        source=RiskPlanSource.OPTIMIZATION_GENERATED,
        name=request.name or "Optimization Generated Risk Plan",
        description=request.description
        or "Draft RiskPlan saved from an Optimization winner. Requires Walk-Forward validation before use.",
        created_by=request.created_by,
        parameters=parameters,
        ai_summary="Optimization-generated draft. Hypothesis only; validate with Walk-Forward before activation.",
    )


@router.delete("/api/v1/optimization/runs/{run_id}", response_model=OptimizationRun)
def archive_optimization_run(run_id: UUID, store: ResearchStoreDependency) -> OptimizationRun:
    run = _load_typed(store, run_id, OptimizationRun)
    archived = run.model_copy(update={"best_metrics": _with_status(run.best_metrics, "archived")})
    return store.save_research_evidence(archived)


@router.get("/api/v1/walk-forward/runs", response_model=WalkForwardRunListResponse)
def list_walk_forward_runs(store: ResearchStoreDependency) -> WalkForwardRunListResponse:
    return WalkForwardRunListResponse(runs=_list_typed(store, "walk_forward_run", WalkForwardRun))


@router.post("/api/v1/walk-forward/runs", response_model=WalkForwardRun)
def create_walk_forward_run(request: WalkForwardRunRequest, store: ResearchStoreDependency) -> WalkForwardRun:
    symbols = tuple(s for s in request.symbols if s)
    if symbols:
        if request.start is None or request.end is None:
            raise HTTPException(
                status_code=422,
                detail="start and end are required for spine-driven walk-forward runs",
            )
        if request.initial_capital <= 0:
            raise HTTPException(
                status_code=422,
                detail="initial_capital must be positive when symbols are provided",
            )
        configure_data_center_persistence(store)
        ingest_service = HistoricalBarIngestService(
            store=store,
            sources={"yahoo": YahooBarsSource(), "alpaca": alpaca_bars_source_from_runtime(store)},
        )
        from backend.app.research.walk_forward import (
            WalkForwardExecutionRequest,
            WalkForwardExecutionService,
        )
        from backend.app.research.walk_forward.service import (
            WalkForwardSweepConfig,
            WalkForwardSweepParameter,
        )
        from backend.app.research.walk_forward.window_planner import LengthSpec
        from backend.app.research.backtests.monte_carlo import MonteCarloConfig

        def _length_spec(payload: JsonDict) -> LengthSpec:
            return LengthSpec(unit=payload.get("unit", "days"), value=int(payload.get("value", 180)))

        def _sweep(payload: JsonDict | None) -> WalkForwardSweepConfig | None:
            if not payload or not payload.get("enabled"):
                return None
            params = tuple(
                WalkForwardSweepParameter(field=p["field"], values=tuple(p["values"]))
                for p in payload.get("parameters", [])
            )
            base_id = payload.get("base_risk_plan_version_id")
            return WalkForwardSweepConfig(
                enabled=True,
                base_risk_plan_version_id=UUID(base_id) if base_id else None,
                parameters=params,
            )

        wf_request = WalkForwardExecutionRequest(
            strategy_id=request.strategy_id,
            strategy_version_id=request.strategy_version_id,
            strategy_controls_version_id=_required_component_id(
                request.strategy_controls_version_id,
                "strategy_controls_version_id",
                "walk-forward",
            ),
            execution_plan_version_id=_required_component_id(
                request.execution_plan_version_id,
                "execution_plan_version_id",
                "walk-forward",
            ),
            symbols=symbols,
            start=request.start,
            end=request.end,
            initial_capital=request.initial_capital,
            cost_model=request.cost_model,
            timeframe=request.timeframe,
            source=request.source,  # type: ignore[arg-type]
            adjustment_policy=request.adjustment_policy,  # type: ignore[arg-type]
            window_mode=request.window_mode,  # type: ignore[arg-type]
            is_length=_length_spec(request.is_length),
            oos_length=_length_spec(request.oos_length),
            step=_length_spec(request.step) if request.step else None,
            max_folds=request.max_folds,
            selection_criterion=request.selection_criterion,  # type: ignore[arg-type]
            sweep=_sweep(request.sweep),
            monte_carlo=MonteCarloConfig(**request.monte_carlo) if request.monte_carlo else None,
            fold_pass_threshold_sharpe=request.fold_pass_threshold_sharpe,
            score_weights={k: float(v) for k, v in request.score_weights.items()} if request.score_weights else None,
            ship_thresholds={k: float(v) for k, v in request.ship_thresholds.items()} if request.ship_thresholds else None,
        )
        try:
            run = WalkForwardExecutionService(
                strategy_lookup=_get_strategy_lookup(),
                ingest_service=ingest_service,
                store=store,
                risk_decision_sink=store,
            ).create_run(wf_request)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return store.save_research_evidence(run)
    raise HTTPException(
        status_code=422,
        detail=(
            "walk-forward research evidence must be produced by the research spine; "
            "provide symbols/window inputs instead of client-authored counts"
        ),
    )


@router.get("/api/v1/walk-forward/runs/{run_id}", response_model=WalkForwardRun)
def get_walk_forward_run(run_id: UUID, store: ResearchStoreDependency) -> WalkForwardRun:
    return _load_typed(store, run_id, WalkForwardRun)


@router.post("/api/v1/walk-forward/runs/{run_id}/save-risk-plan", response_model=SaveRiskPlanDraftResponse)
def save_walk_forward_recommendation_as_risk_plan(
    run_id: UUID,
    request: SaveRiskPlanDraftRequest,
    store: ResearchStoreDependency,
) -> SaveRiskPlanDraftResponse:
    run = _load_typed(store, run_id, WalkForwardRun)
    recommendation = run.metrics.get("recommended_risk_plan") or {}
    parameters = dict(recommendation.get("parameters") or {})
    if not parameters:
        raise HTTPException(status_code=422, detail="walk-forward run has no recommended RiskPlan parameters to save")
    return _save_recommended_risk_plan(
        store=store,
        source_run_id=run_id,
        source=RiskPlanSource.WALK_FORWARD_RECOMMENDED,
        name=request.name or "Walk-Forward Recommended Risk Plan",
        description=request.description or "Draft RiskPlan saved from a Walk-Forward recommendation.",
        created_by=request.created_by,
        parameters=parameters,
        ai_summary=str(recommendation.get("explanation") or "Walk-Forward recommended draft."),
    )


@router.delete("/api/v1/walk-forward/runs/{run_id}", response_model=WalkForwardRun)
def archive_walk_forward_run(run_id: UUID, store: ResearchStoreDependency) -> WalkForwardRun:
    run = _load_typed(store, run_id, WalkForwardRun)
    archived = run.model_copy(update={"metrics": _with_status(run.metrics, "archived")})
    return store.save_research_evidence(archived)


def _save_recommended_risk_plan(
    *,
    store: Any,
    source_run_id: UUID,
    source: RiskPlanSource,
    name: str,
    description: str,
    created_by: str | None,
    parameters: dict[str, Any],
    ai_summary: str,
) -> SaveRiskPlanDraftResponse:
    now = utc_now()
    config = _risk_plan_config_from_recommendation(parameters)
    evidence_lineage = _risk_plan_evidence_lineage(
        store=store,
        source_run_id=source_run_id,
        source=source,
        parameters=parameters,
    )
    risk_plan = RiskPlan(
        name=name,
        description=description,
        status=RiskPlanStatus.DRAFT,
        risk_score=_risk_score_from_config(config),
        risk_tier=_risk_tier_from_config(config),
        version=1,
        created_at=now,
        updated_at=now,
        created_by=created_by,
        ai_generated=False,
        ai_summary=ai_summary,
        source=source,
        source_run_id=source_run_id,
        source_evidence_type=evidence_lineage.get("source_evidence_type"),
        evidence_lineage=evidence_lineage,
    )
    version = RiskPlanVersion(
        risk_plan_id=risk_plan.risk_plan_id,
        version=1,
        status=RiskPlanVersionStatus.DRAFT,
        config=config,
        created_at=now,
    )
    store.save_risk_plan(risk_plan)
    store.save_risk_plan_version(version)
    return SaveRiskPlanDraftResponse(
        risk_plan=risk_plan,
        risk_plan_version=version,
        source_run_id=source_run_id,
    )


def _risk_plan_evidence_lineage(
    *,
    store: Any,
    source_run_id: UUID,
    source: RiskPlanSource,
    parameters: dict[str, Any],
) -> JsonDict:
    try:
        evidence = store.load_research_evidence(source_run_id)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=422,
            detail=f"cannot save research-derived RiskPlan without source evidence: {source_run_id}",
        ) from exc
    lineage: JsonDict = {
        "source_run_id": str(source_run_id),
        "source": source.value,
        "source_evidence_type": evidence.__class__.__name__,
        "strategy_id": str(evidence.strategy_id),
        "strategy_version_id": str(evidence.strategy_version_id),
        "parameters": dict(parameters),
    }
    artifact_id = getattr(evidence, "artifact_id", None)
    deployment_snapshot_id = getattr(evidence, "deployment_snapshot_id", None)
    if artifact_id is not None:
        lineage["artifact_id"] = str(artifact_id)
    if deployment_snapshot_id is not None:
        lineage["deployment_snapshot_id"] = str(deployment_snapshot_id)
    artifact = None
    if hasattr(store, "load_research_run_artifact_for_run"):
        try:
            artifact = store.load_research_run_artifact_for_run(source_run_id)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=422,
                detail=(
                    "cannot save research-derived RiskPlan without immutable "
                    f"ResearchRunArtifact lineage: {source_run_id}"
                ),
            ) from exc
    if artifact is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "cannot save research-derived RiskPlan without immutable "
                f"ResearchRunArtifact lineage: {source_run_id}"
            ),
        )
    snapshot = artifact.deployment_snapshot
    lineage["artifact_id"] = str(artifact.artifact_id)
    lineage["deployment_snapshot_id"] = str(snapshot.snapshot_id)
    lineage["strategy_controls_version_id"] = str(snapshot.strategy_controls_version_id)
    lineage["execution_plan_version_id"] = str(snapshot.execution_plan_version_id)
    lineage["risk_plan_version_id"] = str(snapshot.risk_plan_version_id)
    lineage["symbols"] = list(snapshot.symbols)
    return lineage


def _risk_plan_config_from_recommendation(parameters: dict[str, Any]) -> RiskPlanConfig:
    payload: dict[str, Any] = {}
    for key in (
        "fixed_shares",
        "fixed_notional",
        "risk_per_trade_pct",
        "account_allocation_pct",
        "max_position_pct_of_equity",
        "max_position_notional",
        "max_symbol_exposure_pct",
        "max_sector_exposure_pct",
        "max_gross_exposure_pct",
        "max_net_exposure_pct",
        "max_daily_loss_pct",
        "max_drawdown_pct",
        "max_open_risk_pct",
        "max_trades_per_day",
        "cooldown_after_loss_minutes",
    ):
        if parameters.get(key) is not None:
            payload[key] = parameters[key]
    if parameters.get("max_open_positions") is not None:
        payload["max_open_positions"] = parameters["max_open_positions"]
    elif parameters.get("max_positions") is not None:
        payload["max_open_positions"] = parameters["max_positions"]

    if payload.get("fixed_shares") is not None:
        payload["sizing_method"] = "fixed_shares"
    elif payload.get("fixed_notional") is not None:
        payload["sizing_method"] = "fixed_notional"
    elif payload.get("account_allocation_pct") is not None:
        payload["sizing_method"] = "account_percent"
    else:
        payload["sizing_method"] = "risk_percent"
        payload.setdefault("risk_per_trade_pct", 1.0)

    payload.setdefault("fractional_quantity_allowed", True)
    payload.setdefault("whole_share_rounding", "floor")
    payload.setdefault("min_quantity", 1)
    payload.setdefault("stop_required", True)
    payload.setdefault("reject_if_no_stop", True)
    payload.setdefault("default_stop_policy", {"kind": "recommendation_import", "source": "research"})
    payload.setdefault("target_required", False)
    payload.setdefault("runner_allowed", True)
    payload.setdefault("allow_scale_in", False)
    payload.setdefault("allow_scale_out", True)
    payload.setdefault("allow_short", False)
    payload.setdefault("allow_extended_hours", False)
    return RiskPlanConfig.model_validate(payload)


def _risk_score_from_config(config: RiskPlanConfig) -> int:
    risk_pct = config.risk_per_trade_pct or 0
    open_positions = config.max_open_positions or 1
    score = 5
    if risk_pct <= 0.5 and open_positions <= 3:
        score = 3
    elif risk_pct >= 2 or open_positions >= 8 or config.allow_short or config.allow_extended_hours:
        score = 8
    return score


def _risk_tier_from_config(config: RiskPlanConfig) -> RiskPlanTier:
    score = _risk_score_from_config(config)
    if score <= 4:
        return RiskPlanTier.CONSERVATIVE
    if score >= 7:
        return RiskPlanTier.AGGRESSIVE
    return RiskPlanTier.BALANCED


def _list_typed(store: Any, evidence_type: str, model: type[Any]) -> tuple[Any, ...]:
    return tuple(item for item in store.list_research_evidence(evidence_type=evidence_type) if isinstance(item, model))


def _load_typed(store: Any, evidence_id: UUID, model: type[Any]) -> Any:
    try:
        evidence = store.load_research_evidence(evidence_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown research run: {evidence_id}") from exc
    if not isinstance(evidence, model):
        raise HTTPException(status_code=404, detail=f"research run {evidence_id} is not a {model.__name__}")
    return evidence


def _with_status(metrics: JsonDict, status: str, *, reason: str | None = None) -> JsonDict:
    updated = dict(metrics)
    updated["status"] = status
    updated["status_updated_at"] = utc_now().isoformat()
    if reason is not None:
        updated["status_reason"] = reason
    return updated


def _sim_lab_stream_request(websocket: WebSocket) -> SimLabBatchRunApiRequest:
    query = websocket.query_params
    universe = tuple(symbol.strip().upper() for symbol in (query.get("universe") or "").split(",") if symbol.strip())
    payload = {
        "strategy_id": _required_query(query, "strategy_id"),
        "strategy_version_id": _required_query(query, "strategy_version_id"),
        "strategy_controls_version_id": _required_query(query, "strategy_controls_version_id"),
        "execution_plan_version_id": _required_query(query, "execution_plan_version_id"),
        "risk_plan_version_id": _required_query(query, "risk_plan_version_id"),
        "scenario_name": _required_query(query, "scenario_name"),
        "universe": universe,
        "timeframe": query.get("timeframe") or "5m",
        "start": _required_query(query, "start"),
        "end": _required_query(query, "end"),
        "initial_cash": float(query.get("initial_cash") or 100_000),
        "bar_count": int(query.get("bar_count") or 12),
    }
    return SimLabBatchRunApiRequest.model_validate(payload)


def _required_stream_component_id(value: UUID | None, field_name: str) -> UUID:
    if value is None:
        raise ValueError(f"{field_name} is required for spine-driven sim lab streams")
    return value


def _required_query(query: Any, name: str) -> str:
    value = query.get(name)
    if value is None or not str(value).strip():
        raise ValueError(f"{name} is required")
    return str(value)

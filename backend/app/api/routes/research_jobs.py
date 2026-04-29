"""Async research-run jobs API.

POST endpoints (one per kind) enqueue a ResearchJob and return immediately
with the JobRecord (status=queued). The runner dispatches the actual run
through the same service the sync POST routes use; per-fold (WF) and
per-candidate (Optimization) progress flows back via JobReporter.

GET endpoints expose status + progress + result_run_id; cancel is a single
POST. Frontend polls the list endpoint every few seconds while the JobMonitor
is open.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.data_center.historical_catalog import (
    configure_persistence as configure_data_center_persistence,
)
from backend.app.data_center.ingest_service import (
    HistoricalBarIngestService,
    YahooBarsSource,
    alpaca_bars_source_from_runtime,
)
from backend.app.domain import (
    ResearchJob,
    ResearchJobKind,
    research_job_summary,
)
from backend.app.domain._base import JsonDict
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.research.backtests.monte_carlo import MonteCarloConfig
from backend.app.research.jobs import JobReporter, ResearchJobRunner, build_dispatcher


router = APIRouter(tags=["research-jobs"])


class ResearchJobSubmitRequest(BaseModel):
    """Wraps a sync-POST payload (`request`) plus optional metadata."""

    model_config = ConfigDict(extra="forbid")

    request: JsonDict
    operator_session_id: str | None = None
    metadata: JsonDict = Field(default_factory=dict)


class ResearchJobSummary(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    job_id: str
    kind: str
    status: str
    progress_current: int = 0
    progress_total: int = 0
    progress_label: str = ""
    result_run_id: str | None = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class ResearchJobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: tuple[ResearchJobSummary, ...] = ()


def get_research_job_store() -> SQLiteRuntimeStore:
    return SQLiteRuntimeStore(get_runtime_db_path())


def _dependency(default: object) -> object:
    return Depends(default)


JobStoreDependency = Annotated[Any, _dependency(get_research_job_store)]


# ---------------------------------------------------------------------------
# Module-level runner
# ---------------------------------------------------------------------------
# We instantiate the runner lazily on first use, sharing it across requests
# (the singleton ThreadPoolExecutor lives for the lifetime of the process).
# Tests that need isolation can monkey-patch ``_get_runner``.

_RUNNER: ResearchJobRunner | None = None


def _get_runner() -> ResearchJobRunner:
    global _RUNNER
    if _RUNNER is None:
        _RUNNER = _build_runner()
    return _RUNNER


def _build_runner() -> ResearchJobRunner:
    store = SQLiteRuntimeStore(get_runtime_db_path())
    return ResearchJobRunner(store=store, dispatchers=build_dispatcher(
        backtest=_dispatch_backtest,
        walk_forward=_dispatch_walk_forward,
        optimization=_dispatch_optimization,
    ))


def _resolve_strategy_lookup() -> Any:
    from backend.app.api.routes.strategies import get_strategy_service

    return get_strategy_service()


def _ingest_service(store: SQLiteRuntimeStore) -> HistoricalBarIngestService:
    return HistoricalBarIngestService(
        store=store,
        sources={"yahoo": YahooBarsSource(), "alpaca": alpaca_bars_source_from_runtime(store)},
    )


# ---------------------------------------------------------------------------
# Per-kind dispatchers
# ---------------------------------------------------------------------------


def _dispatch_backtest(job: ResearchJob, reporter: JobReporter) -> UUID:
    from backend.app.research.backtests import (
        BacktestExecutionRequest,
        BacktestExecutionService,
    )

    request = job.request
    store = SQLiteRuntimeStore(get_runtime_db_path())
    configure_data_center_persistence(store)
    service = BacktestExecutionService(
        strategy_lookup=_resolve_strategy_lookup(),
        ingest_service=_ingest_service(store),
        store=store,
        risk_decision_sink=store,
    )
    reporter.update(current=0, total=1, label="run", message="backtest starting")
    run = service.create_run(
        BacktestExecutionRequest(
            strategy_id=UUID(str(request["strategy_id"])),
            strategy_version_id=UUID(str(request["strategy_version_id"])),
            risk_plan_version_id=(
                UUID(str(request["risk_plan_version_id"])) if request.get("risk_plan_version_id") else None
            ),
            symbols=tuple(request.get("symbols") or request.get("universe") or ()),
            start=_iso(request["start"]),
            end=_iso(request["end"]),
            initial_capital=float(request["initial_capital"]),
            cost_model=dict(request.get("cost_model") or {}),
            source=request.get("source", "yahoo"),
            timeframe=request.get("timeframe", "1d"),
            adjustment_policy=request.get("adjustment_policy", "split_dividend_adjusted"),
            monte_carlo=request.get("monte_carlo"),
        )
    )
    persisted = store.save_research_evidence(run)
    reporter.update(current=1, total=1, label="run", message="backtest complete")
    return persisted.run_id


def _dispatch_walk_forward(job: ResearchJob, reporter: JobReporter) -> UUID:
    from backend.app.research.walk_forward import (
        WalkForwardExecutionRequest,
        WalkForwardExecutionService,
    )
    from backend.app.research.walk_forward.service import (
        WalkForwardSweepConfig,
        WalkForwardSweepParameter,
    )
    from backend.app.research.walk_forward.window_planner import LengthSpec

    request = job.request
    store = SQLiteRuntimeStore(get_runtime_db_path())
    configure_data_center_persistence(store)
    service = WalkForwardExecutionService(
        strategy_lookup=_resolve_strategy_lookup(),
        ingest_service=_ingest_service(store),
        store=store,
        risk_decision_sink=store,
    )

    def _length(payload: JsonDict) -> LengthSpec:
        return LengthSpec(unit=payload.get("unit", "days"), value=int(payload.get("value", 180)))

    sweep_payload = request.get("sweep") or {}
    sweep = None
    if sweep_payload.get("enabled"):
        sweep = WalkForwardSweepConfig(
            enabled=True,
            base_risk_plan_version_id=(
                UUID(str(sweep_payload["base_risk_plan_version_id"]))
                if sweep_payload.get("base_risk_plan_version_id")
                else None
            ),
            parameters=tuple(
                WalkForwardSweepParameter(field=p["field"], values=tuple(p["values"]))
                for p in sweep_payload.get("parameters", [])
            ),
        )

    wf_request = WalkForwardExecutionRequest(
        strategy_id=UUID(str(request["strategy_id"])),
        strategy_version_id=UUID(str(request["strategy_version_id"])),
        symbols=tuple(request["symbols"]),
        start=_iso(request["start"]),
        end=_iso(request["end"]),
        initial_capital=float(request["initial_capital"]),
        cost_model=dict(request.get("cost_model") or {}),
        timeframe=request.get("timeframe", "1d"),
        source=request.get("source", "yahoo"),
        adjustment_policy=request.get("adjustment_policy", "split_dividend_adjusted"),
        window_mode=request.get("window_mode", "rolling"),
        is_length=_length(request.get("is_length") or {"unit": "days", "value": 180}),
        oos_length=_length(request.get("oos_length") or {"unit": "days", "value": 60}),
        step=_length(request["step"]) if request.get("step") else None,
        max_folds=request.get("max_folds"),
        selection_criterion=request.get("selection_criterion", "max_dd_bounded_sharpe"),
        sweep=sweep,
        monte_carlo=MonteCarloConfig(**request["monte_carlo"]) if request.get("monte_carlo") else None,
        fold_pass_threshold_sharpe=float(request.get("fold_pass_threshold_sharpe", 0.0)),
        score_weights=request.get("score_weights"),
        ship_thresholds=request.get("ship_thresholds"),
        progress_reporter=reporter,
    )
    run = service.create_run(wf_request)
    persisted = store.save_research_evidence(run)
    return persisted.run_id


def _dispatch_optimization(job: ResearchJob, reporter: JobReporter) -> UUID:
    from backend.app.research.optimization import (
        OptimizationExecutionRequest,
        OptimizationExecutionService,
        OptimizationSweepConfig,
        OptimizationSweepParameter,
    )

    request = job.request
    store = SQLiteRuntimeStore(get_runtime_db_path())
    configure_data_center_persistence(store)
    service = OptimizationExecutionService(
        strategy_lookup=_resolve_strategy_lookup(),
        ingest_service=_ingest_service(store),
        store=store,
        risk_decision_sink=store,
    )
    sweep_payload = request.get("sweep") or {}
    sweep = OptimizationSweepConfig(
        base_risk_plan_version_id=(
            UUID(str(sweep_payload["base_risk_plan_version_id"]))
            if sweep_payload.get("base_risk_plan_version_id")
            else None
        ),
        parameters=tuple(
            OptimizationSweepParameter(field=p["field"], values=tuple(p["values"]))
            for p in sweep_payload.get("parameters", [])
        ),
    )
    opt_request = OptimizationExecutionRequest(
        strategy_id=UUID(str(request["strategy_id"])),
        strategy_version_id=UUID(str(request["strategy_version_id"])),
        symbols=tuple(request["symbols"]),
        start=_iso(request["start"]),
        end=_iso(request["end"]),
        initial_capital=float(request["initial_capital"]),
        cost_model=dict(request.get("cost_model") or {}),
        sweep=sweep,
        timeframe=request.get("timeframe", "1d"),
        source=request.get("source", "yahoo"),
        adjustment_policy=request.get("adjustment_policy", "split_dividend_adjusted"),
        method=request.get("method", "grid"),
        selection_criterion=request.get("selection_criterion", "max_dd_bounded_sharpe"),
        max_candidates=request.get("max_candidates", 200),
        seed=int(request.get("seed", 42)),
        monte_carlo=MonteCarloConfig(**request["monte_carlo"]) if request.get("monte_carlo") else None,
        runners_up_threshold_pct=float(request.get("runners_up_threshold_pct", 0.05)),
        walk_forward_handoff_top_k=int(request.get("walk_forward_handoff_top_k", 3)),
        heatmap_dimensions=tuple(request["heatmap_dimensions"]) if request.get("heatmap_dimensions") else None,
        progress_reporter=reporter,
    )
    run = service.create_run(opt_request)
    persisted = store.save_research_evidence(run)
    return persisted.run_id


def _iso(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _summary(job: ResearchJob) -> ResearchJobSummary:
    return ResearchJobSummary(**research_job_summary(job))


@router.post("/api/v1/research/jobs/backtest", response_model=ResearchJobSummary)
def submit_backtest_job(payload: ResearchJobSubmitRequest, store: JobStoreDependency) -> ResearchJobSummary:
    return _submit(kind=ResearchJobKind.BACKTEST, payload=payload, store=store)


@router.post("/api/v1/research/jobs/walk-forward", response_model=ResearchJobSummary)
def submit_walk_forward_job(payload: ResearchJobSubmitRequest, store: JobStoreDependency) -> ResearchJobSummary:
    return _submit(kind=ResearchJobKind.WALK_FORWARD, payload=payload, store=store)


@router.post("/api/v1/research/jobs/optimization", response_model=ResearchJobSummary)
def submit_optimization_job(payload: ResearchJobSubmitRequest, store: JobStoreDependency) -> ResearchJobSummary:
    return _submit(kind=ResearchJobKind.OPTIMIZATION, payload=payload, store=store)


def _submit(
    *,
    kind: ResearchJobKind,
    payload: ResearchJobSubmitRequest,
    store: SQLiteRuntimeStore,
) -> ResearchJobSummary:
    runner = _get_runner()
    try:
        job = runner.submit(
            kind=kind,
            request=payload.request,
            operator_session_id=payload.operator_session_id,
            metadata=payload.metadata,
        )
    except Exception as exc:  # noqa: BLE001 — surface as 422 to the operator
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _summary(job)


@router.get("/api/v1/research/jobs", response_model=ResearchJobListResponse)
def list_research_jobs(
    store: JobStoreDependency,
    status: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> ResearchJobListResponse:
    jobs = store.list_research_jobs(status=status, kind=kind, limit=limit)
    return ResearchJobListResponse(jobs=tuple(_summary(j) for j in jobs))


@router.get("/api/v1/research/jobs/{job_id}", response_model=ResearchJobSummary)
def get_research_job(job_id: UUID, store: JobStoreDependency) -> ResearchJobSummary:
    try:
        job = store.load_research_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _summary(job)


@router.post("/api/v1/research/jobs/{job_id}/cancel", response_model=ResearchJobSummary)
def cancel_research_job(job_id: UUID, store: JobStoreDependency) -> ResearchJobSummary:
    try:
        job = _get_runner().request_cancel(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _summary(job)

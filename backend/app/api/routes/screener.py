"""Screener REST API.

Routes:

- ``GET    /api/v1/screeners``                            — list saved Screeners
- ``POST   /api/v1/screeners``                            — create Screener + first version
- ``GET    /api/v1/screeners/presets``                    — built-in universe presets
- ``GET    /api/v1/screeners/metrics``                    — metric vocabulary for the criteria editor
- ``GET    /api/v1/screeners/{id}``                       — detail (Screener + all versions + last run summary)
- ``PATCH  /api/v1/screeners/{id}``                       — edit Screener identity (name / description / tags / status)
- ``POST   /api/v1/screeners/{id}/delete``                — delete (cascades versions + runs)
- ``POST   /api/v1/screeners/{id}/versions``              — add a new version
- ``POST   /api/v1/screeners/{id}/run``                   — execute the screener (sync; results persisted)
- ``GET    /api/v1/screeners/{id}/runs``                  — list runs for a screener
- ``GET    /api/v1/screeners/runs/{run_id}``              — read a run + its full results
- ``POST   /api/v1/screeners/runs/{run_id}/save-as-watchlist`` — convert matched symbols to a new Watchlist

Doctrine guards:

- The Screener never mutates Watchlists; ``save-as-watchlist`` POSTs a
  CREATE through the existing ``WatchlistService`` exactly like any other
  operator-driven Watchlist creation.
- Runs are immutable. Re-running spawns a new ``ScreenerRun``.
- No deployment / broker / account side effects.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.app.screener import (
    Screener,
    ScreenerCriterion,
    ScreenerExpression,
    ScreenerExecutionService,
    ScreenerNotFoundError,
    ScreenerRun,
    ScreenerSourceError,
    ScreenerUniverseSource,
    ScreenerValidationError,
    ScreenerVersion,
)
from backend.app.screener.ai import ScreenerAIInterpretRequest, ScreenerAIInterpretResponse, interpret_screener_prompt
from backend.app.screener.domain import ScreenerMetric
from backend.app.screener.fields import api_field_definitions
from backend.app.screener.presets import list_presets
from backend.app.screener.templates import list_market_lists, list_templates, version_from_template


def get_screener_service() -> ScreenerExecutionService:
    from backend.app.screener.runtime import create_screener_service_from_environment

    return create_screener_service_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/screeners", tags=["screener"])
market_lists_router = APIRouter(prefix="/api/v1/market-lists", tags=["market-lists"])

ServiceDep = Annotated[Any, _dependency(get_screener_service)]


def _err(status: int, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail=msg)


# -------- request / response models -----------------------------------


class ScreenerCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    tags: tuple[str, ...] = Field(default_factory=tuple)
    universe_source: ScreenerUniverseSource
    criteria: tuple[ScreenerCriterion, ...] = Field(default_factory=tuple)
    expression: ScreenerExpression | None = None
    timeframe: str = "1d"
    source_preference: Literal["auto", "alpaca", "data_center"] = "auto"
    sort_metric: ScreenerMetric | None = None
    sort_descending: bool = True
    max_results: int = Field(default=200, ge=1, le=1000)


class ScreenerPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=120)
    description: str | None = None
    tags: tuple[str, ...] | None = None
    status: str | None = None


class ScreenerRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_id: UUID | None = None
    operator_session_id: str | None = None


class ScreenerRerunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator_session_id: str | None = None


class ScreenerFromTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_key: str = Field(min_length=1)
    name: str | None = Field(default=None, max_length=120)
    description: str | None = None
    tags: tuple[str, ...] = Field(default_factory=tuple)


class SaveAsWatchlistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    only_matched: bool = True
    kind: str = "static"


class ScreenerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screener: Screener
    versions: tuple[ScreenerVersion, ...] = Field(default_factory=tuple)
    last_run: ScreenerRun | None = None


class ScreenerListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screeners: tuple[Screener, ...] = Field(default_factory=tuple)


class ScreenerRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runs: tuple[ScreenerRun, ...] = Field(default_factory=tuple)


class SaveAsWatchlistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    watchlist_id: UUID
    name: str
    symbol_count: int


class PresetsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    presets: tuple[dict[str, Any], ...]


class MetricsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: tuple[dict[str, Any], ...]


class FieldsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: tuple[dict[str, Any], ...]


class TemplatesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    templates: tuple[dict[str, Any], ...]


class MarketListsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    market_lists: tuple[dict[str, Any], ...]


class MarketListRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    screener: Screener
    version: ScreenerVersion
    run: ScreenerRun


class RunDiffResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    against_run_id: UUID
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    stayed: tuple[str, ...] = ()
    newly_failed: tuple[str, ...] = ()
    reason_changes: tuple[dict[str, Any], ...] = ()


# -------- routes -------------------------------------------------------


@router.get("", response_model=ScreenerListResponse)
def list_screeners(service: ServiceDep) -> ScreenerListResponse:
    return ScreenerListResponse(screeners=service.list_screeners())


@router.post("", response_model=ScreenerResponse, status_code=201)
def create_screener(request: ScreenerCreateRequest, service: ServiceDep) -> ScreenerResponse:
    from uuid import uuid4

    screener_id = uuid4()
    version = ScreenerVersion(
        screener_id=screener_id,
        name=request.name,
        description=request.description,
        universe_source=request.universe_source,
        criteria=request.criteria,
        expression=request.expression,
        timeframe=request.timeframe,  # type: ignore[arg-type]
        source_preference=request.source_preference,  # type: ignore[arg-type]
        sort_metric=request.sort_metric,
        sort_descending=request.sort_descending,
        max_results=request.max_results,
    )
    try:
        screener, version = service.create_screener(
            name=request.name,
            description=request.description,
            version=version,
            tags=request.tags,
        )
    except ScreenerValidationError as exc:
        raise _err(422, str(exc)) from exc
    return ScreenerResponse(screener=screener, versions=(version,))


@router.get("/presets", response_model=PresetsResponse)
def list_screener_presets() -> PresetsResponse:
    return PresetsResponse(presets=list_presets())


@router.get("/metrics", response_model=MetricsResponse)
def list_screener_metrics() -> MetricsResponse:
    """Return the operator-readable metric vocabulary for the criteria editor."""
    metrics = (
        {"key": ScreenerMetric.PRICE.value, "label": "Last price", "unit": "$"},
        {"key": ScreenerMetric.AVG_VOLUME_20D.value, "label": "Avg volume (20d)", "unit": "shares"},
        {"key": ScreenerMetric.RELATIVE_VOLUME.value, "label": "Relative volume (today / 20d avg)", "unit": "x"},
        {"key": ScreenerMetric.GAP_PCT.value, "label": "Gap from prior close", "unit": "%"},
        {"key": ScreenerMetric.CHANGE_PCT.value, "label": "Today's change", "unit": "%"},
        {"key": ScreenerMetric.RSI_14.value, "label": "RSI(14)", "unit": "0..100"},
        {"key": ScreenerMetric.ATR_14_PCT.value, "label": "ATR(14) as % of price", "unit": "%"},
        {"key": ScreenerMetric.PRIOR_DAY_CLOSE.value, "label": "Prior day close", "unit": "$"},
        {"key": ScreenerMetric.PRIOR_DAY_RANGE_PCT.value, "label": "Prior day range %", "unit": "%"},
    )
    return MetricsResponse(metrics=metrics)


@router.get("/fields", response_model=FieldsResponse)
def list_screener_fields() -> FieldsResponse:
    return FieldsResponse(fields=api_field_definitions())


@router.get("/templates", response_model=TemplatesResponse)
def list_screener_templates() -> TemplatesResponse:
    return TemplatesResponse(templates=list_templates())


@router.post("/from-template", response_model=ScreenerResponse, status_code=201)
def create_screener_from_template(
    request: ScreenerFromTemplateRequest,
    service: ServiceDep,
) -> ScreenerResponse:
    from uuid import uuid4

    try:
        version = version_from_template(
            request.template_key,
            screener_id=uuid4(),
            name=request.name,
        )
    except KeyError as exc:
        raise _err(404, str(exc)) from exc
    screener, version = service.create_screener(
        name=request.name or version.name,
        description=request.description or version.description,
        version=version,
        tags=request.tags or version.tags,
    )
    return ScreenerResponse(screener=screener, versions=(version,))


@router.post("/ai/interpret", response_model=ScreenerAIInterpretResponse)
def interpret_ai_screener_prompt(request: ScreenerAIInterpretRequest) -> ScreenerAIInterpretResponse:
    return interpret_screener_prompt(request)


@router.get("/market-lists", response_model=MarketListsResponse)
def list_screener_market_lists() -> MarketListsResponse:
    return MarketListsResponse(market_lists=list_market_lists())


@market_lists_router.get("", response_model=MarketListsResponse)
def list_market_list_catalog() -> MarketListsResponse:
    return MarketListsResponse(market_lists=list_market_lists())


@market_lists_router.post("/{template_key}/run", response_model=MarketListRunResponse)
def run_market_list_template(
    template_key: str,
    service: ServiceDep,
) -> MarketListRunResponse:
    from uuid import uuid4

    try:
        version = version_from_template(template_key, screener_id=uuid4())
    except KeyError as exc:
        raise _err(404, str(exc)) from exc
    screener, version = service.create_screener(
        name=version.name,
        description=version.description,
        version=version,
        tags=version.tags,
    )
    run = service.run_screener(screener.id, version_id=version.id)
    return MarketListRunResponse(screener=screener, version=version, run=run)


@router.get("/runs/{run_id}", response_model=ScreenerRun)
def get_run(run_id: UUID, service: ServiceDep) -> ScreenerRun:
    try:
        return service.get_run(run_id)
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc


@router.post("/runs/{run_id}/rerun", response_model=ScreenerRun)
def rerun_screener(
    run_id: UUID,
    request: ScreenerRerunRequest,
    service: ServiceDep,
) -> ScreenerRun:
    try:
        return service.rerun(run_id, operator_session_id=request.operator_session_id)
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc


@router.get("/runs/{run_id}/diff", response_model=RunDiffResponse)
def diff_screener_runs(
    run_id: UUID,
    service: ServiceDep,
    against_run_id: UUID = Query(...),
) -> RunDiffResponse:
    try:
        payload = service.diff_runs(run_id, against_run_id=against_run_id)
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    return RunDiffResponse.model_validate(payload)


@router.post("/runs/{run_id}/save-as-watchlist", response_model=SaveAsWatchlistResponse)
def save_run_as_watchlist(
    run_id: UUID,
    request: SaveAsWatchlistRequest,
    service: ServiceDep,
) -> SaveAsWatchlistResponse:
    """Persist matched symbols as a new static Watchlist via WatchlistService.

    Doctrine: this never mutates an existing Watchlist; it creates a new
    one. The Screener service does not own Watchlist storage.
    """
    try:
        run = service.get_run(run_id)
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc

    rows = run.results
    if request.only_matched:
        rows = tuple(r for r in rows if r.matched)
    symbols = tuple(sorted({r.symbol for r in rows}))
    if not symbols:
        raise _err(422, "no symbols to save (run has zero matched results)")

    from backend.app.watchlists.runtime_service import (
        create_watchlist_service_from_environment,
    )
    from backend.app.watchlists.models import WatchlistDynamicRules, WatchlistKind, WatchlistWriteRequest

    watchlists = create_watchlist_service_from_environment()
    kind = request.kind.strip().lower()
    if kind not in {"static", "dynamic"}:
        raise _err(422, "kind must be static or dynamic")
    dynamic_rules = None
    if kind == "dynamic":
        dynamic_rules = WatchlistDynamicRules(
            source_type="screener_version",
            screener_id=run.screener_id,
            screener_version_id=run.screener_version_id,
            notes=f"Dynamic Watchlist from Screener run {run_id}",
        )
    created = watchlists.create_watchlist(
        WatchlistWriteRequest(
            name=request.name,
            description=request.description or f"Saved from Screener run {run_id}",
            kind=WatchlistKind.DYNAMIC if kind == "dynamic" else WatchlistKind.STATIC,
            static_symbols=symbols,
            dynamic_rules=dynamic_rules,
        )
    )
    return SaveAsWatchlistResponse(
        watchlist_id=created.watchlist_id,
        name=created.name,
        symbol_count=len(symbols),
    )


@router.get("/{screener_id}", response_model=ScreenerResponse)
def get_screener(screener_id: UUID, service: ServiceDep) -> ScreenerResponse:
    try:
        screener, versions = service.get_screener(screener_id)
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    last_run = None
    if screener.last_run_id is not None:
        try:
            last_run = service.get_run(screener.last_run_id)
        except ScreenerNotFoundError:
            last_run = None
    return ScreenerResponse(screener=screener, versions=versions, last_run=last_run)


@router.patch("/{screener_id}", response_model=ScreenerResponse)
def patch_screener(
    screener_id: UUID,
    request: ScreenerPatchRequest,
    service: ServiceDep,
) -> ScreenerResponse:
    try:
        screener, versions = service.get_screener(screener_id)
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    update: dict[str, Any] = {}
    if request.name is not None:
        update["name"] = request.name.strip()
    if request.description is not None:
        update["description"] = request.description
    if request.tags is not None:
        update["tags"] = request.tags
    if request.status is not None:
        if request.status not in {"draft", "active", "deprecated", "archived"}:
            raise _err(422, f"invalid status {request.status!r}")
        update["status"] = request.status
    updated = screener.model_copy(update=update)
    service._store.save_screener(updated)  # noqa: SLF001 — service has no patch sugar; accept here
    return ScreenerResponse(screener=updated, versions=versions)


@router.post("/{screener_id}/delete", status_code=204)
def delete_screener(screener_id: UUID, service: ServiceDep) -> None:
    try:
        service.delete_screener(screener_id)
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ScreenerValidationError as exc:
        raise _err(409, str(exc)) from exc


@router.post("/{screener_id}/archive", response_model=ScreenerResponse)
def archive_screener(screener_id: UUID, service: ServiceDep) -> ScreenerResponse:
    try:
        archived = service.archive_screener(screener_id)
        _, versions = service.get_screener(screener_id)
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    return ScreenerResponse(screener=archived, versions=versions)


@router.post("/{screener_id}/versions", response_model=ScreenerVersion)
def add_version(
    screener_id: UUID,
    request: ScreenerCreateRequest,
    service: ServiceDep,
) -> ScreenerVersion:
    try:
        version = service.add_version(
            screener_id,
            name=request.name,
            version_payload=ScreenerVersion(
                screener_id=screener_id,
                name=request.name,
                description=request.description,
                universe_source=request.universe_source,
                criteria=request.criteria,
                expression=request.expression,
                timeframe=request.timeframe,  # type: ignore[arg-type]
                source_preference=request.source_preference,  # type: ignore[arg-type]
                sort_metric=request.sort_metric,
                sort_descending=request.sort_descending,
                max_results=request.max_results,
            ),
        )
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ScreenerValidationError as exc:
        raise _err(422, str(exc)) from exc
    return version


@router.post("/{screener_id}/run", response_model=ScreenerRun)
def run_screener(
    screener_id: UUID,
    request: ScreenerRunRequest,
    service: ServiceDep,
) -> ScreenerRun:
    try:
        return service.run_screener(
            screener_id,
            version_id=request.version_id,
            operator_session_id=request.operator_session_id,
        )
    except ScreenerNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except ScreenerValidationError as exc:
        raise _err(422, str(exc)) from exc
    except ScreenerSourceError as exc:
        raise _err(502, str(exc)) from exc


@router.get("/{screener_id}/runs", response_model=ScreenerRunListResponse)
def list_runs_for_screener(
    screener_id: UUID,
    service: ServiceDep,
    limit: int = Query(default=50, ge=1, le=500),
) -> ScreenerRunListResponse:
    runs = service.list_runs(screener_id=screener_id, limit=limit)
    return ScreenerRunListResponse(runs=runs)


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()

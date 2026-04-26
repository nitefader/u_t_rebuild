"""Market-data API surface — services + pipelines + resolve."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.app.domain import TradingMode
from backend.app.market_data import (
    MarketDataCatalogError,
    MarketDataPipeline,
    MarketDataPipelineList,
    MarketDataPipelineWrite,
    MarketDataServiceList,
    MarketDataServiceRecord,
    MarketDataServiceWrite,
    PipelineRegistryError,
    ResolveMarketDataRequest,
    ResolverResult,
    ServicePurpose,
)
from backend.app.market_data.pipeline import MarketDataPipelineEdit

if TYPE_CHECKING:
    from backend.app.market_data import MarketDataPipelineRegistry, MarketDataServiceCatalog


def get_market_data_catalog() -> "MarketDataServiceCatalog":
    from backend.app.market_data.runtime import create_market_data_catalog_from_environment

    return create_market_data_catalog_from_environment()


def get_pipeline_registry() -> "MarketDataPipelineRegistry":
    from backend.app.market_data.runtime import create_pipeline_registry_from_environment

    return create_pipeline_registry_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/market-data", tags=["market-data"])


CatalogDependency = Annotated[Any, _dependency(get_market_data_catalog)]
PipelineDependency = Annotated[Any, _dependency(get_pipeline_registry)]


# ---------------------------------------------------------------------------
# Services (existing surface)
# ---------------------------------------------------------------------------


@router.get("/services", response_model=MarketDataServiceList)
def list_services(catalog: CatalogDependency) -> MarketDataServiceList:
    return catalog.list_services()


@router.post("/services", response_model=MarketDataServiceRecord)
def create_service(request: MarketDataServiceWrite, catalog: CatalogDependency) -> MarketDataServiceRecord:
    return catalog.create_service(request)


@router.get("/services/{service_id}", response_model=MarketDataServiceRecord)
def get_service(service_id: UUID, catalog: CatalogDependency) -> MarketDataServiceRecord:
    try:
        return catalog.get_service(service_id)
    except MarketDataCatalogError as exc:
        raise _operator_error(str(exc)) from exc


@router.put("/services/{service_id}", response_model=MarketDataServiceRecord)
def update_service(service_id: UUID, request: MarketDataServiceWrite, catalog: CatalogDependency) -> MarketDataServiceRecord:
    try:
        return catalog.update_service(service_id, request)
    except MarketDataCatalogError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/services/{service_id}/validate", response_model=MarketDataServiceRecord)
def validate_service(service_id: UUID, catalog: CatalogDependency) -> MarketDataServiceRecord:
    return catalog.validate_service(service_id)


@router.post("/services/{service_id}/set-default", response_model=MarketDataServiceRecord)
def set_default_service(service_id: UUID, catalog: CatalogDependency) -> MarketDataServiceRecord:
    """DEPRECATED. "Default" is a Pipeline concern (which stream is the
    canonical one for a provider), not a Service concern (a Service is
    just a credential record). Use POST /pipelines/{id}/set-default.

    This endpoint still mutates the legacy ``is_default`` flag for
    backward compat, but new clients should not call it. The frontend
    no longer surfaces the action.
    """
    try:
        return catalog.set_default(service_id)
    except MarketDataCatalogError as exc:
        raise _operator_error(str(exc)) from exc


class SetDefaultForRequest(BaseModel):
    """Replace the operator-driven ``default_for`` purpose tag set on a Service."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    purposes: tuple[ServicePurpose, ...] = ()


@router.post("/services/{service_id}/default-for", response_model=MarketDataServiceRecord)
def set_default_for_service(
    service_id: UUID, request: SetDefaultForRequest, catalog: CatalogDependency
) -> MarketDataServiceRecord:
    """Replace the ``default_for`` purpose tags on a Service.

    Single-canonical-default per purpose: any other Service holding one
    of the requested tags loses it. Replaces env-driven role selection
    (``ALPACA_USE_TEST_STREAM`` etc.) with operator-driven tagging.
    """
    try:
        return catalog.set_default_for(service_id, request.purposes)
    except MarketDataCatalogError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/services/{service_id}/disable", response_model=MarketDataServiceRecord)
def disable_service(service_id: UUID, catalog: CatalogDependency) -> MarketDataServiceRecord:
    return catalog.disable_service(service_id)


@router.post("/services/resolve", response_model=ResolverResult)
def resolve_service(
    request: ResolveMarketDataRequest,
    catalog: CatalogDependency,
    pipelines: PipelineDependency,
) -> ResolverResult:
    return catalog.resolve(request, pipeline_registry=pipelines)


# ---------------------------------------------------------------------------
# Pipelines (Phase 1 §11.3 deliverable — first-class MarketDataPipeline)
# ---------------------------------------------------------------------------


@router.get("/pipelines", response_model=MarketDataPipelineList)
def list_pipelines(pipelines: PipelineDependency) -> MarketDataPipelineList:
    return pipelines.list_pipelines()


@router.post("/pipelines", response_model=MarketDataPipeline)
def create_pipeline(
    request: MarketDataPipelineWrite,
    catalog: CatalogDependency,
    pipelines: PipelineDependency,
) -> MarketDataPipeline:
    """Create a Pipeline. If ``service_id`` is bound, ``provider`` is
    derived from the Service rather than trusted from the request — the
    FK is the source of truth, the denormalized field cannot drift."""
    request = _derive_provider_from_service(request, catalog)
    try:
        return pipelines.create_pipeline(request)
    except PipelineRegistryError as exc:
        raise _operator_error(str(exc)) from exc


def _derive_provider_from_service(
    request: MarketDataPipelineWrite,
    catalog: "MarketDataServiceCatalog",
) -> MarketDataPipelineWrite:
    if request.service_id is None:
        return request
    try:
        service = catalog.get_service(request.service_id)
    except MarketDataCatalogError as exc:
        raise _operator_error(str(exc)) from exc
    if service.provider == request.provider:
        return request
    return request.model_copy(update={"provider": service.provider})


@router.get("/pipelines/{pipeline_id}", response_model=MarketDataPipeline)
def get_pipeline(pipeline_id: UUID, pipelines: PipelineDependency) -> MarketDataPipeline:
    try:
        return pipelines.get_pipeline(pipeline_id)
    except PipelineRegistryError as exc:
        raise _operator_error(str(exc)) from exc


@router.put("/pipelines/{pipeline_id}", response_model=MarketDataPipeline)
def update_pipeline(
    pipeline_id: UUID,
    request: MarketDataPipelineEdit,
    pipelines: PipelineDependency,
) -> MarketDataPipeline:
    """Partial update: ``display_name`` and ``capabilities`` only.

    Identity changes are *not* available on this endpoint:
    - service rebind → ``POST /pipelines/{id}/attach-service``
    - data_feed / trading_mode change → disable this pipeline and
      create a new one (subscribers won't migrate silently).
    """
    try:
        return pipelines.update_pipeline(pipeline_id, request)
    except PipelineRegistryError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/pipelines/{pipeline_id}/set-default", response_model=MarketDataPipeline)
def set_default_pipeline(pipeline_id: UUID, pipelines: PipelineDependency) -> MarketDataPipeline:
    try:
        return pipelines.set_default_for_provider(pipeline_id)
    except PipelineRegistryError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/pipelines/{pipeline_id}/disable", response_model=MarketDataPipeline)
def disable_pipeline(pipeline_id: UUID, pipelines: PipelineDependency) -> MarketDataPipeline:
    try:
        return pipelines.disable_pipeline(pipeline_id)
    except PipelineRegistryError as exc:
        raise _operator_error(str(exc)) from exc


# ---------------------------------------------------------------------------
# Pipelines from a Service (R2-B explicit action)
# ---------------------------------------------------------------------------


class CreatePipelineFromServiceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    service_id: UUID
    trading_mode: TradingMode | None = None
    data_feed: str = "iex"
    display_name: str | None = None


class AttachServiceRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    service_id: UUID


@router.post("/pipelines/{pipeline_id}/attach-service", response_model=MarketDataPipeline)
def attach_service_to_pipeline(
    pipeline_id: UUID,
    request: AttachServiceRequest,
    catalog: CatalogDependency,
    pipelines: PipelineDependency,
) -> MarketDataPipeline:
    """Backfill ``service_id`` on a legacy v1 pipeline that loaded without one.

    Per DE round-3 B6: pre-R2-A pipelines load with ``service_id=None``
    and the operator had no path forward except delete-and-recreate.
    This endpoint binds the pipeline to a registered Service; the
    registry's ``(service_id, trading_mode, data_feed)`` invariant
    rejects bindings that would create a duplicate active stream.
    """
    try:
        catalog.get_service(request.service_id)
    except MarketDataCatalogError as exc:
        raise _operator_error(str(exc)) from exc
    try:
        return pipelines.attach_service_id(pipeline_id, request.service_id)
    except PipelineRegistryError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/pipelines/from-service", response_model=MarketDataPipeline)
def create_pipeline_from_service(
    request: CreatePipelineFromServiceRequest,
    catalog: CatalogDependency,
    pipelines: PipelineDependency,
) -> MarketDataPipeline:
    """Activate a Service as a streaming subscription (Pipeline).

    Replaces the implicit Pipeline creation that bootstrap-from-env used
    to do. The operator picks feed + mode explicitly. The
    ``(service_id, trading_mode, data_feed)`` invariant in the registry
    rejects creating a duplicate active pipeline for the same identity.
    """
    try:
        service = catalog.get_service(request.service_id)
    except MarketDataCatalogError as exc:
        raise _operator_error(str(exc)) from exc

    display_name = request.display_name or f"{service.name} · {request.data_feed}"
    write = MarketDataPipelineWrite(
        display_name=display_name,
        provider=service.provider,
        service_id=request.service_id,
        data_feed=request.data_feed,
        trading_mode=request.trading_mode,
    )
    try:
        return pipelines.create_pipeline(write)
    except PipelineRegistryError as exc:
        raise _operator_error(str(exc)) from exc


def _operator_error(message: str) -> Exception:
    return HTTPException(status_code=400, detail=message)


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()

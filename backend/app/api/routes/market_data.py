"""Market-data API surface — services + pipelines + resolve."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated
from uuid import UUID

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
)

if TYPE_CHECKING:
    from backend.app.market_data import MarketDataPipelineRegistry, MarketDataServiceCatalog

try:  # pragma: no cover
    from fastapi import APIRouter, Depends, HTTPException
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]


def get_market_data_catalog() -> "MarketDataServiceCatalog":
    from backend.app.market_data.runtime import create_market_data_catalog_from_environment

    return create_market_data_catalog_from_environment()


def get_pipeline_registry() -> "MarketDataPipelineRegistry":
    from backend.app.market_data.runtime import create_pipeline_registry_from_environment

    return create_pipeline_registry_from_environment()


def _dependency(default: object) -> object:
    if Depends is None:
        return default
    return Depends(default)


if APIRouter is None:
    from backend.app.api.routes.operations import FallbackRouter

    router = FallbackRouter(prefix="/api/v1/market-data", tags=["market-data"])
else:
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
    try:
        return catalog.set_default(service_id)
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
def create_pipeline(request: MarketDataPipelineWrite, pipelines: PipelineDependency) -> MarketDataPipeline:
    return pipelines.create_pipeline(request)


@router.get("/pipelines/{pipeline_id}", response_model=MarketDataPipeline)
def get_pipeline(pipeline_id: UUID, pipelines: PipelineDependency) -> MarketDataPipeline:
    try:
        return pipelines.get_pipeline(pipeline_id)
    except PipelineRegistryError as exc:
        raise _operator_error(str(exc)) from exc


@router.put("/pipelines/{pipeline_id}", response_model=MarketDataPipeline)
def update_pipeline(pipeline_id: UUID, request: MarketDataPipelineWrite, pipelines: PipelineDependency) -> MarketDataPipeline:
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


def _operator_error(message: str) -> Exception:
    if HTTPException is None:
        return MarketDataCatalogError(message)
    return HTTPException(status_code=400, detail=message)


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()

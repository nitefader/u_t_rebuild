from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated
from uuid import UUID

from backend.app.services import (
    AIServiceList,
    AIServiceRecord,
    AIServiceWrite,
    MarketDataServiceList,
    MarketDataServiceRecord,
    MarketDataServiceWrite,
    ResolveMarketDataRequest,
    ResolverResult,
    ServicesCenterError,
)

if TYPE_CHECKING:
    from backend.app.services import ServicesCenterService

try:  # pragma: no cover
    from fastapi import APIRouter, Depends, HTTPException
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]


def get_services_center_service() -> "ServicesCenterService":
    from backend.app.services.runtime_service import create_services_center_service_from_environment

    return create_services_center_service_from_environment()


def _dependency(default: object) -> object:
    if Depends is None:
        return default
    return Depends(default)


if APIRouter is None:
    from backend.app.api.routes.operations import FallbackRouter

    router = FallbackRouter(prefix="/api/v1/services", tags=["services"])
else:
    router = APIRouter(prefix="/api/v1/services", tags=["services"])


ServicesDependency = Annotated[Any, _dependency(get_services_center_service)]


@router.get("/market-data", response_model=MarketDataServiceList)
def list_market_data_services(service: ServicesDependency) -> MarketDataServiceList:
    return service.list_market_data_services()


@router.post("/market-data", response_model=MarketDataServiceRecord)
def create_market_data_service(request: MarketDataServiceWrite, service: ServicesDependency) -> MarketDataServiceRecord:
    return service.create_market_data_service(request)


@router.get("/market-data/{service_id}", response_model=MarketDataServiceRecord)
def get_market_data_service(service_id: UUID, service: ServicesDependency) -> MarketDataServiceRecord:
    try:
        return service.get_market_data_service(service_id)
    except ServicesCenterError as exc:
        raise _operator_error(str(exc)) from exc


@router.put("/market-data/{service_id}", response_model=MarketDataServiceRecord)
def update_market_data_service(service_id: UUID, request: MarketDataServiceWrite, service: ServicesDependency) -> MarketDataServiceRecord:
    try:
        return service.update_market_data_service(service_id, request)
    except ServicesCenterError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/market-data/{service_id}/validate", response_model=MarketDataServiceRecord)
def validate_market_data_service(service_id: UUID, service: ServicesDependency) -> MarketDataServiceRecord:
    return service.validate_market_data_service(service_id)


@router.post("/market-data/{service_id}/set-default", response_model=MarketDataServiceRecord)
def set_default_market_data_service(service_id: UUID, service: ServicesDependency) -> MarketDataServiceRecord:
    try:
        return service.set_default_market_data_service(service_id)
    except ServicesCenterError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/market-data/{service_id}/disable", response_model=MarketDataServiceRecord)
def disable_market_data_service(service_id: UUID, service: ServicesDependency) -> MarketDataServiceRecord:
    return service.disable_market_data_service(service_id)


@router.post("/market-data/resolve", response_model=ResolverResult)
def resolve_market_data_service(request: ResolveMarketDataRequest, service: ServicesDependency) -> ResolverResult:
    return service.resolve_market_data(request)


@router.get("/ai", response_model=AIServiceList)
def list_ai_services(service: ServicesDependency) -> AIServiceList:
    return service.list_ai_services()


@router.post("/ai", response_model=AIServiceRecord)
def create_ai_service(request: AIServiceWrite, service: ServicesDependency) -> AIServiceRecord:
    return service.create_ai_service(request)


@router.get("/ai/{service_id}", response_model=AIServiceRecord)
def get_ai_service(service_id: UUID, service: ServicesDependency) -> AIServiceRecord:
    try:
        return service.get_ai_service(service_id)
    except ServicesCenterError as exc:
        raise _operator_error(str(exc)) from exc


@router.put("/ai/{service_id}", response_model=AIServiceRecord)
def update_ai_service(service_id: UUID, request: AIServiceWrite, service: ServicesDependency) -> AIServiceRecord:
    try:
        return service.update_ai_service(service_id, request)
    except ServicesCenterError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/ai/{service_id}/validate", response_model=AIServiceRecord)
def validate_ai_service(service_id: UUID, service: ServicesDependency) -> AIServiceRecord:
    return service.validate_ai_service(service_id)


@router.post("/ai/{service_id}/set-default", response_model=AIServiceRecord)
def set_default_ai_service(service_id: UUID, service: ServicesDependency) -> AIServiceRecord:
    try:
        return service.set_default_ai_service(service_id)
    except ServicesCenterError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/ai/{service_id}/disable", response_model=AIServiceRecord)
def disable_ai_service(service_id: UUID, service: ServicesDependency) -> AIServiceRecord:
    return service.disable_ai_service(service_id)


def _operator_error(message: str) -> Exception:
    if HTTPException is None:
        return ServicesCenterError(message)
    return HTTPException(status_code=400, detail=message)


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()

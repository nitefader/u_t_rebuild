"""AI provider API surface — separate from market-data per Section I."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from backend.app.ai import (
    AIProviderCatalogError,
    AIServiceDeletionResponse,
    AIServiceList,
    AIServiceRecord,
    AIServiceWrite,
    DeleteAIServiceRequest,
)

if TYPE_CHECKING:
    from backend.app.ai import AIProviderCatalog


def get_ai_provider_catalog() -> "AIProviderCatalog":
    from backend.app.ai.runtime import create_ai_provider_catalog_from_environment

    return create_ai_provider_catalog_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


CatalogDependency = Annotated[Any, _dependency(get_ai_provider_catalog)]


@router.get("/providers", response_model=AIServiceList)
def list_providers(catalog: CatalogDependency) -> AIServiceList:
    return catalog.list_services()


@router.post("/providers", response_model=AIServiceRecord)
def create_provider(request: AIServiceWrite, catalog: CatalogDependency) -> AIServiceRecord:
    return catalog.create_service(request)


@router.get("/providers/{service_id}", response_model=AIServiceRecord)
def get_provider(service_id: UUID, catalog: CatalogDependency) -> AIServiceRecord:
    try:
        return catalog.get_service(service_id)
    except AIProviderCatalogError as exc:
        raise _operator_error(str(exc)) from exc


@router.put("/providers/{service_id}", response_model=AIServiceRecord)
def update_provider(service_id: UUID, request: AIServiceWrite, catalog: CatalogDependency) -> AIServiceRecord:
    try:
        return catalog.update_service(service_id, request)
    except AIProviderCatalogError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/providers/{service_id}/validate", response_model=AIServiceRecord)
def validate_provider(service_id: UUID, catalog: CatalogDependency) -> AIServiceRecord:
    return catalog.validate_service(service_id)


@router.post("/providers/{service_id}/set-default", response_model=AIServiceRecord)
def set_default_provider(service_id: UUID, catalog: CatalogDependency) -> AIServiceRecord:
    try:
        return catalog.set_default(service_id)
    except AIProviderCatalogError as exc:
        raise _operator_error(str(exc)) from exc


@router.post("/providers/{service_id}/disable", response_model=AIServiceRecord)
def disable_provider(service_id: UUID, catalog: CatalogDependency) -> AIServiceRecord:
    """Soft-retire (archive): record stays on disk but is excluded from routing."""
    return catalog.disable_service(service_id)


@router.post("/providers/{service_id}/delete", response_model=AIServiceDeletionResponse)
def delete_ai_provider(
    service_id: UUID,
    request: DeleteAIServiceRequest,
    catalog: CatalogDependency,
) -> AIServiceDeletionResponse:
    """Hard-delete: remove catalog row after name confirmation."""
    try:
        existing = catalog.get_service(service_id)
    except AIProviderCatalogError as exc:
        raise _operator_error(str(exc)) from exc
    if request.confirm_service_name.strip() != existing.name:
        raise _operator_error("confirm_service_name did not match provider name")
    catalog.delete_service(service_id)
    return AIServiceDeletionResponse(service_id=service_id, message="AI provider removed from catalog")


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

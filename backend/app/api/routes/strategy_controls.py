"""StrategyControls library CRUD routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.app.strategy_controls.service import (
    StrategyControlsBoundError,
    StrategyControlsNotFoundError,
    StrategyControlsService,
)
from backend.app.strategy_controls.service_models import (
    StrategyControlsDraft,
    StrategyControlsLibrary,
    StrategyControlsLibrarySummary,
    StrategyControlsUsedByResponse,
    StrategyControlsVersionSummary,
)
from backend.app.strategy_controls.models import StrategyControlsVersionRecord


def get_strategy_controls_service() -> StrategyControlsService:
    from backend.app.strategy_controls.runtime_service import (
        create_strategy_controls_service_from_environment,
    )

    return create_strategy_controls_service_from_environment()


router = APIRouter(prefix="/api/v1/strategy-controls", tags=["strategy-controls"])

ServiceDep = Annotated[Any, Depends(get_strategy_controls_service)]


# ------------------------------------------------------------------
# Request bodies
# ------------------------------------------------------------------


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    draft: StrategyControlsDraft


class EditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: StrategyControlsDraft


class DuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_name: str


# ------------------------------------------------------------------
# Response helpers
# ------------------------------------------------------------------


class LibraryListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    libraries: list[StrategyControlsLibrarySummary]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("", response_model=LibraryListResponse)
def list_libraries(service: ServiceDep) -> LibraryListResponse:
    return LibraryListResponse(libraries=service.list_libraries())


@router.get("/{strategy_controls_id}", response_model=StrategyControlsLibrary)
def get_library(strategy_controls_id: UUID, service: ServiceDep) -> StrategyControlsLibrary:
    try:
        return service.get_library(strategy_controls_id)
    except StrategyControlsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{strategy_controls_id}/versions/{version}",
    response_model=StrategyControlsVersionRecord,
)
def get_version_by_number(
    strategy_controls_id: UUID, version: int, service: ServiceDep
) -> StrategyControlsVersionRecord:
    try:
        library = service.get_library(strategy_controls_id)
    except StrategyControlsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for summary in library.history:
        if summary.version == version:
            try:
                return service.get_version(summary.version_id)
            except StrategyControlsNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(
        status_code=404,
        detail=f"version {version} not found for strategy_controls_id {strategy_controls_id}",
    )


@router.post("", response_model=StrategyControlsVersionRecord, status_code=201)
def create_library(request: CreateRequest, service: ServiceDep) -> StrategyControlsVersionRecord:
    return service.create(request.name, request.draft)


@router.put("/{strategy_controls_id}", response_model=StrategyControlsVersionRecord)
def edit_library(
    strategy_controls_id: UUID, request: EditRequest, service: ServiceDep
) -> StrategyControlsVersionRecord:
    try:
        return service.edit(strategy_controls_id, request.draft)
    except StrategyControlsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{strategy_controls_id}/duplicate", response_model=StrategyControlsVersionRecord, status_code=201)
def duplicate_library(
    strategy_controls_id: UUID, request: DuplicateRequest, service: ServiceDep
) -> StrategyControlsVersionRecord:
    try:
        library = service.get_library(strategy_controls_id)
    except StrategyControlsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return service.duplicate(library.head.payload.id, request.new_name)


@router.post("/{strategy_controls_id}/retire", status_code=204)
def retire_library(strategy_controls_id: UUID, service: ServiceDep) -> None:
    try:
        service.retire(strategy_controls_id)
    except StrategyControlsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StrategyControlsBoundError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "bound_deployment_ids": [str(did) for did in exc.deployment_ids],
            },
        ) from exc


@router.post("/{strategy_controls_id}/set-default", status_code=204)
def set_default(strategy_controls_id: UUID, service: ServiceDep) -> None:
    try:
        service.set_default(strategy_controls_id)
    except StrategyControlsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{strategy_controls_id}/used-by", response_model=StrategyControlsUsedByResponse
)
def used_by(
    strategy_controls_id: UUID, service: ServiceDep
) -> StrategyControlsUsedByResponse:
    try:
        return service.used_by(strategy_controls_id)
    except StrategyControlsNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

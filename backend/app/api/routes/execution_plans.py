"""ExecutionPlan library CRUD routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.app.execution_plans.service import (
    ExecutionPlanBoundError,
    ExecutionPlanNotFoundError,
    ExecutionPlanService,
)
from backend.app.execution_plans.service_models import (
    ExecutionPlanDraft,
    ExecutionPlanLibrary,
    ExecutionPlanLibrarySummary,
    ExecutionPlanUsedByResponse,
    ExecutionPlanVersionSummary,
)
from backend.app.execution_plans.models import ExecutionPlanVersionRecord


def get_execution_plan_service() -> ExecutionPlanService:
    from backend.app.execution_plans.runtime_service import (
        create_execution_plan_service_from_environment,
    )

    return create_execution_plan_service_from_environment()


router = APIRouter(prefix="/api/v1/execution-plans", tags=["execution-plans"])

ServiceDep = Annotated[Any, Depends(get_execution_plan_service)]


# ------------------------------------------------------------------
# Request bodies
# ------------------------------------------------------------------


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    draft: ExecutionPlanDraft


class EditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft: ExecutionPlanDraft


class DuplicateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_name: str


# ------------------------------------------------------------------
# Response helpers
# ------------------------------------------------------------------


class LibraryListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    libraries: list[ExecutionPlanLibrarySummary]


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.get("", response_model=LibraryListResponse)
def list_libraries(service: ServiceDep) -> LibraryListResponse:
    return LibraryListResponse(libraries=service.list_libraries())


@router.get("/{execution_plan_id}", response_model=ExecutionPlanLibrary)
def get_library(execution_plan_id: UUID, service: ServiceDep) -> ExecutionPlanLibrary:
    try:
        return service.get_library(execution_plan_id)
    except ExecutionPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{execution_plan_id}/versions/{version}",
    response_model=ExecutionPlanVersionRecord,
)
def get_version_by_number(
    execution_plan_id: UUID, version: int, service: ServiceDep
) -> ExecutionPlanVersionRecord:
    try:
        library = service.get_library(execution_plan_id)
    except ExecutionPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    for summary in library.history:
        if summary.version == version:
            try:
                return service.get_version(summary.version_id)
            except ExecutionPlanNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
    raise HTTPException(
        status_code=404,
        detail=f"version {version} not found for execution_plan_id {execution_plan_id}",
    )


@router.post("", response_model=ExecutionPlanVersionRecord, status_code=201)
def create_library(request: CreateRequest, service: ServiceDep) -> ExecutionPlanVersionRecord:
    return service.create(request.name, request.draft)


@router.put("/{execution_plan_id}", response_model=ExecutionPlanVersionRecord)
def edit_library(
    execution_plan_id: UUID, request: EditRequest, service: ServiceDep
) -> ExecutionPlanVersionRecord:
    try:
        return service.edit(execution_plan_id, request.draft)
    except ExecutionPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{execution_plan_id}/duplicate", response_model=ExecutionPlanVersionRecord, status_code=201)
def duplicate_library(
    execution_plan_id: UUID, request: DuplicateRequest, service: ServiceDep
) -> ExecutionPlanVersionRecord:
    try:
        library = service.get_library(execution_plan_id)
    except ExecutionPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return service.duplicate(library.head.payload.id, request.new_name)


@router.post("/{execution_plan_id}/retire", status_code=204)
def retire_library(execution_plan_id: UUID, service: ServiceDep) -> None:
    try:
        service.retire(execution_plan_id)
    except ExecutionPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExecutionPlanBoundError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "bound_deployment_ids": [str(did) for did in exc.deployment_ids],
            },
        ) from exc


@router.post("/{execution_plan_id}/set-default", status_code=204)
def set_default(execution_plan_id: UUID, service: ServiceDep) -> None:
    try:
        service.set_default(execution_plan_id)
    except ExecutionPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{execution_plan_id}/used-by", response_model=ExecutionPlanUsedByResponse
)
def used_by(
    execution_plan_id: UUID, service: ServiceDep
) -> ExecutionPlanUsedByResponse:
    try:
        return service.used_by(execution_plan_id)
    except ExecutionPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

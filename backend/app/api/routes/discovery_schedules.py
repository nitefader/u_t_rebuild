"""Discovery schedule API.

Schedules can run Screeners or refresh Watchlists. They are discovery and
entry-universe automation only; this route never touches orders, positions,
broker adapters, or BrokerSync.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.screener.schedule_service import (
    DiscoveryScheduleService,
    DiscoveryScheduleServiceError,
    create_discovery_schedule_service_from_environment,
)
from backend.app.screener.schedule_store import DiscoveryScheduleNotFoundError
from backend.app.screener.schedules import (
    DiscoverySchedule,
    DiscoveryScheduleExecution,
    DiscoveryScheduleExecutionListResponse,
    DiscoveryScheduleListResponse,
    DiscoverySchedulePatchRequest,
    DiscoveryScheduleTrigger,
    DiscoveryScheduleWriteRequest,
)


def get_discovery_schedule_service() -> DiscoveryScheduleService:
    return create_discovery_schedule_service_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/discovery-schedules", tags=["discovery-schedules"])

ServiceDep = Annotated[Any, _dependency(get_discovery_schedule_service)]


def _err(status: int, msg: str) -> HTTPException:
    return HTTPException(status_code=status, detail=msg)


@router.get("", response_model=DiscoveryScheduleListResponse)
def list_discovery_schedules(service: ServiceDep) -> DiscoveryScheduleListResponse:
    return DiscoveryScheduleListResponse(schedules=service.list_schedules())


@router.post("", response_model=DiscoverySchedule, status_code=201)
def create_discovery_schedule(
    request: DiscoveryScheduleWriteRequest,
    service: ServiceDep,
) -> DiscoverySchedule:
    try:
        return service.create_schedule(request)
    except DiscoveryScheduleServiceError as exc:
        raise _err(422, str(exc)) from exc


@router.get("/{schedule_id}", response_model=DiscoverySchedule)
def get_discovery_schedule(schedule_id: UUID, service: ServiceDep) -> DiscoverySchedule:
    try:
        return service.get_schedule(schedule_id)
    except DiscoveryScheduleNotFoundError as exc:
        raise _err(404, str(exc)) from exc


@router.patch("/{schedule_id}", response_model=DiscoverySchedule)
def patch_discovery_schedule(
    schedule_id: UUID,
    request: DiscoverySchedulePatchRequest,
    service: ServiceDep,
) -> DiscoverySchedule:
    try:
        return service.patch_schedule(schedule_id, request)
    except DiscoveryScheduleNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except DiscoveryScheduleServiceError as exc:
        raise _err(422, str(exc)) from exc


@router.post("/{schedule_id}/pause", response_model=DiscoverySchedule)
def pause_discovery_schedule(schedule_id: UUID, service: ServiceDep) -> DiscoverySchedule:
    try:
        return service.pause_schedule(schedule_id)
    except DiscoveryScheduleNotFoundError as exc:
        raise _err(404, str(exc)) from exc


@router.post("/{schedule_id}/resume", response_model=DiscoverySchedule)
def resume_discovery_schedule(schedule_id: UUID, service: ServiceDep) -> DiscoverySchedule:
    try:
        return service.resume_schedule(schedule_id)
    except DiscoveryScheduleNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except DiscoveryScheduleServiceError as exc:
        raise _err(422, str(exc)) from exc


@router.post("/{schedule_id}/archive", response_model=DiscoverySchedule)
def archive_discovery_schedule(schedule_id: UUID, service: ServiceDep) -> DiscoverySchedule:
    try:
        return service.archive_schedule(schedule_id)
    except DiscoveryScheduleNotFoundError as exc:
        raise _err(404, str(exc)) from exc


@router.post("/{schedule_id}/delete", status_code=204)
def delete_discovery_schedule(schedule_id: UUID, service: ServiceDep) -> None:
    try:
        service.delete_schedule(schedule_id)
    except DiscoveryScheduleNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except DiscoveryScheduleServiceError as exc:
        raise _err(409, str(exc)) from exc


@router.post("/{schedule_id}/run-now", response_model=DiscoveryScheduleExecution)
def run_discovery_schedule_now(schedule_id: UUID, service: ServiceDep) -> DiscoveryScheduleExecution:
    try:
        return service.run_schedule(schedule_id, trigger=DiscoveryScheduleTrigger.RUN_NOW)
    except DiscoveryScheduleNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    except DiscoveryScheduleServiceError as exc:
        raise _err(409, str(exc)) from exc


@router.post("/run-due", response_model=DiscoveryScheduleExecutionListResponse)
def run_due_discovery_schedules(service: ServiceDep) -> DiscoveryScheduleExecutionListResponse:
    return DiscoveryScheduleExecutionListResponse(executions=service.run_due())


@router.get("/{schedule_id}/executions", response_model=DiscoveryScheduleExecutionListResponse)
def list_discovery_schedule_executions(
    schedule_id: UUID,
    service: ServiceDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> DiscoveryScheduleExecutionListResponse:
    try:
        service.get_schedule(schedule_id)
    except DiscoveryScheduleNotFoundError as exc:
        raise _err(404, str(exc)) from exc
    return DiscoveryScheduleExecutionListResponse(
        executions=service.list_executions(schedule_id=schedule_id, limit=limit)
    )


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()

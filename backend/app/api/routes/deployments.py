"""Deployment CRUD + lifecycle routes.

Pause / resume / flatten with control-plane gating live under
``/api/v1/operations/deployments/{id}/...`` (Operation Turtle Shell
ownership). The lifecycle endpoints here update the persisted
deployment record's lifecycle_status; the runtime composition root
honors that state on its next tick.
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.deployments import (
    Deployment,
    DeploymentListResponse,
    DeploymentResponse,
    DeploymentService,
    DeploymentServiceError,
    DeploymentWriteRequest,
)
from backend.app.deployments.models import (
    DeploymentBindingHistoryListResponse,
    DeploymentLifecycleRequest,
    DeploymentRebindRequest,
    DeploymentSubscribeRequest,
)


def get_deployment_service(request: Request) -> DeploymentService:
    from backend.app.deployments.runtime_service import (
        create_deployment_service_from_environment,
    )

    supervisor = getattr(request.app.state, "broker_runtime_supervisor", None)
    runtime_reloader = supervisor.reload_deployment if supervisor is not None else None
    return create_deployment_service_from_environment(runtime_reloader=runtime_reloader)


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])

ServiceDep = Annotated[Any, _dependency(get_deployment_service)]


def _err(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


@router.get("", response_model=DeploymentListResponse)
def list_deployments(service: ServiceDep) -> DeploymentListResponse:
    return DeploymentListResponse(deployments=service.list_deployments())


@router.post("", response_model=DeploymentResponse)
def create_deployment(request: DeploymentWriteRequest, service: ServiceDep) -> DeploymentResponse:
    try:
        deployment = service.create_deployment(request)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.get("/{deployment_id}", response_model=DeploymentResponse)
def get_deployment(deployment_id: UUID, service: ServiceDep) -> DeploymentResponse:
    try:
        return service.get_deployment(deployment_id)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc


@router.patch("/{deployment_id}", response_model=DeploymentResponse)
def update_deployment(
    deployment_id: UUID, request: DeploymentWriteRequest, service: ServiceDep
) -> DeploymentResponse:
    try:
        deployment = service.update_deployment(deployment_id, request)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.post("/{deployment_id}/delete", status_code=204)
def delete_deployment(deployment_id: UUID, service: ServiceDep) -> None:
    try:
        service.delete_deployment(deployment_id)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc


@router.post("/{deployment_id}/start", response_model=DeploymentResponse)
def start_deployment(
    deployment_id: UUID, request: DeploymentLifecycleRequest, service: ServiceDep
) -> DeploymentResponse:
    try:
        deployment = service.start(deployment_id, reason=request.reason)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.post("/{deployment_id}/stop", response_model=DeploymentResponse)
def stop_deployment(
    deployment_id: UUID, request: DeploymentLifecycleRequest, service: ServiceDep
) -> DeploymentResponse:
    try:
        deployment = service.stop(deployment_id, reason=request.reason)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.post("/{deployment_id}/pause", response_model=DeploymentResponse)
def pause_deployment(
    deployment_id: UUID, request: DeploymentLifecycleRequest, service: ServiceDep
) -> DeploymentResponse:
    """Pause persistence record only. For control-plane-gated
    runtime pause, use ``/api/v1/operations/deployments/{id}/pause``."""
    try:
        deployment = service.pause(deployment_id, reason=request.reason)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.post("/{deployment_id}/resume", response_model=DeploymentResponse)
def resume_deployment(
    deployment_id: UUID, request: DeploymentLifecycleRequest, service: ServiceDep
) -> DeploymentResponse:
    try:
        deployment = service.resume(deployment_id, reason=request.reason)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.post("/{deployment_id}/subscribe", response_model=DeploymentResponse)
def subscribe_account(
    deployment_id: UUID, request: DeploymentSubscribeRequest, service: ServiceDep
) -> DeploymentResponse:
    try:
        deployment: Deployment = service.subscribe_account(deployment_id, request.account_id)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.post("/{deployment_id}/unsubscribe", response_model=DeploymentResponse)
def unsubscribe_account(
    deployment_id: UUID, request: DeploymentSubscribeRequest, service: ServiceDep
) -> DeploymentResponse:
    try:
        deployment = service.unsubscribe_account(deployment_id, request.account_id)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.post("/{deployment_id}/rebind", response_model=DeploymentResponse)
def rebind_deployment(
    deployment_id: UUID, request: DeploymentRebindRequest, service: ServiceDep
) -> DeploymentResponse:
    """Hot-swap Controls and/or ExecutionPlan on a running deployment.

    Open positions are unaffected; the runtime reads the new bindings on
    its next tick for candidate orders only.
    """
    try:
        deployment = service.rebind(deployment_id, request)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc
    return DeploymentResponse(deployment=deployment)


@router.get(
    "/{deployment_id}/binding-history",
    response_model=DeploymentBindingHistoryListResponse,
)
def get_binding_history(
    deployment_id: UUID, service: ServiceDep
) -> DeploymentBindingHistoryListResponse:
    """Return the binding change history for a deployment, newest-first."""
    try:
        return service.get_binding_history(deployment_id)
    except DeploymentServiceError as exc:
        raise _err(str(exc)) from exc


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()

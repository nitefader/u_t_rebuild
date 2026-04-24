from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from typing import Annotated, Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.operations.models import (
    AccountOperations,
    DeploymentOperations,
    FlattenRequestResponse,
    RuntimeOverview,
)

if TYPE_CHECKING:
    from backend.app.operations import OperationsCenterService

try:  # pragma: no cover - exercised only when the optional web framework is installed.
    from fastapi import APIRouter, Body, Depends, HTTPException
except ModuleNotFoundError:  # pragma: no cover - the fallback is covered by unit tests in this environment.
    APIRouter = None  # type: ignore[assignment]
    Body = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]


class ControlCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1)


class ControlCommandResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool = True
    action: str
    scope: str
    target_id: UUID | None = None
    message: str


class OperatorErrorResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    detail: str


class OperatorRouteError(RuntimeError):
    """Raised by fallback route functions with operator-readable details."""


@dataclass(frozen=True)
class RegisteredRoute:
    path: str
    method: str
    endpoint: Callable[..., object]
    response_model: type[BaseModel]


class FallbackRouter:
    def __init__(self, *, prefix: str = "", tags: list[str] | None = None) -> None:
        self.prefix = prefix
        self.tags = tags or []
        self.routes: list[RegisteredRoute] = []

    def get(self, path: str, *, response_model: type[BaseModel]) -> Callable[[Callable[..., object]], Callable[..., object]]:
        return self._register("GET", path, response_model)

    def post(self, path: str, *, response_model: type[BaseModel]) -> Callable[[Callable[..., object]], Callable[..., object]]:
        return self._register("POST", path, response_model)

    def _register(
        self,
        method: str,
        path: str,
        response_model: type[BaseModel],
    ) -> Callable[[Callable[..., object]], Callable[..., object]]:
        def decorator(endpoint: Callable[..., object]) -> Callable[..., object]:
            self.routes.append(RegisteredRoute(path=f"{self.prefix}{path}", method=method, endpoint=endpoint, response_model=response_model))
            return endpoint

        return decorator


def get_operations_center_service() -> "OperationsCenterService":
    from backend.app.operations.runtime_service import create_operations_center_service_from_environment

    return create_operations_center_service_from_environment()


def _dependency(default: object) -> object:
    if Depends is None:
        return default
    return Depends(default)


def _body(default: object) -> object:
    if Body is None:
        return default
    return Body(default)


def _router():
    if APIRouter is None:
        return FallbackRouter(prefix="/api/v1/operations", tags=["operations"])
    return APIRouter(prefix="/api/v1/operations", tags=["operations"])


router = _router()

OperationsServiceDependency = Annotated[Any, _dependency(get_operations_center_service)]
CommandBody = Annotated[ControlCommandRequest, _body(...)]


@router.get("/overview", response_model=RuntimeOverview)
def get_runtime_overview(service: OperationsServiceDependency) -> RuntimeOverview:
    try:
        return service.get_runtime_overview()
    except Exception as exc:  # noqa: BLE001 - operator routes should return a readable boundary error.
        raise _operator_error("Unable to load operations overview", exc) from exc


@router.get("/accounts/{account_id}", response_model=AccountOperations)
def get_account_operations(account_id: UUID, service: OperationsServiceDependency) -> AccountOperations:
    try:
        return service.get_account_operations(account_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to load account operations for {account_id}", exc) from exc


@router.get("/deployments/{deployment_id}", response_model=DeploymentOperations)
def get_deployment_operations(deployment_id: UUID, service: OperationsServiceDependency) -> DeploymentOperations:
    try:
        return service.get_deployment_operations(deployment_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to load deployment operations for {deployment_id}", exc) from exc


@router.post("/deployments/{deployment_id}/pause", response_model=ControlCommandResponse)
def pause_deployment(deployment_id: UUID, command: CommandBody, service: OperationsServiceDependency) -> ControlCommandResponse:
    try:
        service.pause_deployment(deployment_id, command.reason)
        return _control_response(action="pause", scope="deployment", target_id=deployment_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to pause deployment {deployment_id}", exc) from exc


@router.post("/deployments/{deployment_id}/resume", response_model=ControlCommandResponse)
def resume_deployment(deployment_id: UUID, command: CommandBody, service: OperationsServiceDependency) -> ControlCommandResponse:
    try:
        service.resume_deployment(deployment_id, command.reason)
        return _control_response(action="resume", scope="deployment", target_id=deployment_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to resume deployment {deployment_id}", exc) from exc


@router.post("/accounts/{account_id}/pause", response_model=ControlCommandResponse)
def pause_account(account_id: UUID, command: CommandBody, service: OperationsServiceDependency) -> ControlCommandResponse:
    try:
        service.pause_account(account_id, command.reason)
        return _control_response(action="pause", scope="account", target_id=account_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to pause account {account_id}", exc) from exc


@router.post("/accounts/{account_id}/resume", response_model=ControlCommandResponse)
def resume_account(account_id: UUID, command: CommandBody, service: OperationsServiceDependency) -> ControlCommandResponse:
    try:
        service.resume_account(account_id, command.reason)
        return _control_response(action="resume", scope="account", target_id=account_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to resume account {account_id}", exc) from exc


@router.post("/global/kill", response_model=ControlCommandResponse)
def global_kill(command: CommandBody, service: OperationsServiceDependency) -> ControlCommandResponse:
    try:
        service.global_kill(command.reason)
        return _control_response(action="kill", scope="global")
    except Exception as exc:  # noqa: BLE001
        raise _operator_error("Unable to activate global kill", exc) from exc


@router.post("/global/resume", response_model=ControlCommandResponse)
def global_resume(command: CommandBody, service: OperationsServiceDependency) -> ControlCommandResponse:
    try:
        service.global_resume(command.reason)
        return _control_response(action="resume", scope="global")
    except Exception as exc:  # noqa: BLE001
        raise _operator_error("Unable to resume global operations", exc) from exc


@router.post("/accounts/{account_id}/flatten", response_model=FlattenRequestResponse)
def flatten_account(account_id: UUID, command: CommandBody, service: OperationsServiceDependency) -> FlattenRequestResponse:
    try:
        return service.request_flatten_account(account_id, command.reason)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to request account flatten for {account_id}", exc) from exc


@router.post("/deployments/{deployment_id}/flatten", response_model=FlattenRequestResponse)
def flatten_deployment(deployment_id: UUID, command: CommandBody, service: OperationsServiceDependency) -> FlattenRequestResponse:
    try:
        return service.request_flatten_deployment(deployment_id, command.reason)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to request deployment flatten for {deployment_id}", exc) from exc


def _control_response(*, action: str, scope: str, target_id: UUID | None = None) -> ControlCommandResponse:
    target = f" {target_id}" if target_id is not None else ""
    return ControlCommandResponse(
        action=action,
        scope=scope,
        target_id=target_id,
        message=f"operations control {action} accepted for {scope}{target}",
    )


def _operator_error(message: str, exc: Exception) -> Exception:
    detail = f"{message}: {exc}"
    if HTTPException is None:
        return OperatorRouteError(detail)
    return HTTPException(status_code=503, detail=detail)

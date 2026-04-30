from __future__ import annotations

from typing import TYPE_CHECKING, Any
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.operations.models import (
    AccountOperations,
    AccountSignalPlanEvaluationListResponse,
    DailyRiskStateResponse,
    DeploymentOperations,
    FlattenRequestResponse,
    OrderDetail,
    RuntimeOverview,
)
from backend.app.domain import (
    BacktestRun,
    ChartLabPreviewEvidence,
    OptimizationRun,
    PromotionEvidenceBundle,
    SimulationRunEvidence,
    WalkForwardRun,
)

if TYPE_CHECKING:
    from backend.app.operations import OperationsCenterService


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


class OperatorRouteError(HTTPException):
    """Raised by direct route calls with operator-readable FastAPI details."""

    def __init__(self, detail: str) -> None:
        super().__init__(status_code=503, detail=detail)


ResearchEvidenceResponse = (
    ChartLabPreviewEvidence
    | BacktestRun
    | SimulationRunEvidence
    | OptimizationRun
    | WalkForwardRun
    | PromotionEvidenceBundle
)


class ResearchEvidenceListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence: tuple[ResearchEvidenceResponse, ...] = ()


def get_operations_center_service() -> "OperationsCenterService":
    from backend.app.operations.runtime_service import create_operations_center_service_from_environment

    return create_operations_center_service_from_environment()


def _dependency(default: object) -> object:
    return Depends(default)


def _body(default: object) -> object:
    return Body(default)


router = APIRouter(prefix="/api/v1/operations", tags=["operations"])

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


@router.get("/accounts/{account_id}/daily-risk-state", response_model=DailyRiskStateResponse)
def get_account_daily_risk_state(account_id: UUID, service: OperationsServiceDependency) -> DailyRiskStateResponse:
    try:
        return service.get_daily_risk_state(account_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to load daily risk state for {account_id}", exc) from exc


@router.get("/deployments/{deployment_id}", response_model=DeploymentOperations)
def get_deployment_operations(deployment_id: UUID, service: OperationsServiceDependency) -> DeploymentOperations:
    try:
        return service.get_deployment_operations(deployment_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to load deployment operations for {deployment_id}", exc) from exc


@router.get("/orders/{order_id}", response_model=OrderDetail)
def get_order_detail(order_id: UUID, service: OperationsServiceDependency) -> OrderDetail:
    try:
        return service.get_order_detail(order_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to load order detail for {order_id}", exc) from exc


@router.get("/broker-orders/{broker_order_id}", response_model=OrderDetail)
def get_order_detail_by_broker_order_id(broker_order_id: str, service: OperationsServiceDependency) -> OrderDetail:
    try:
        return service.get_order_detail_by_broker_order_id(broker_order_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to load order detail for broker order {broker_order_id}", exc) from exc


@router.get("/evaluations", response_model=AccountSignalPlanEvaluationListResponse)
def list_account_signal_plan_evaluations(
    service: OperationsServiceDependency,
    account_id: UUID | None = None,
    deployment_id: UUID | None = None,
    signal_plan_id: UUID | None = None,
    limit: int = 100,
) -> AccountSignalPlanEvaluationListResponse:
    try:
        return AccountSignalPlanEvaluationListResponse(
            evaluations=service.list_account_signal_plan_evaluations(
                account_id=account_id,
                deployment_id=deployment_id,
                signal_plan_id=signal_plan_id,
                limit=limit,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise _operator_error("Unable to load account SignalPlan evaluations", exc) from exc


@router.get("/research-evidence", response_model=ResearchEvidenceListResponse)
def list_research_evidence(
    service: OperationsServiceDependency,
    strategy_id: UUID | None = None,
    strategy_version_id: UUID | None = None,
    evidence_type: str | None = None,
) -> ResearchEvidenceListResponse:
    try:
        return ResearchEvidenceListResponse(
            evidence=service.list_research_evidence(
                strategy_id=strategy_id,
                strategy_version_id=strategy_version_id,
                evidence_type=evidence_type,
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise _operator_error("Unable to load research evidence", exc) from exc


@router.get("/research-evidence/{evidence_id}", response_model=ResearchEvidenceResponse)
def get_research_evidence(evidence_id: UUID, service: OperationsServiceDependency) -> ResearchEvidenceResponse:
    try:
        return service.get_research_evidence(evidence_id)
    except Exception as exc:  # noqa: BLE001
        raise _operator_error(f"Unable to load research evidence {evidence_id}", exc) from exc


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
    return OperatorRouteError(detail)


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()

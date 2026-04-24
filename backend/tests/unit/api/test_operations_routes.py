from __future__ import annotations

import inspect
from uuid import UUID

from backend.app.api.routes import operations
from backend.app.control_plane import ControlPlaneState
from backend.app.operations import (
    AccountOperations,
    DeploymentOperations,
    FlattenRequestResponse,
    InternalOrderLedgerSummary,
    RuntimeOverview,
)
from backend.app.runtime import RuntimeStatus


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


class RecordingOperationsService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID | str]] = []
        self.overview = RuntimeOverview(
            system_recovery_active=False,
            global_kill_active=False,
            control_state=ControlPlaneState(),
        )
        self.account = AccountOperations(
            account_id=ACCOUNT_ID,
            internal_order_ledger_summary=InternalOrderLedgerSummary(),
        )
        self.deployment = DeploymentOperations(
            deployment_id=DEPLOYMENT_ID,
            runtime_status=RuntimeStatus.RUNNING,
            governor_id="portfolio-governor",
        )

    def get_runtime_overview(self) -> RuntimeOverview:
        self.calls.append(("get_runtime_overview", "global"))
        return self.overview

    def get_account_operations(self, account_id: UUID) -> AccountOperations:
        self.calls.append(("get_account_operations", account_id))
        return self.account

    def get_deployment_operations(self, deployment_id: UUID) -> DeploymentOperations:
        self.calls.append(("get_deployment_operations", deployment_id))
        return self.deployment

    def pause_deployment(self, deployment_id: UUID, reason: str) -> None:
        self.calls.append(("pause_deployment", deployment_id))
        self.calls.append(("reason", reason))

    def resume_deployment(self, deployment_id: UUID, reason: str) -> None:
        self.calls.append(("resume_deployment", deployment_id))
        self.calls.append(("reason", reason))

    def pause_account(self, account_id: UUID, reason: str) -> None:
        self.calls.append(("pause_account", account_id))
        self.calls.append(("reason", reason))

    def resume_account(self, account_id: UUID, reason: str) -> None:
        self.calls.append(("resume_account", account_id))
        self.calls.append(("reason", reason))

    def global_kill(self, reason: str) -> None:
        self.calls.append(("global_kill", reason))

    def global_resume(self, reason: str) -> None:
        self.calls.append(("global_resume", reason))

    def request_flatten_account(self, account_id: UUID, reason: str) -> FlattenRequestResponse:
        self.calls.append(("request_flatten_account", account_id))
        self.calls.append(("reason", reason))
        return FlattenRequestResponse(
            accepted=False,
            status="unsupported_not_ready",
            reason="flatten_not_implemented_in_control_plane",
            scope="account",
            target_id=account_id,
        )

    def request_flatten_deployment(self, deployment_id: UUID, reason: str) -> FlattenRequestResponse:
        self.calls.append(("request_flatten_deployment", deployment_id))
        self.calls.append(("reason", reason))
        return FlattenRequestResponse(
            accepted=False,
            status="unsupported_not_ready",
            reason="flatten_not_implemented_in_control_plane",
            scope="deployment",
            target_id=deployment_id,
        )


def _command(reason: str = "operator_request") -> operations.ControlCommandRequest:
    return operations.ControlCommandRequest(reason=reason)


def test_routes_are_registered_with_explicit_response_models() -> None:
    registered = {(route.method, route.path): route.response_model for route in operations.router.routes}

    assert registered[("GET", "/api/v1/operations/overview")] is RuntimeOverview
    assert registered[("GET", f"/api/v1/operations/accounts/{{account_id}}")] is AccountOperations
    assert registered[("GET", f"/api/v1/operations/deployments/{{deployment_id}}")] is DeploymentOperations
    assert registered[("POST", f"/api/v1/operations/deployments/{{deployment_id}}/pause")] is operations.ControlCommandResponse
    assert registered[("POST", f"/api/v1/operations/deployments/{{deployment_id}}/resume")] is operations.ControlCommandResponse
    assert registered[("POST", f"/api/v1/operations/accounts/{{account_id}}/pause")] is operations.ControlCommandResponse
    assert registered[("POST", f"/api/v1/operations/accounts/{{account_id}}/resume")] is operations.ControlCommandResponse
    assert registered[("POST", "/api/v1/operations/global/kill")] is operations.ControlCommandResponse
    assert registered[("POST", "/api/v1/operations/global/resume")] is operations.ControlCommandResponse
    assert registered[("POST", f"/api/v1/operations/accounts/{{account_id}}/flatten")] is FlattenRequestResponse
    assert registered[("POST", f"/api/v1/operations/deployments/{{deployment_id}}/flatten")] is FlattenRequestResponse


def test_overview_route_returns_runtime_overview() -> None:
    service = RecordingOperationsService()

    response = operations.get_runtime_overview(service=service)

    assert response == service.overview
    assert service.calls == [("get_runtime_overview", "global")]


def test_account_route_returns_account_operations() -> None:
    service = RecordingOperationsService()

    response = operations.get_account_operations(ACCOUNT_ID, service=service)

    assert response == service.account
    assert service.calls == [("get_account_operations", ACCOUNT_ID)]


def test_deployment_route_returns_deployment_operations() -> None:
    service = RecordingOperationsService()

    response = operations.get_deployment_operations(DEPLOYMENT_ID, service=service)

    assert response == service.deployment
    assert service.calls == [("get_deployment_operations", DEPLOYMENT_ID)]


def test_pause_resume_deployment_delegates_through_service() -> None:
    service = RecordingOperationsService()

    pause = operations.pause_deployment(DEPLOYMENT_ID, _command("maintenance"), service=service)
    resume = operations.resume_deployment(DEPLOYMENT_ID, _command("ready"), service=service)

    assert pause.action == "pause"
    assert resume.action == "resume"
    assert service.calls == [
        ("pause_deployment", DEPLOYMENT_ID),
        ("reason", "maintenance"),
        ("resume_deployment", DEPLOYMENT_ID),
        ("reason", "ready"),
    ]


def test_pause_resume_account_delegates_through_service() -> None:
    service = RecordingOperationsService()

    pause = operations.pause_account(ACCOUNT_ID, _command("risk"), service=service)
    resume = operations.resume_account(ACCOUNT_ID, _command("clear"), service=service)

    assert pause.scope == "account"
    assert resume.scope == "account"
    assert service.calls == [
        ("pause_account", ACCOUNT_ID),
        ("reason", "risk"),
        ("resume_account", ACCOUNT_ID),
        ("reason", "clear"),
    ]


def test_global_kill_resume_delegates_through_service() -> None:
    service = RecordingOperationsService()

    kill = operations.global_kill(_command("operator"), service=service)
    resume = operations.global_resume(_command("operator"), service=service)

    assert kill.action == "kill"
    assert resume.action == "resume"
    assert service.calls == [("global_kill", "operator"), ("global_resume", "operator")]


def test_flatten_routes_return_explicit_unsupported_not_ready() -> None:
    service = RecordingOperationsService()

    account = operations.flatten_account(ACCOUNT_ID, _command("operator"), service=service)
    deployment = operations.flatten_deployment(DEPLOYMENT_ID, _command("operator"), service=service)

    assert account.accepted is False
    assert account.status == "unsupported_not_ready"
    assert deployment.accepted is False
    assert deployment.status == "unsupported_not_ready"
    assert service.calls == [
        ("request_flatten_account", ACCOUNT_ID),
        ("reason", "operator"),
        ("request_flatten_deployment", DEPLOYMENT_ID),
        ("reason", "operator"),
    ]


def test_route_errors_are_operator_readable() -> None:
    class FailingService(RecordingOperationsService):
        def get_runtime_overview(self) -> RuntimeOverview:
            raise RuntimeError("state store unavailable")

    try:
        operations.get_runtime_overview(service=FailingService())
    except operations.OperatorRouteError as exc:
        assert "Unable to load operations overview" in str(exc)
        assert "state store unavailable" in str(exc)
    else:  # pragma: no cover - defensive branch for route error contract.
        raise AssertionError("expected operator-readable route error")


def test_routes_do_not_call_direct_broker_or_create_orders_or_mutate_broker_truth() -> None:
    source = inspect.getsource(operations)

    assert "BrokerAdapter" not in source
    assert "AlpacaBrokerAdapter" not in source
    assert ".submit_order(" not in source
    assert ".create_order(" not in source
    assert "OrderManager" not in source
    assert "save_broker_account_snapshot" not in source
    assert "save_broker_open_order_snapshot" not in source
    assert "save_broker_sync_freshness" not in source

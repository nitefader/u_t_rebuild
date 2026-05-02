from __future__ import annotations

import inspect
from uuid import UUID

from backend.app.api.routes import operations
from backend.app.control_plane import ControlPlaneState
from backend.app.operations import (
    AccountOperations,
    AccountSignalPlanEvaluationListResponse,
    DeploymentOperations,
    FlattenRequestResponse,
    GovernorDecisionListResponse,
    InternalOrderLedgerSummary,
    OrderDetail,
    RuntimeOverview,
    SignalPlanListResponse,
)
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
    SignalPlan,
    SignalPlanIntent,
    SignalPlanSide,
)
from backend.tests.unit.operations.test_operations_center_service import STRATEGY_VERSION_ID, _backtest_evidence, _order
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
        order = _order()
        self.order_detail = OrderDetail(
            internal_order=order,
            broker_account_id=ACCOUNT_ID,
            deployment_id=DEPLOYMENT_ID,
            strategy_version_id=STRATEGY_VERSION_ID,
        )
        self.evaluations = (
            AccountSignalPlanEvaluation(
                evaluation_id=UUID("22222222-3333-4444-5555-666666666666"),
                account_id=ACCOUNT_ID,
                signal_plan_id=UUID("33333333-4444-5555-6666-777777777777"),
                deployment_id=DEPLOYMENT_ID,
                strategy_id=UUID("44444444-5555-6666-7777-888888888888"),
                status=AccountEvaluationStatus.ACCEPTED,
                participation_decision=AccountParticipationDecision.PARTICIPATE,
            ),
        )
        self.signal_plans = (
            SignalPlan(
                signal_plan_id=self.evaluations[0].signal_plan_id,
                deployment_id=DEPLOYMENT_ID,
                strategy_id=self.evaluations[0].strategy_id,
                strategy_version_id=STRATEGY_VERSION_ID,
                symbol="SPY",
                side=SignalPlanSide.LONG,
                intent=SignalPlanIntent.OPEN,
            ),
        )
        self.governor_decisions = (
            GovernorDecisionTrace(
                governor_decision_id=UUID("55555555-6666-7777-8888-999999999999"),
                account_id=ACCOUNT_ID,
                signal_plan_id=self.evaluations[0].signal_plan_id,
                status=GovernorDecisionStatus.APPROVED,
                approved=True,
                reasons=("approved",),
            ),
        )
        self.research_evidence = (_backtest_evidence(),)

    def get_runtime_overview(self) -> RuntimeOverview:
        self.calls.append(("get_runtime_overview", "global"))
        return self.overview

    def get_account_operations(self, account_id: UUID) -> AccountOperations:
        self.calls.append(("get_account_operations", account_id))
        return self.account

    def get_deployment_operations(self, deployment_id: UUID) -> DeploymentOperations:
        self.calls.append(("get_deployment_operations", deployment_id))
        return self.deployment

    def get_order_detail(self, order_id: UUID) -> OrderDetail:
        self.calls.append(("get_order_detail", order_id))
        return self.order_detail

    def get_order_detail_by_broker_order_id(self, broker_order_id: str) -> OrderDetail:
        self.calls.append(("get_order_detail_by_broker_order_id", broker_order_id))
        return self.order_detail

    def list_account_signal_plan_evaluations(
        self,
        *,
        account_id: UUID | None = None,
        deployment_id: UUID | None = None,
        signal_plan_id: UUID | None = None,
        limit: int = 100,
    ) -> tuple[AccountSignalPlanEvaluation, ...]:
        self.calls.append(("list_account_signal_plan_evaluations", account_id or "all"))
        self.calls.append(("deployment_id", deployment_id or "all"))
        self.calls.append(("signal_plan_id", signal_plan_id or "all"))
        self.calls.append(("limit", str(limit)))
        return self.evaluations

    def list_signal_plans(
        self,
        *,
        account_id: UUID | None = None,
        deployment_id: UUID | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> tuple[SignalPlan, ...]:
        self.calls.append(("list_signal_plans", account_id or "all"))
        self.calls.append(("deployment_id", deployment_id or "all"))
        self.calls.append(("symbol", symbol or "all"))
        self.calls.append(("limit", str(limit)))
        return self.signal_plans

    def list_governor_decision_traces(
        self,
        *,
        account_id: UUID | None = None,
        deployment_id: UUID | None = None,
        signal_plan_id: UUID | None = None,
        limit: int = 100,
    ) -> tuple[GovernorDecisionTrace, ...]:
        self.calls.append(("list_governor_decision_traces", account_id or "all"))
        self.calls.append(("deployment_id", deployment_id or "all"))
        self.calls.append(("signal_plan_id", signal_plan_id or "all"))
        self.calls.append(("limit", str(limit)))
        return self.governor_decisions

    def list_research_evidence(
        self,
        *,
        strategy_id: UUID | None = None,
        strategy_version_id: UUID | None = None,
        evidence_type: str | None = None,
    ) -> tuple[object, ...]:
        self.calls.append(("list_research_evidence", evidence_type or "all"))
        _ = strategy_id, strategy_version_id
        return self.research_evidence

    def get_research_evidence(self, evidence_id: UUID) -> object:
        self.calls.append(("get_research_evidence", evidence_id))
        return self.research_evidence[0]

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
    assert registered[("GET", f"/api/v1/operations/orders/{{order_id}}")] is OrderDetail
    assert registered[("GET", "/api/v1/operations/broker-orders/{broker_order_id}")] is OrderDetail
    assert registered[("GET", "/api/v1/operations/signal-plans")] is SignalPlanListResponse
    assert registered[("GET", "/api/v1/operations/evaluations")] is AccountSignalPlanEvaluationListResponse
    assert registered[("GET", "/api/v1/operations/governor-decisions")] is GovernorDecisionListResponse
    assert registered[("GET", "/api/v1/operations/research-evidence")] is operations.ResearchEvidenceListResponse
    assert registered[("GET", "/api/v1/operations/research-evidence/{evidence_id}")] is operations.ResearchEvidenceResponse
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


def test_order_detail_route_returns_order_detail_without_auth_dependency_in_paper_mode() -> None:
    service = RecordingOperationsService()
    order_id = service.order_detail.internal_order.order_id

    response = operations.get_order_detail(order_id, service=service)

    assert response == service.order_detail
    assert service.calls == [("get_order_detail", order_id)]


def test_broker_order_detail_route_returns_order_detail_without_direct_broker_call() -> None:
    service = RecordingOperationsService()

    response = operations.get_order_detail_by_broker_order_id("broker-1", service=service)

    assert response == service.order_detail
    assert service.calls == [("get_order_detail_by_broker_order_id", "broker-1")]


def test_account_signal_plan_evaluations_route_returns_read_model_with_filters() -> None:
    service = RecordingOperationsService()
    signal_plan_id = service.evaluations[0].signal_plan_id

    response = operations.list_account_signal_plan_evaluations(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        signal_plan_id=signal_plan_id,
        limit=25,
        service=service,
    )

    assert response.evaluations == service.evaluations
    assert service.calls == [
        ("list_account_signal_plan_evaluations", ACCOUNT_ID),
        ("deployment_id", DEPLOYMENT_ID),
        ("signal_plan_id", signal_plan_id),
        ("limit", "25"),
    ]


def test_signal_plans_route_returns_read_model_with_filters() -> None:
    service = RecordingOperationsService()

    response = operations.list_signal_plans(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        symbol="SPY",
        limit=25,
        service=service,
    )

    assert response.signal_plans == service.signal_plans
    assert service.calls == [
        ("list_signal_plans", ACCOUNT_ID),
        ("deployment_id", DEPLOYMENT_ID),
        ("symbol", "SPY"),
        ("limit", "25"),
    ]


def test_governor_decisions_route_returns_read_model_with_filters() -> None:
    service = RecordingOperationsService()
    signal_plan_id = service.governor_decisions[0].signal_plan_id

    response = operations.list_governor_decisions(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        signal_plan_id=signal_plan_id,
        limit=25,
        service=service,
    )

    assert response.governor_decisions == service.governor_decisions
    assert service.calls == [
        ("list_governor_decision_traces", ACCOUNT_ID),
        ("deployment_id", DEPLOYMENT_ID),
        ("signal_plan_id", signal_plan_id),
        ("limit", "25"),
    ]


def test_research_evidence_routes_return_list_and_detail_without_trading_authority() -> None:
    service = RecordingOperationsService()
    evidence = service.research_evidence[0]

    list_response = operations.list_research_evidence(
        strategy_id=evidence.strategy_id,
        strategy_version_id=evidence.strategy_version_id,
        evidence_type="backtest_run",
        service=service,
    )
    detail_response = operations.get_research_evidence(evidence.run_id, service=service)

    assert list_response.evidence == service.research_evidence
    assert detail_response == evidence
    assert service.calls == [
        ("list_research_evidence", "backtest_run"),
        ("get_research_evidence", evidence.run_id),
    ]


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


# ---------------------------------------------------------------------------
# M10: RiskResolver detail in operations evaluation response
# ---------------------------------------------------------------------------


def test_list_evaluations_response_includes_risk_resolver_result() -> None:
    """M10: Operations evaluation list response exposes risk_resolver_result at top level.

    The AccountSignalPlanEvaluation domain object carries risk_resolver_result
    as a first-class field.  The API response serializes it directly — no
    separate extraction step needed.  This test pins that the field is non-None
    and accessible from the response object (not buried inside a sub-object).
    """
    from backend.app.domain import RiskResolverResult
    from uuid import uuid4

    signal_plan_id = uuid4()
    strategy_id = uuid4()
    risk_result = RiskResolverResult(
        account_id=ACCOUNT_ID,
        signal_plan_id=signal_plan_id,
        allowed=True,
        resolved_quantity=10.0,
        violations=(),
        warnings=(),
    )
    evaluation = AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=signal_plan_id,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=strategy_id,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
        risk_resolver_result=risk_result,
    )

    class RiskDetailService(RecordingOperationsService):
        def list_account_signal_plan_evaluations(self, **kwargs: object) -> tuple[AccountSignalPlanEvaluation, ...]:
            return (evaluation,)

    response = operations.list_account_signal_plan_evaluations(
        account_id=ACCOUNT_ID,
        deployment_id=None,
        signal_plan_id=None,
        limit=10,
        service=RiskDetailService(),
    )

    assert len(response.evaluations) == 1
    returned_evaluation = response.evaluations[0]
    # risk_resolver_result is a top-level field on AccountSignalPlanEvaluation.
    assert returned_evaluation.risk_resolver_result is not None
    assert returned_evaluation.risk_resolver_result.allowed is True
    assert returned_evaluation.risk_resolver_result.resolved_quantity == 10.0
    # Verify it serializes to JSON without losing the field.
    serialized = response.model_dump(mode="json")
    first_eval = serialized["evaluations"][0]
    assert "risk_resolver_result" in first_eval
    assert first_eval["risk_resolver_result"]["allowed"] is True

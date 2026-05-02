from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import risk_plans
from backend.app.ai import AIProvider, AIProviderStatus, AIServiceList, AIServiceRecord
from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.domain import BacktestRun, RiskDecisionCard, RiskDecisionMode, RiskDecisionStatus, TradingMode
from backend.app.domain._base import utc_now
from backend.app.persistence import SQLiteRuntimeStore


def _store(tmp_path) -> SQLiteRuntimeStore:  # type: ignore[no-untyped-def]
    return SQLiteRuntimeStore(tmp_path / "runtime.db")


def _http_client(store: SQLiteRuntimeStore) -> TestClient:
    app = FastAPI()
    app.include_router(risk_plans.router)
    app.dependency_overrides[risk_plans.get_risk_plan_store] = lambda: store
    return TestClient(app)


def _http_client_with_ai(store: SQLiteRuntimeStore, catalog: object) -> TestClient:
    app = FastAPI()
    app.include_router(risk_plans.router)
    app.dependency_overrides[risk_plans.get_risk_plan_store] = lambda: store
    app.dependency_overrides[risk_plans.get_risk_plan_ai_catalog] = lambda: catalog
    return TestClient(app)


class _FakeAICatalog:
    def __init__(self, services: tuple[AIServiceRecord, ...]) -> None:
        self.services = services
        self.called = False

    def list_services(self) -> AIServiceList:
        self.called = True
        return AIServiceList(services=self.services)


def _risk_config_payload() -> dict[str, object]:
    return {
        "sizing_method": "risk_percent",
        "risk_per_trade_pct": 1,
        "max_trade_notional": 10_000,
        "max_position_pct_of_equity": 20,
        "max_symbol_exposure_pct": 25,
        "max_open_positions": 5,
        "max_daily_loss_pct": 3,
        "max_drawdown_pct": 10,
        "fractional_quantity_allowed": False,
        "whole_share_rounding": "floor",
        "min_quantity": 1,
        "max_quantity": 100,
        "stop_required": True,
        "reject_if_no_stop": True,
        "target_required": False,
        "runner_allowed": True,
        "allow_scale_in": False,
        "allow_scale_out": True,
        "allow_short": False,
        "allow_extended_hours": False,
    }


def _create_plan(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/risk-plans",
        json={
            "name": "Balanced Momentum Risk",
            "description": "Balanced liquid ETF policy.",
            "risk_score": 5,
            "risk_tier": "balanced",
            "config": _risk_config_payload(),
            "created_by": "operator",
        },
    )
    assert response.status_code == 200
    return response.json()


def _risk_decision_card(
    *,
    run_id: UUID,
    account_id: UUID | None,
    risk_plan_id: UUID,
    risk_plan_version_id: UUID,
    decision: RiskDecisionStatus,
    reason_codes: tuple[str, ...] = (),
) -> RiskDecisionCard:
    return RiskDecisionCard(
        mode=RiskDecisionMode.BACKTEST,
        run_id=run_id,
        account_id=account_id,
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        signal_plan_id=uuid4(),
        symbol="SPY",
        side="buy",
        lifecycle_intent="open",
        timestamp=utc_now(),
        risk_plan_id=risk_plan_id,
        risk_plan_version_id=risk_plan_version_id,
        risk_score=5,
        risk_tier="balanced",
        account_equity=100_000,
        account_cash=100_000,
        buying_power=100_000,
        current_price=500,
        sizing_method="risk_percent",
        formula_used="risk_budget / stop_distance",
        final_quantity=10,
        final_notional=5_000,
        decision=decision,
        reason_codes=reason_codes,
        human_summary="Traceable risk decision for SPY.",
    )


def test_risk_plan_lifecycle_routes_create_version_activate_archive(tmp_path) -> None:
    store = _store(tmp_path)
    client = _http_client(store)

    created = _create_plan(client)
    risk_plan_id = created["risk_plan"]["risk_plan_id"]
    first_version_id = created["versions"][0]["risk_plan_version_id"]
    assert created["risk_plan"]["status"] == "draft"
    assert created["versions"][0]["config_fingerprint"]

    patched = client.patch(
        f"/api/v1/risk-plans/{risk_plan_id}",
        json={"name": "Balanced ETF Risk", "risk_score": 6},
    )
    assert patched.status_code == 200
    assert patched.json()["risk_plan"]["name"] == "Balanced ETF Risk"

    version_response = client.post(
        f"/api/v1/risk-plans/{risk_plan_id}/versions",
        json={"config": {**_risk_config_payload(), "risk_per_trade_pct": 0.5}},
    )
    assert version_response.status_code == 200
    second_version_id = version_response.json()["risk_plan_version_id"]
    assert version_response.json()["version"] == 2

    versions = client.get(f"/api/v1/risk-plans/{risk_plan_id}/versions")
    assert versions.status_code == 200
    assert [version["version"] for version in versions.json()["versions"]] == [1, 2]

    activated = client.post(
        f"/api/v1/risk-plans/{risk_plan_id}/activate",
        json={"risk_plan_version_id": second_version_id},
    )
    assert activated.status_code == 200
    assert activated.json()["risk_plan"]["status"] == "active"
    assert activated.json()["risk_plan"]["version"] == 2
    active_versions = [version for version in activated.json()["versions"] if version["status"] == "active"]
    assert [version["risk_plan_version_id"] for version in active_versions] == [second_version_id]

    rejected_patch = client.patch(f"/api/v1/risk-plans/{risk_plan_id}", json={"risk_score": 4})
    assert rejected_patch.status_code == 400
    assert rejected_patch.json()["detail"] == "only draft RiskPlans can be edited"

    archived = client.post(f"/api/v1/risk-plans/{risk_plan_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["risk_plan"]["status"] == "archived"
    assert {version["status"] for version in archived.json()["versions"]} == {"deprecated"}

    listed = client.get("/api/v1/risk-plans", params={"status": "archived", "risk_tier": "balanced"})
    assert listed.status_code == 200
    assert listed.json()["risk_plans"][0]["risk_plan_id"] == risk_plan_id
    assert UUID(first_version_id)


def test_research_derived_risk_plan_create_requires_source_run_id(tmp_path) -> None:
    store = _store(tmp_path)
    client = _http_client(store)

    response = client.post(
        "/api/v1/risk-plans",
        json={
            "name": "Optimization Winner",
            "description": "Research generated draft.",
            "risk_score": 5,
            "risk_tier": "balanced",
            "source": "optimization_generated",
            "config": _risk_config_payload(),
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "research-derived Risk Plans require source_run_id"
    assert store.list_risk_plans() == ()


def test_account_default_risk_plan_routes_assign_and_read(tmp_path) -> None:
    store = _store(tmp_path)
    client = _http_client(store)
    account = BrokerAccount(
        id=uuid4(),
        display_name="Alpaca Paper Account 1",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:acct:fingerprint",
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    store.save_broker_account(account)
    created = _create_plan(client)
    risk_plan_id = created["risk_plan"]["risk_plan_id"]
    risk_plan_version_id = created["versions"][0]["risk_plan_version_id"]

    empty = client.get(f"/api/v1/accounts/{account.id}/risk-plan")
    assert empty.status_code == 200
    assert empty.json()["risk_plan"] is None
    assert empty.json()["risk_plan_version"] is None

    assigned = client.put(
        f"/api/v1/accounts/{account.id}/risk-plan",
        json={
            "risk_plan_id": risk_plan_id,
            "risk_plan_version_id": risk_plan_version_id,
        },
    )
    assert assigned.status_code == 200
    assert assigned.json()["risk_plan"]["name"] == "Balanced Momentum Risk"
    assert assigned.json()["risk_plan_version"]["risk_plan_version_id"] == risk_plan_version_id

    persisted = store.load_broker_account(account.id)
    assert str(persisted.default_risk_plan_id) == risk_plan_id
    assert str(persisted.default_risk_plan_version_id) == risk_plan_version_id

    loaded = client.get(f"/api/v1/accounts/{account.id}/risk-plan")
    assert loaded.status_code == 200
    assert loaded.json() == assigned.json()


def test_account_risk_plan_assignment_rejects_mismatched_version(tmp_path) -> None:
    store = _store(tmp_path)
    client = _http_client(store)
    account = BrokerAccount(
        id=uuid4(),
        display_name="Alpaca Paper Account 1",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:acct:fingerprint",
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    store.save_broker_account(account)
    first = _create_plan(client)
    second = _create_plan(client)

    response = client.put(
        f"/api/v1/accounts/{account.id}/risk-plan",
        json={
            "risk_plan_id": first["risk_plan"]["risk_plan_id"],
            "risk_plan_version_id": second["versions"][0]["risk_plan_version_id"],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "risk_plan_version_id does not belong to risk_plan_id"


def test_risk_plan_list_rows_include_active_version_and_usage_summary(tmp_path) -> None:
    store = _store(tmp_path)
    client = _http_client(store)
    created = _create_plan(client)
    risk_plan_id = UUID(created["risk_plan"]["risk_plan_id"])
    first_version_id = UUID(created["versions"][0]["risk_plan_version_id"])
    account = BrokerAccount(
        id=uuid4(),
        display_name="Alpaca Paper Account 1",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:acct:fingerprint",
        validation_status=BrokerAccountValidationStatus.VALID,
        default_risk_plan_id=risk_plan_id,
        default_risk_plan_version_id=first_version_id,
    )
    store.save_broker_account(account)

    version_response = client.post(
        f"/api/v1/risk-plans/{risk_plan_id}/versions",
        json={"config": {**_risk_config_payload(), "risk_per_trade_pct": 0.5}},
    )
    second_version_id = version_response.json()["risk_plan_version_id"]
    activated = client.post(
        f"/api/v1/risk-plans/{risk_plan_id}/activate",
        json={"risk_plan_version_id": second_version_id},
    )
    assert activated.status_code == 200
    run_id = uuid4()
    now = utc_now()
    store.save_research_evidence(
        BacktestRun(
            run_id=run_id,
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            start=now - timedelta(days=10),
            end=now,
            bar_count=10,
            signal_plan_count=1,
            simulated_trade_count=1,
            metrics={"risk_plan_version_id": second_version_id, "sharpe": 1.2},
            created_at=now,
        )
    )

    listed = client.get("/api/v1/risk-plans")

    assert listed.status_code == 200
    row = listed.json()["risk_plans"][0]
    assert row["risk_plan_id"] == str(risk_plan_id)
    assert row["active_version_id"] == second_version_id
    assert row["active_version"]["risk_plan_version_id"] == second_version_id
    assert row["active_version"]["config"]["risk_per_trade_pct"] == 0.5
    assert row["linked_account_count"] == 1
    assert row["last_used_at"] is not None


def test_risk_plan_detail_includes_linked_accounts_backtests_and_decision_stats(tmp_path) -> None:
    store = _store(tmp_path)
    client = _http_client(store)
    created = _create_plan(client)
    risk_plan_id = UUID(created["risk_plan"]["risk_plan_id"])
    risk_plan_version_id = UUID(created["versions"][0]["risk_plan_version_id"])
    account = BrokerAccount(
        id=uuid4(),
        display_name="Alpaca Paper Account 1",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:acct:fingerprint",
        validation_status=BrokerAccountValidationStatus.VALID,
        default_risk_plan_id=risk_plan_id,
        default_risk_plan_version_id=risk_plan_version_id,
    )
    store.save_broker_account(account)
    run_id = uuid4()
    now = utc_now()
    strategy_id = uuid4()
    strategy_version_id = uuid4()
    store.save_research_evidence(
        BacktestRun(
            run_id=run_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            start=now - timedelta(days=5),
            end=now,
            bar_count=5,
            signal_plan_count=2,
            simulated_trade_count=2,
            metrics={
                "risk_plan_version_id": str(risk_plan_version_id),
                "sharpe": 1.4,
                "max_drawdown": -0.06,
                "total_return": 0.18,
                "monte_carlo": {"replications": 100},
                "warnings": ["thin sample"],
            },
            created_at=now,
        )
    )
    store.save_risk_decision_card(
        _risk_decision_card(
            run_id=run_id,
            account_id=account.id,
            risk_plan_id=risk_plan_id,
            risk_plan_version_id=risk_plan_version_id,
            decision=RiskDecisionStatus.APPROVED,
        )
    )
    store.save_risk_decision_card(
        _risk_decision_card(
            run_id=run_id,
            account_id=account.id,
            risk_plan_id=risk_plan_id,
            risk_plan_version_id=risk_plan_version_id,
            decision=RiskDecisionStatus.REJECTED,
            reason_codes=("stop_required",),
        )
    )

    response = client.get(f"/api/v1/risk-plans/{risk_plan_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["active_version_id"] == str(risk_plan_version_id)
    assert body["linked_accounts"] == [
        {
            "account_id": str(account.id),
            "account_name": "Alpaca Paper Account 1",
            "account_mode": "paper",
            "is_default": True,
            "last_risk_decision_at": body["linked_accounts"][0]["last_risk_decision_at"],
        }
    ]
    assert body["linked_accounts"][0]["last_risk_decision_at"] is not None
    assert body["backtest_usage"][0]["run_id"] == str(run_id)
    assert body["backtest_usage"][0]["strategy_id"] == str(strategy_id)
    assert body["backtest_usage"][0]["strategy_version_id"] == str(strategy_version_id)
    assert body["backtest_usage"][0]["sharpe"] == 1.4
    assert body["backtest_usage"][0]["monte_carlo_summary"] == {"replications": 100}
    assert body["backtest_usage"][0]["warnings"] == ["thin sample"]
    assert body["decision_stats"]["total"] == 2
    assert body["decision_stats"]["approved"] == 1
    assert body["decision_stats"]["rejected"] == 1
    assert body["decision_stats"]["top_rejection_reasons"] == [{"reason": "stop_required", "count": 1}]


def test_ai_draft_route_returns_unsaved_draft_and_guardrails(tmp_path) -> None:
    store = _store(tmp_path)
    service = AIServiceRecord(
        name="OpenAI Default",
        provider=AIProvider.OPENAI,
        status=AIProviderStatus.VALID,
        is_default=True,
        has_api_key=True,
    )
    catalog = _FakeAICatalog((service,))
    client = _http_client_with_ai(store, catalog)

    response = client.post(
        "/api/v1/risk-plans/ai-draft",
        json={
            "prompt": "Draft an aggressive ETF risk plan with extended hours.",
            "created_by": "operator",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert catalog.called is True
    assert body["risk_plan"]["status"] == "draft"
    assert body["risk_plan"]["source"] == "ai_generated"
    assert body["risk_plan"]["ai_generated"] is True
    assert body["risk_plan"]["ai_summary"]
    assert body["risk_plan_version"]["status"] == "draft"
    assert body["risk_plan_version"]["config"]["allow_extended_hours"] is True
    assert body["warnings"]
    assert "never assigned to an Account automatically" in " ".join(body["boundary_guardrails"])
    assert store.list_risk_plans() == ()


def test_ai_draft_route_requires_valid_ai_provider(tmp_path) -> None:
    store = _store(tmp_path)
    catalog = _FakeAICatalog(())
    client = _http_client_with_ai(store, catalog)

    response = client.post(
        "/api/v1/risk-plans/ai-draft",
        json={"prompt": "Draft a conservative risk plan."},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "no valid AI provider is configured"
    assert store.list_risk_plans() == ()

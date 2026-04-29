from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import risk_plans
from backend.app.api.server import app
from backend.app.ai import AIProvider, AIProviderStatus, AIServiceList, AIServiceRecord
from backend.app.persistence import SQLiteRuntimeStore


def _registered_http_routes() -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        path = getattr(route, "path", None)
        if not methods or not path:
            continue
        for method in methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            routes.add((method, path))
    return routes


def _registered_websocket_routes() -> set[str]:
    return {
        path
        for route in app.routes
        if (path := getattr(route, "path", None))
        and route.__class__.__name__.lower().endswith("websocketroute")
    }


def test_current_frontend_http_api_contract_is_registered() -> None:
    """Every API called from frontend/src/api must exist in FastAPI.

    This intentionally tracks the current frontend client surface only. Future
    create-run APIs for Backtests, Sim Lab, Optimization, and Walk-Forward are
    documented gaps until those frontend pages start calling them.
    """

    expected = {
        ("GET", "/api/v1/system/status"),
        ("GET", "/api/v1/system/streams"),
        ("GET", "/api/v1/system/settings"),
        ("PUT", "/api/v1/system/settings"),
        ("GET", "/api/v1/broker-accounts"),
        ("POST", "/api/v1/broker-accounts"),
        ("PATCH", "/api/v1/broker-accounts/{account_id}"),
        ("PUT", "/api/v1/broker-accounts/{account_id}/credentials"),
        ("POST", "/api/v1/broker-accounts/{account_id}/delete"),
        ("GET", "/api/v1/operations/overview"),
        ("GET", "/api/v1/operations/accounts/{account_id}"),
        ("POST", "/api/v1/operations/accounts/{account_id}/pause"),
        ("POST", "/api/v1/operations/accounts/{account_id}/resume"),
        ("POST", "/api/v1/operations/accounts/{account_id}/flatten"),
        ("POST", "/api/v1/operations/deployments/{deployment_id}/pause"),
        ("POST", "/api/v1/operations/deployments/{deployment_id}/resume"),
        ("POST", "/api/v1/operations/deployments/{deployment_id}/flatten"),
        ("POST", "/api/v1/operations/global/kill"),
        ("POST", "/api/v1/operations/global/resume"),
        ("GET", "/api/v1/operations/research-evidence"),
        ("GET", "/api/v1/operations/research-evidence/{evidence_id}"),
        ("GET", "/api/v1/operations/broker-orders/{broker_order_id}"),
        ("GET", "/api/v1/market-data/services"),
        ("GET", "/api/v1/data-center/historical-datasets"),
        ("GET", "/api/v1/data-center/historical-datasets/{dataset_id}"),
        ("GET", "/api/v1/data-center/historical-datasets/{dataset_id}/bars"),
        ("POST", "/api/v1/market-data/services/{service_id}/validate"),
        ("POST", "/api/v1/market-data/services/{service_id}/set-default"),
        ("POST", "/api/v1/market-data/services/{service_id}/default-for"),
        ("POST", "/api/v1/market-data/services/{service_id}/disable"),
        ("POST", "/api/v1/market-data/services/{service_id}/enable"),
        ("POST", "/api/v1/market-data/services/{service_id}/delete"),
        ("GET", "/api/v1/ai/providers"),
        ("POST", "/api/v1/ai/providers"),
        ("PUT", "/api/v1/ai/providers/{service_id}"),
        ("POST", "/api/v1/ai/providers/{service_id}/validate"),
        ("POST", "/api/v1/ai/providers/{service_id}/set-default"),
        ("POST", "/api/v1/ai/providers/{service_id}/disable"),
        ("POST", "/api/v1/ai/providers/{service_id}/delete"),
        ("GET", "/api/v1/chart-lab/health"),
        ("GET", "/api/v1/strategies"),
        ("POST", "/api/v1/strategies"),
        ("GET", "/api/v1/strategies/builder/features"),
        ("GET", "/api/v1/strategies/builder/features/aliases"),
        ("POST", "/api/v1/strategies/builder/features/validate"),
        ("POST", "/api/v1/strategies/builder/features/plan-preview"),
        ("POST", "/api/v1/strategies/builder/conditions/parse"),
        ("POST", "/api/v1/strategies/builder/reuse-matches"),
        ("POST", "/api/v1/strategies/composer/preview"),
        ("POST", "/api/v1/strategies/composer/drafts"),
        ("GET", "/api/v1/strategies/{strategy_id}"),
        ("PATCH", "/api/v1/strategies/{strategy_id}"),
        ("POST", "/api/v1/strategies/{strategy_id}/delete"),
        ("POST", "/api/v1/strategies/{strategy_id}/deprecate"),
        ("GET", "/api/v1/strategies/{strategy_id}/versions"),
        ("POST", "/api/v1/strategies/{strategy_id}/versions"),
        ("PATCH", "/api/v1/strategies/{strategy_id}/versions/{version_id}"),
        ("POST", "/api/v1/strategies/{strategy_id}/versions/{version_id}/freeze"),
        ("GET", "/api/v1/watchlists"),
        ("POST", "/api/v1/watchlists"),
        ("GET", "/api/v1/watchlists/{watchlist_id}"),
        ("PATCH", "/api/v1/watchlists/{watchlist_id}"),
        ("POST", "/api/v1/watchlists/{watchlist_id}/delete"),
        ("POST", "/api/v1/watchlists/{watchlist_id}/archive"),
        ("POST", "/api/v1/watchlists/{watchlist_id}/snapshot"),
        ("POST", "/api/v1/watchlists/{watchlist_id}/refresh"),
        ("GET", "/api/v1/deployments"),
        ("POST", "/api/v1/deployments"),
        ("GET", "/api/v1/deployments/{deployment_id}"),
        ("PATCH", "/api/v1/deployments/{deployment_id}"),
        ("POST", "/api/v1/deployments/{deployment_id}/delete"),
        ("POST", "/api/v1/deployments/{deployment_id}/start"),
        ("POST", "/api/v1/deployments/{deployment_id}/stop"),
        ("POST", "/api/v1/deployments/{deployment_id}/pause"),
        ("POST", "/api/v1/deployments/{deployment_id}/resume"),
        ("POST", "/api/v1/deployments/{deployment_id}/subscribe"),
        ("POST", "/api/v1/deployments/{deployment_id}/unsubscribe"),
        ("GET", "/api/v1/research/backtests"),
        ("POST", "/api/v1/research/backtests"),
        ("GET", "/api/v1/research/backtests/{run_id}"),
        ("POST", "/api/v1/research/backtests/{run_id}/cancel"),
        ("GET", "/api/v1/research/backtests/{run_id}/results"),
        ("GET", "/api/v1/research/backtests/{run_id}/metrics"),
        ("POST", "/api/v1/data-center/historical-datasets/ingest"),
        ("GET", "/api/v1/screeners"),
        ("POST", "/api/v1/screeners"),
        ("GET", "/api/v1/screeners/presets"),
        ("GET", "/api/v1/screeners/metrics"),
        ("GET", "/api/v1/screeners/fields"),
        ("GET", "/api/v1/screeners/templates"),
        ("POST", "/api/v1/screeners/from-template"),
        ("POST", "/api/v1/screeners/ai/interpret"),
        ("GET", "/api/v1/screeners/market-lists"),
        ("GET", "/api/v1/market-lists"),
        ("POST", "/api/v1/market-lists/{template_key}/run"),
        ("GET", "/api/v1/screeners/{screener_id}"),
        ("PATCH", "/api/v1/screeners/{screener_id}"),
        ("POST", "/api/v1/screeners/{screener_id}/delete"),
        ("POST", "/api/v1/screeners/{screener_id}/archive"),
        ("POST", "/api/v1/screeners/{screener_id}/versions"),
        ("POST", "/api/v1/screeners/{screener_id}/run"),
        ("GET", "/api/v1/screeners/{screener_id}/runs"),
        ("GET", "/api/v1/screeners/runs/{run_id}"),
        ("POST", "/api/v1/screeners/runs/{run_id}/rerun"),
        ("GET", "/api/v1/screeners/runs/{run_id}/diff"),
        ("POST", "/api/v1/screeners/runs/{run_id}/save-as-watchlist"),
        ("GET", "/api/v1/discovery-schedules"),
        ("POST", "/api/v1/discovery-schedules"),
        ("POST", "/api/v1/discovery-schedules/run-due"),
        ("GET", "/api/v1/discovery-schedules/{schedule_id}"),
        ("PATCH", "/api/v1/discovery-schedules/{schedule_id}"),
        ("POST", "/api/v1/discovery-schedules/{schedule_id}/pause"),
        ("POST", "/api/v1/discovery-schedules/{schedule_id}/resume"),
        ("POST", "/api/v1/discovery-schedules/{schedule_id}/archive"),
        ("POST", "/api/v1/discovery-schedules/{schedule_id}/delete"),
        ("POST", "/api/v1/discovery-schedules/{schedule_id}/run-now"),
        ("GET", "/api/v1/discovery-schedules/{schedule_id}/executions"),
        ("GET", "/api/v1/risk-decisions/{risk_decision_id}"),
        ("GET", "/api/v1/risk-decisions"),
        ("POST", "/api/v1/research/sim_lab/runs"),
        ("GET", "/api/v1/sim-lab/sessions"),
        ("POST", "/api/v1/sim-lab/sessions"),
        ("GET", "/api/v1/sim-lab/sessions/{session_id}"),
        ("DELETE", "/api/v1/sim-lab/sessions/{session_id}"),
        ("POST", "/api/v1/sim-lab/sessions/{session_id}/run"),
        ("GET", "/api/v1/sim-lab/sessions/{session_id}/results"),
        ("GET", "/api/v1/optimization/runs"),
        ("POST", "/api/v1/optimization/runs"),
        ("GET", "/api/v1/optimization/runs/{run_id}"),
        ("DELETE", "/api/v1/optimization/runs/{run_id}"),
        ("GET", "/api/v1/walk-forward/runs"),
        ("POST", "/api/v1/walk-forward/runs"),
        ("GET", "/api/v1/walk-forward/runs/{run_id}"),
        ("DELETE", "/api/v1/walk-forward/runs/{run_id}"),
        ("POST", "/api/v1/research/jobs/backtest"),
        ("POST", "/api/v1/research/jobs/walk-forward"),
        ("POST", "/api/v1/research/jobs/optimization"),
        ("GET", "/api/v1/research/jobs"),
        ("GET", "/api/v1/research/jobs/{job_id}"),
        ("POST", "/api/v1/research/jobs/{job_id}/cancel"),
        # Risk Plan slice (RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §8.1 + §8.2).
        ("GET", "/api/v1/risk-plans"),
        ("POST", "/api/v1/risk-plans"),
        ("GET", "/api/v1/risk-plans/{risk_plan_id}"),
        ("PATCH", "/api/v1/risk-plans/{risk_plan_id}"),
        ("GET", "/api/v1/risk-plans/{risk_plan_id}/versions"),
        ("POST", "/api/v1/risk-plans/{risk_plan_id}/versions"),
        ("POST", "/api/v1/risk-plans/{risk_plan_id}/activate"),
        ("POST", "/api/v1/risk-plans/{risk_plan_id}/archive"),
        ("POST", "/api/v1/risk-plans/ai-draft"),
        ("GET", "/api/v1/accounts/{account_id}/risk-plan"),
        ("PUT", "/api/v1/accounts/{account_id}/risk-plan"),
    }

    registered = _registered_http_routes()

    assert expected <= registered


def test_current_frontend_websocket_api_contract_is_registered() -> None:
    expected = {
        "/api/v1/chart-lab/stream",
        "/api/v1/research/sim_lab/stream",
    }

    assert expected <= _registered_websocket_routes()


# ---------------------------------------------------------------------------
# Risk Plan slice — request/response payload-shape contract.
#
# The route-existence test above only proves a route is registered. These
# tests lock the actual request and response *shapes* against what the
# frontend's Zod schemas expect, so a silent drift cannot ship a green slice
# with a broken UI again.
#
# The bug this exists to catch: the create body originally sent
# `ai_notes: <object>` while the backend uses `ai_summary: str | None`, with
# extra="forbid". That survived the route-registered test but blocked every
# save in the browser.
# ---------------------------------------------------------------------------


class _FakeAICatalog:
    def __init__(self, services: tuple[AIServiceRecord, ...]) -> None:
        self.services = services

    def list_services(self) -> AIServiceList:
        return AIServiceList(services=self.services)


def _isolated_risk_plan_app(tmp_path) -> tuple[TestClient, SQLiteRuntimeStore]:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    isolated = FastAPI()
    isolated.include_router(risk_plans.router)
    isolated.dependency_overrides[risk_plans.get_risk_plan_store] = lambda: store
    return TestClient(isolated), store


def _isolated_risk_plan_app_with_ai(  # type: ignore[no-untyped-def]
    tmp_path,
    catalog: _FakeAICatalog,
) -> tuple[TestClient, SQLiteRuntimeStore]:
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    isolated = FastAPI()
    isolated.include_router(risk_plans.router)
    isolated.dependency_overrides[risk_plans.get_risk_plan_store] = lambda: store
    isolated.dependency_overrides[risk_plans.get_risk_plan_ai_catalog] = lambda: catalog
    return TestClient(isolated), store


def _frontend_create_payload(*, ai_summary: str | None = None) -> dict[str, object]:
    """Mirror of `CreateRiskPlanRequestSchema` in
    `frontend/src/api/schemas/riskPlans.ts` — the exact body the Create drawer
    sends. If a backend rename ever forces the frontend to drop a field, the
    update belongs here too."""

    return {
        "name": "Balanced Momentum Risk",
        "description": "Balanced ETF policy",
        "risk_score": 5,
        "risk_tier": "balanced",
        "source": "manual",
        "ai_generated": ai_summary is not None,
        "ai_summary": ai_summary,
        "config": {
            "sizing_method": "risk_percent",
            "risk_per_trade_pct": 1.0,
            "max_open_positions": 5,
            "max_daily_loss_pct": 3.0,
            "max_drawdown_pct": 10.0,
            "stop_required": True,
            "reject_if_no_stop": True,
            "fractional_quantity_allowed": False,
            "whole_share_rounding": "floor",
        },
    }


def test_risk_plan_create_accepts_frontend_payload_and_returns_envelope(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client, _ = _isolated_risk_plan_app(tmp_path)
    response = client.post("/api/v1/risk-plans", json=_frontend_create_payload())
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) >= {"risk_plan", "versions"}
    assert isinstance(body["versions"], list) and len(body["versions"]) == 1
    plan = body["risk_plan"]
    assert plan["name"] == "Balanced Momentum Risk"
    assert plan["status"] == "draft"
    assert plan["source"] == "manual"
    assert plan["ai_summary"] is None
    # Legacy frontend invention must not leak back in via passthrough.
    assert "ai_notes" not in plan


def test_risk_plan_create_with_ai_summary_persists_string(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Save-as-Risk-Plan flow attaches a one-line summary (string), not an
    object. Locks the contract §4.1 shape (`ai_summary: str | None`)."""

    client, _ = _isolated_risk_plan_app(tmp_path)
    response = client.post(
        "/api/v1/risk-plans",
        json=_frontend_create_payload(ai_summary="WF recommended balanced 1% per trade"),
    )
    assert response.status_code == 200
    plan = response.json()["risk_plan"]
    assert plan["ai_generated"] is True
    assert plan["ai_summary"] == "WF recommended balanced 1% per trade"


def test_risk_plan_create_rejects_legacy_ai_notes_field(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Regression guard: the bug fixed on 2026-04-28 — the frontend used to
    send `ai_notes` (rich object) which the backend forbids via
    extra="forbid". If any caller ever sends it again this fails fast at
    the API boundary."""

    client, _ = _isolated_risk_plan_app(tmp_path)
    payload = _frontend_create_payload()
    payload["ai_notes"] = {"summary": "...", "warnings": []}
    response = client.post("/api/v1/risk-plans", json=payload)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(
        error.get("loc", []) == ["body", "ai_notes"]
        and error.get("type") == "extra_forbidden"
        for error in detail
    )


def test_risk_plan_patch_accepts_ai_summary_and_rejects_ai_notes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """PATCH is the path the Edit drawer uses. It must accept `ai_summary`
    (string) and reject the legacy `ai_notes` (object)."""

    client, _ = _isolated_risk_plan_app(tmp_path)
    created = client.post("/api/v1/risk-plans", json=_frontend_create_payload()).json()
    risk_plan_id = created["risk_plan"]["risk_plan_id"]

    accepted = client.patch(
        f"/api/v1/risk-plans/{risk_plan_id}",
        json={"name": "Edited", "ai_summary": "Operator clarified intent"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["risk_plan"]["ai_summary"] == "Operator clarified intent"

    rejected = client.patch(
        f"/api/v1/risk-plans/{risk_plan_id}",
        json={"name": "Edited", "ai_notes": {"summary": "..."}},
    )
    assert rejected.status_code == 422


def test_risk_plan_get_returns_envelope(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """GET detail returns `{risk_plan, versions}`; the typed client flattens
    that into the flat `RiskPlanDetail` shape consumers read directly."""

    client, _ = _isolated_risk_plan_app(tmp_path)
    created = client.post("/api/v1/risk-plans", json=_frontend_create_payload()).json()
    risk_plan_id = created["risk_plan"]["risk_plan_id"]

    response = client.get(f"/api/v1/risk-plans/{risk_plan_id}")
    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) >= {"risk_plan", "versions"}
    assert body["risk_plan"]["risk_plan_id"] == risk_plan_id


def test_risk_plan_ai_draft_response_matches_frontend_zod_keys(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The AI-draft response shape is locked at the keys the frontend's
    `RiskPlanAiDraftResponseSchema` parses. Backend cannot rename `risk_plan`
    → `draft` (the original frontend Zod bug) without updating the typed
    client."""

    catalog = _FakeAICatalog(
        (
            AIServiceRecord(
                name="GROQ Default",
                provider=AIProvider.GROQ,
                status=AIProviderStatus.VALID,
                is_default=True,
                has_api_key=True,
            ),
        )
    )
    client, _ = _isolated_risk_plan_app_with_ai(tmp_path, catalog)

    response = client.post(
        "/api/v1/risk-plans/ai-draft",
        json={"prompt": "balanced day-trading plan, 1% per trade, 5 positions"},
    )
    assert response.status_code == 200
    body = response.json()
    expected = {
        "risk_plan",
        "risk_plan_version",
        "warnings",
        "ai_provider_id",
        "ai_provider_name",
        "boundary_guardrails",
    }
    assert expected <= set(body.keys())
    # Locked: legacy frontend Zod keys must not be reintroduced.
    assert "draft" not in body
    assert "ai_notes" not in body
    assert body["risk_plan"]["source"] == "ai_generated"
    assert body["risk_plan"]["ai_generated"] is True
    # `risk_plan_version.config` carries the form fields the drawer expects.
    cfg = body["risk_plan_version"]["config"]
    assert cfg["sizing_method"] in {
        "risk_percent",
        "fixed_shares",
        "fixed_notional",
        "volatility_adjusted",
        "account_percent",
        "custom",
    }

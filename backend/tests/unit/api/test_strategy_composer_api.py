from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import strategies
from backend.app.strategies import StrategyService
from backend.app.strategies.persistence import StrategyRepository
from backend.app.strategies_v4.persistence import StrategyV4Repository
from backend.app.strategies_v4.service import StrategyV4Service


def _client(tmp_path: Path) -> TestClient:
    service = StrategyService(repository=StrategyRepository(tmp_path / "ut.db"))
    v4_service = StrategyV4Service(repository=StrategyV4Repository(tmp_path / "ut_v4.db"))
    app = FastAPI()
    app.include_router(strategies.router)
    app.dependency_overrides[strategies.get_strategy_service] = lambda: service
    app.dependency_overrides[strategies.get_strategy_v4_service] = lambda: v4_service
    return TestClient(app)


def test_strategy_builder_feature_and_composer_routes(tmp_path: Path) -> None:
    client = _client(tmp_path)

    catalog = client.get("/api/v1/strategies/builder/features")
    assert catalog.status_code == 200
    assert any(item["kind"] == "rsi" for item in catalog.json())
    assert any(item["display_name"] == "RSI" for item in catalog.json())

    aliases = client.get("/api/v1/strategies/builder/features/aliases")
    assert aliases.status_code == 200
    assert aliases.json()["rsi21"] == "5m.rsi:length=21[0]"

    validation = client.post(
        "/api/v1/strategies/builder/features/validate",
        json={"feature_refs": ["sma20"], "consumer": "backtest"},
    )
    assert validation.status_code == 200
    assert validation.json()["valid"] is True

    condition = client.post(
        "/api/v1/strategies/builder/conditions/parse",
        json={
            "logical_exit_rule": {
                "kind": "bars_since_entry",
                "bars": 6,
            }
        },
    )
    assert condition.status_code == 200
    assert condition.json()["valid"] is True

    # new body shape: no symbols, no notes
    draft = client.post(
        "/api/v1/strategies/composer/preview",
        json={"prompt": "green bar long entry with exit after 30 minutes"},
    )
    assert draft.status_code == 200
    body = draft.json()
    assert body["validation"]["valid"] is True
    # no universe or risk_plan in response
    assert "suggested_universe" not in body
    assert "suggested_risk_plan" not in body
    assert "execution_style" in body
    assert "signal_plan_shape" in body
    assert "chart_lab" not in body["launch_plans"]
    assert body["launch_plans"]["backtest"]["route"] == "/api/v1/research/jobs/backtest"
    assert body["launch_plans"]["backtest"]["ready"] is False
    assert body["launch_plans"]["walk_forward"]["route"] == "/api/v1/research/jobs/walk-forward"


def test_strategy_builder_frontend_safe_contract_responses(tmp_path: Path) -> None:
    client = _client(tmp_path)

    validation = client.post(
        "/api/v1/strategies/builder/features/validate",
        json={"feature_refs": ["not_a_feature"], "consumer": "backtest"},
    )
    validation_body = validation.json()
    assert validation.status_code == 200
    assert validation_body["valid"] is False
    assert validation_body["items"][0]["input"] == "not_a_feature"
    assert validation_body["items"][0]["error_code"] == "unsupported_feature"

    parsed = client.post(
        "/api/v1/strategies/builder/conditions/parse",
        json={
            "logical_exit_rule": {
                "kind": "hybrid",
                "operator": "any",
                "children": [
                    {"kind": "bars_since_entry", "bars": 5},
                    {"kind": "time_of_day_et", "time_of_day_et": "15:55"},
                ],
            }
        },
    )
    parsed_body = parsed.json()
    assert parsed.status_code == 200
    assert parsed_body["valid"] is True
    assert parsed_body["normalized_logical_exit_rule"]["kind"] == "hybrid"
    assert parsed_body["readable_summary"] == "logical exit: hybrid"

    draft = client.post(
        "/api/v1/strategies/composer/preview",
        json={"prompt": "green bar entry exit after 30 minutes"},
    )
    draft_body = draft.json()
    assert draft.status_code == 200
    assert draft_body["strategy"]["name"]
    assert draft_body["validation"]["feature_plan_preview"]["valid"] is True
    assert draft_body["launch_plans"]["backtest"]["request"]["request"]["risk_plan_version_id"] is None
    assert "start" in draft_body["launch_plans"]["backtest"]["missing_fields"]


def test_composer_preview_rejects_symbols_field(tmp_path: Path) -> None:
    """symbols is no longer an accepted field on AIComposerRequest."""
    client = _client(tmp_path)

    draft = client.post(
        "/api/v1/strategies/composer/preview",
        json={"prompt": "green bar entry", "symbols": ["SPY"]},
    )

    assert draft.status_code == 422
    detail = draft.json()["detail"]
    assert any("extra_forbidden" in str(item) or "symbols" in str(item) for item in detail)


def test_composer_preview_rejects_notes_field(tmp_path: Path) -> None:
    """notes is no longer an accepted field on AIComposerRequest."""
    client = _client(tmp_path)

    draft = client.post(
        "/api/v1/strategies/composer/preview",
        json={"prompt": "green bar entry", "notes": "some notes"},
    )

    assert draft.status_code == 422


def test_composer_preview_with_explicit_preset(tmp_path: Path) -> None:
    client = _client(tmp_path)

    draft = client.post(
        "/api/v1/strategies/composer/preview",
        json={
            "prompt": "bracket entry strategy",
            "execution_style_preset": "bracket_stop_target",
            "execution_style_overrides": {"stop_pct": 1.0, "target_pct": 2.0},
        },
    )

    assert draft.status_code == 200
    body = draft.json()
    assert body["signal_plan_shape"]["preset"] == "bracket_stop_target"
    assert body["signal_plan_shape"]["stop"] is not None
    assert len(body["signal_plan_shape"]["targets"]) == 1

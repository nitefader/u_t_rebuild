from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.app.api.routes import research_jobs
from backend.app.domain import ResearchJobKind


def _base_request() -> dict[str, object]:
    return {
        "strategy_id": str(uuid4()),
        "strategy_version_id": str(uuid4()),
        "strategy_controls_version_id": str(uuid4()),
        "execution_plan_version_id": str(uuid4()),
        "symbols": ["SPY"],
        "start": "2026-01-01T00:00:00+00:00",
        "end": "2026-02-01T00:00:00+00:00",
        "initial_capital": 100_000,
        "cost_model": {"commission_per_trade": 0, "slippage_bps": 0},
        "source": "yahoo",
        "timeframe": "1d",
    }


def test_backtest_job_validation_requires_deployment_like_components() -> None:
    request = _base_request()
    request.pop("strategy_controls_version_id")
    request["risk_plan_version_id"] = str(uuid4())

    with pytest.raises(HTTPException) as exc_info:
        research_jobs._validate_job_request(ResearchJobKind.BACKTEST, request)

    assert exc_info.value.status_code == 422
    assert "strategy_controls_version_id" in str(exc_info.value.detail)


def test_walk_forward_job_validation_requires_base_risk_plan() -> None:
    request = _base_request()
    request["sweep"] = {"enabled": True, "parameters": []}

    with pytest.raises(HTTPException) as exc_info:
        research_jobs._validate_job_request(ResearchJobKind.WALK_FORWARD, request)

    assert exc_info.value.status_code == 422
    assert "base_risk_plan_version_id" in str(exc_info.value.detail)


def test_optimization_job_validation_returns_canonical_payload() -> None:
    request = _base_request()
    base_risk_plan_version_id = str(uuid4())
    request["sweep"] = {
        "base_risk_plan_version_id": base_risk_plan_version_id,
        "parameters": [{"field": "risk_per_trade_pct", "values": [0.5, 1.0]}],
    }

    validated = research_jobs._validate_job_request(ResearchJobKind.OPTIMIZATION, request)

    assert validated["strategy_controls_version_id"] == request["strategy_controls_version_id"]
    assert validated["execution_plan_version_id"] == request["execution_plan_version_id"]
    assert validated["sweep"]["base_risk_plan_version_id"] == base_risk_plan_version_id
    assert validated["sweep"]["parameters"][0]["field"] == "risk_per_trade_pct"

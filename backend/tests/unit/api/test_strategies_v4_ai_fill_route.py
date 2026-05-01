"""Route tests for POST /api/v1/strategies/v4/ai-fill."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.ai.llm_client import LLMClientError, LLMResponse
from backend.app.ai.providers import AIProvider
from backend.app.domain.strategy_v4 import ValidationStatusV4
from backend.app.strategies_v4.ai_seedfill import AISeedFillError, AISeedFillResponse
from backend.app.strategies_v4.models import StrategyVersionV4Draft


# ---------------------------------------------------------------------------
# Minimal valid draft (IBS strategy)
# ---------------------------------------------------------------------------

def _ibs_draft() -> StrategyVersionV4Draft:
    return StrategyVersionV4Draft.model_validate(
        {
            "name": "IBS Mean Reversion",
            "entries": {"long": {"expression_text": "ibs < 0.2"}},
            "stops": [{"mode": "simple", "scope": "all", "simple_type": "%", "simple_value": 2.0}],
            "legs": [
                {
                    "position": 1,
                    "kind": "target",
                    "size_pct": 1.0,
                    "target_type": "%",
                    "target_value": 4.0,
                    "on_fill_action": {"kind": "leave", "offset_value": None},
                }
            ],
        }
    )


def _ok_ai_response() -> AISeedFillResponse:
    return AISeedFillResponse(
        draft=_ibs_draft(),
        validation_status=ValidationStatusV4(valid=True),
        provider_used=AIProvider.GROQ,
        model_used="llama-3.1-70b-versatile",
        raw_response_excerpt='{"name":"IBS Mean Reversion"',
        notes=("Mean reversion on daily bars.",),
    )


# ---------------------------------------------------------------------------
# App fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    from fastapi import FastAPI
    from backend.app.api.routes.strategies_v4 import router

    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _build_request_body(prompt: str = "IBS mean reversion on 1d, long only") -> dict:
    return {"prompt": prompt}


# Patch paths — imports are at module level in the route file
_RESOLVE_CLIENT = "backend.app.api.routes.strategies_v4.resolve_default_llm_client"
_SEED_FILL = "backend.app.api.routes.strategies_v4.seed_fill_strategy"
_GET_CATALOG = "backend.app.api.routes.strategies_v4._get_ai_provider_catalog"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestAiFillHappyPath:
    def test_200_with_valid_draft(self, client):
        """Happy path: returns 200 with a valid AISeedFillResponse body."""
        with (
            patch(_GET_CATALOG, return_value=MagicMock()),
            patch(_RESOLVE_CLIENT, return_value=MagicMock()),
            patch(_SEED_FILL, return_value=_ok_ai_response()),
        ):
            resp = client.post(
                "/api/v1/strategies/v4/ai-fill",
                json=_build_request_body(),
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["draft"]["name"] == "IBS Mean Reversion"
        assert body["validation_status"]["valid"] is True
        assert body["provider_used"] == "groq"
        assert body["model_used"] == "llama-3.1-70b-versatile"


# ---------------------------------------------------------------------------
# 412 — no default provider
# ---------------------------------------------------------------------------

class TestAiFill412:
    def test_412_when_no_default_provider(self, client):
        """Returns 412 when no default AI provider is configured."""
        with (
            patch(_GET_CATALOG, return_value=MagicMock()),
            patch(
                _RESOLVE_CLIENT,
                side_effect=LLMClientError("no default AI provider configured"),
            ),
        ):
            resp = client.post(
                "/api/v1/strategies/v4/ai-fill",
                json=_build_request_body(),
            )

        assert resp.status_code == 412
        assert "no default AI provider" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 502 — LLM HTTP failure
# ---------------------------------------------------------------------------

class TestAiFill502:
    def test_502_when_llm_factory_fails_with_non_default_message(self, client):
        """Returns 502 when resolve_default_llm_client raises a non-412 error."""
        with (
            patch(_GET_CATALOG, return_value=MagicMock()),
            patch(
                _RESOLVE_CLIENT,
                side_effect=LLMClientError("default provider has no credentials"),
            ),
        ):
            resp = client.post(
                "/api/v1/strategies/v4/ai-fill",
                json=_build_request_body(),
            )

        assert resp.status_code == 502

    def test_502_when_llm_invoke_fails(self, client):
        """Returns 502 when seed_fill_strategy propagates an LLMClientError."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = LLMClientError("Groq returned HTTP 500: internal server error")

        with (
            patch(_GET_CATALOG, return_value=MagicMock()),
            patch(_RESOLVE_CLIENT, return_value=mock_llm),
            patch(_SEED_FILL, side_effect=LLMClientError("Groq returned HTTP 500")),
        ):
            resp = client.post(
                "/api/v1/strategies/v4/ai-fill",
                json=_build_request_body(),
            )

        assert resp.status_code == 502


# ---------------------------------------------------------------------------
# 422 — malformed LLM output
# ---------------------------------------------------------------------------

class TestAiFill422:
    def test_422_when_llm_returns_malformed_json(self, client):
        """Returns 422 when LLM output is not valid JSON."""
        with (
            patch(_GET_CATALOG, return_value=MagicMock()),
            patch(_RESOLVE_CLIENT, return_value=MagicMock()),
            patch(
                _SEED_FILL,
                side_effect=AISeedFillError("LLM returned non-JSON: Sure! Here is ..."),
            ),
        ):
            resp = client.post(
                "/api/v1/strategies/v4/ai-fill",
                json=_build_request_body(),
            )

        assert resp.status_code == 422
        assert "non-JSON" in resp.json()["detail"]

    def test_422_when_schema_validation_fails(self, client):
        """Returns 422 when LLM output fails pydantic schema validation."""
        with (
            patch(_GET_CATALOG, return_value=MagicMock()),
            patch(_RESOLVE_CLIENT, return_value=MagicMock()),
            patch(
                _SEED_FILL,
                side_effect=AISeedFillError(
                    "LLM output did not match draft schema: 1 validation error"
                ),
            ),
        ):
            resp = client.post(
                "/api/v1/strategies/v4/ai-fill",
                json=_build_request_body(),
            )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 422 — short prompt (request-level validation)
# ---------------------------------------------------------------------------

class TestAiFillRequestValidation:
    def test_422_when_prompt_too_short(self, client):
        """FastAPI/pydantic rejects prompts under 8 characters."""
        resp = client.post(
            "/api/v1/strategies/v4/ai-fill",
            json={"prompt": "short"},
        )
        assert resp.status_code == 422

"""Unit tests for backend.app.strategies_v4.ai_seedfill."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.app.ai.llm_client import LLMClientError, LLMResponse
from backend.app.ai.providers import AIProvider
from backend.app.strategies_v4.ai_seedfill import (
    AISeedFillError,
    AISeedFillRequest,
    seed_fill_strategy,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_llm_client(response_text: str) -> MagicMock:
    """Return a fake LLM client that returns *response_text* from invoke()."""
    client = MagicMock()
    client.invoke.return_value = LLMResponse(
        text=response_text,
        provider=AIProvider.GROQ,
        model="llama-3.1-70b-versatile",
        finish_reason="stop",
        usage_tokens_in=200,
        usage_tokens_out=100,
    )
    return client


def _ibs_draft_json(**overrides) -> str:
    """Return a minimal valid IBS strategy draft as JSON."""
    draft = {
        "name": "IBS Mean Reversion",
        "description": "Internal bar strength mean reversion on 1d.",
        "identity": {"tags": ["mean_reversion"], "direction": "long"},
        "variables": [
            {"name": "ibs", "expression_text": "(bar.close - bar.low) / (bar.high - bar.low)", "kind": "expression"}
        ],
        "entries": {
            "long": {"expression_text": "ibs < 0.2"}
        },
        "stops": [
            {"mode": "simple", "scope": "all", "simple_type": "%", "simple_value": 2.0}
        ],
        "legs": [
            {
                "position": 1,
                "kind": "target",
                "size_pct": 1.0,
                "target_type": "%",
                "target_value": 4.0,
                "on_fill_action": {"kind": "leave", "offset_value": None}
            }
        ],
        "logical_exits": {"long": [], "short": []},
    }
    draft.update(overrides)
    return json.dumps(draft)


def _noop_validate_expression(expr_text: str, variable_names=()) -> MagicMock:
    """Fake validate_expression — always returns valid with no errors."""
    result = MagicMock()
    result.valid = True
    result.errors = []
    result.warnings = []
    return result


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestSeedFillHappyPath:
    def test_returns_response_with_non_none_long_entry(self):
        """Happy path: IBS draft returned, entries.long is present."""
        client = _make_llm_client(_ibs_draft_json())
        request = AISeedFillRequest(prompt="Mean reversion with IBS on 1d, long only")

        response = seed_fill_strategy(
            request, client, validate_expression_fn=_noop_validate_expression
        )

        assert response.draft.entries.long is not None
        assert response.draft.name == "IBS Mean Reversion"

    def test_validation_status_valid_when_expressions_clean(self):
        """When all expressions pass, validation_status.valid is True."""
        client = _make_llm_client(_ibs_draft_json())
        request = AISeedFillRequest(prompt="IBS mean reversion strategy")

        response = seed_fill_strategy(
            request, client, validate_expression_fn=_noop_validate_expression
        )

        assert response.validation_status.valid is True
        assert len(response.validation_status.errors) == 0

    def test_provider_and_model_forwarded(self):
        """provider_used and model_used come from the LLM response."""
        client = _make_llm_client(_ibs_draft_json())
        request = AISeedFillRequest(prompt="IBS mean reversion strategy")

        response = seed_fill_strategy(
            request, client, validate_expression_fn=_noop_validate_expression
        )

        assert response.provider_used == AIProvider.GROQ
        assert response.model_used == "llama-3.1-70b-versatile"

    def test_raw_response_excerpt_is_first_500_chars(self):
        """raw_response_excerpt is the first 500 chars of LLM output."""
        long_text = _ibs_draft_json()
        client = _make_llm_client(long_text)
        request = AISeedFillRequest(prompt="IBS strategy")

        response = seed_fill_strategy(
            request, client, validate_expression_fn=_noop_validate_expression
        )

        assert response.raw_response_excerpt == long_text[:500]

    def test_notes_extracted_from_json(self):
        """Notes key is extracted before pydantic parsing and returned in response."""
        draft_with_notes = json.loads(_ibs_draft_json())
        draft_with_notes["notes"] = ["This is a mean reversion strategy.", "Use on liquid daily stocks."]
        client = _make_llm_client(json.dumps(draft_with_notes))
        request = AISeedFillRequest(prompt="IBS strategy")

        response = seed_fill_strategy(
            request, client, validate_expression_fn=_noop_validate_expression
        )

        assert "This is a mean reversion strategy." in response.notes

    def test_current_draft_appended_to_user_prompt(self):
        """When current_draft is provided, it appears in the user prompt."""
        client = _make_llm_client(_ibs_draft_json())
        # Build a minimal existing draft
        from backend.app.strategies_v4.models import StrategyVersionV4Draft
        existing = StrategyVersionV4Draft.model_validate(json.loads(_ibs_draft_json()))
        request = AISeedFillRequest(
            prompt="Refine this strategy to add RSI confirmation",
            current_draft=existing,
        )

        seed_fill_strategy(request, client, validate_expression_fn=_noop_validate_expression)

        user_prompt_sent = client.invoke.call_args[0][0].user_prompt
        assert "Current draft for context" in user_prompt_sent
        assert "IBS Mean Reversion" in user_prompt_sent


# ---------------------------------------------------------------------------
# Malformed JSON
# ---------------------------------------------------------------------------

class TestSeedFillMalformedJson:
    def test_non_json_response_raises(self):
        """LLM returning prose (non-JSON) raises AISeedFillError."""
        client = _make_llm_client("Sure! Here is a strategy for you: ...")
        request = AISeedFillRequest(prompt="Give me a strategy")

        with pytest.raises(AISeedFillError, match="LLM returned non-JSON"):
            seed_fill_strategy(
                request, client, validate_expression_fn=_noop_validate_expression
            )

    def test_json_array_raises(self):
        """LLM returning a JSON array (not object) raises AISeedFillError."""
        client = _make_llm_client("[1, 2, 3]")
        request = AISeedFillRequest(prompt="Give me a strategy")

        with pytest.raises(AISeedFillError, match="non-object JSON"):
            seed_fill_strategy(
                request, client, validate_expression_fn=_noop_validate_expression
            )


# ---------------------------------------------------------------------------
# Schema validation failure
# ---------------------------------------------------------------------------

class TestSeedFillSchemaFailure:
    def test_missing_required_field_raises(self):
        """LLM output missing 'entries' raises AISeedFillError (schema mismatch)."""
        bad_draft = {"name": "Incomplete Strategy", "stops": []}
        client = _make_llm_client(json.dumps(bad_draft))
        request = AISeedFillRequest(prompt="Give me a strategy")

        with pytest.raises(AISeedFillError, match="did not match draft schema"):
            seed_fill_strategy(
                request, client, validate_expression_fn=_noop_validate_expression
            )

    def test_empty_stops_raises(self):
        """LLM output with empty stops list raises (validator requires at least 1)."""
        draft = json.loads(_ibs_draft_json())
        draft["stops"] = []
        client = _make_llm_client(json.dumps(draft))
        request = AISeedFillRequest(prompt="IBS strategy without stops")

        with pytest.raises(AISeedFillError, match="did not match draft schema"):
            seed_fill_strategy(
                request, client, validate_expression_fn=_noop_validate_expression
            )


# ---------------------------------------------------------------------------
# Expression validation failure (returns, not raises)
# ---------------------------------------------------------------------------

class TestSeedFillExpressionValidationFailure:
    def test_malformed_expression_returns_invalid_status(self):
        """Malformed expression returns response with validation_status.valid=False."""
        def bad_validate(expr_text, variable_names=()):
            result = MagicMock()
            result.valid = False
            result.errors = [MagicMock(message="unexpected token '='")]
            result.warnings = []
            return result

        client = _make_llm_client(_ibs_draft_json())
        request = AISeedFillRequest(prompt="IBS strategy")

        response = seed_fill_strategy(
            request, client, validate_expression_fn=bad_validate
        )

        assert response.validation_status.valid is False
        assert len(response.validation_status.errors) > 0
        # draft is still returned even with errors
        assert response.draft is not None

    def test_malformed_expression_does_not_raise(self):
        """AISeedFillError is NOT raised for expression validation failures."""
        def bad_validate(expr_text, variable_names=()):
            result = MagicMock()
            result.valid = False
            result.errors = [MagicMock(message="bad syntax")]
            result.warnings = []
            return result

        client = _make_llm_client(_ibs_draft_json())
        request = AISeedFillRequest(prompt="IBS strategy")

        # Must not raise
        response = seed_fill_strategy(
            request, client, validate_expression_fn=bad_validate
        )
        assert response is not None


# ---------------------------------------------------------------------------
# System prompt contains catalog features
# ---------------------------------------------------------------------------

class TestSystemPromptCatalogEmbedding:
    def test_system_prompt_embeds_catalog_feature_names(self):
        """System prompt contains at least one feature name from the catalog."""
        from backend.app.strategies.expression_engine import default_catalog

        catalog = default_catalog()
        feature_names = [spec.name for spec in catalog.all()]

        client = _make_llm_client(_ibs_draft_json())
        request = AISeedFillRequest(prompt="IBS strategy")

        seed_fill_strategy(request, client, validate_expression_fn=_noop_validate_expression)

        system_prompt_sent = client.invoke.call_args[0][0].system_prompt
        # At least 5 known features must appear
        found = [name for name in feature_names if name in system_prompt_sent]
        assert len(found) >= 5, f"Expected at least 5 catalog features in prompt, found: {found}"

    def test_system_prompt_reads_catalog_at_call_time(self):
        """Mock the catalog's all() to return a sentinel feature; verify it appears in the prompt."""
        from backend.app.strategies.expression_engine.features import FeatureSpec

        sentinel_feature = FeatureSpec(
            name="sentinel_test_feature_xyz",
            namespace="",
            is_timeframed=True,
            arity=0,
            arg_names=(),
            arg_defaults=(),
            return_type="float",
            description="sentinel for test",
        )

        fake_catalog = MagicMock()
        fake_catalog.all.return_value = [sentinel_feature]

        client = _make_llm_client(_ibs_draft_json())
        request = AISeedFillRequest(prompt="IBS strategy")

        with patch(
            "backend.app.strategies_v4.ai_seedfill._build_system_prompt",
            wraps=lambda: _patched_build_system_prompt(fake_catalog),
        ):
            pass

        # More direct: call the internal _build_system_prompt with the patched catalog
        with patch(
            "backend.app.strategies.expression_engine.default_catalog",
            return_value=fake_catalog,
        ):
            seed_fill_strategy(
                request, client, validate_expression_fn=_noop_validate_expression
            )
            system_prompt = client.invoke.call_args[0][0].system_prompt
            assert "sentinel_test_feature_xyz" in system_prompt


def _patched_build_system_prompt(fake_catalog) -> str:
    """Helper — not tested directly."""
    return ""

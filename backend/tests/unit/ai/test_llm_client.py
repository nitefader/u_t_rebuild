"""Unit tests for backend.app.ai.llm_client."""
from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.app.ai.llm_client import (
    GROQ_DEFAULT_MODEL,
    ANTHROPIC_DEFAULT_MODEL,
    OPENAI_DEFAULT_MODEL,
    AnthropicLLMClient,
    GroqLLMClient,
    LLMClientError,
    LLMRequest,
    LLMResponse,
    OpenAILLMClient,
    resolve_api_key_from_env,
    resolve_default_llm_client,
)
from backend.app.ai.providers import AIProvider, AIProviderStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(json_mode: bool = True) -> LLMRequest:
    return LLMRequest(
        system_prompt="You are a strategy generator.",
        user_prompt="Give me an FVG long strategy on 5m.",
        response_format_json=json_mode,
        max_tokens=512,
        temperature=0.3,
    )


def _openai_success_body(content: str = '{"name":"Test"}', model: str = "gpt-4o-mini") -> bytes:
    payload = {
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "model": model,
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    }
    return json.dumps(payload).encode()


def _anthropic_success_body(content: str = '{"name":"Test"}', model: str = "claude-3-5-sonnet") -> bytes:
    payload = {
        "content": [{"type": "text", "text": content}],
        "model": model,
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 100, "output_tokens": 50},
    }
    return json.dumps(payload).encode()


class _FakeHTTPResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeHTTPError(Exception):
    """Simulates urllib.error.HTTPError."""
    def __init__(self, code: int, body: str = "") -> None:
        super().__init__(str(code))
        self.code = code
        self.fp = MagicMock()
        self.fp.read = lambda: body.encode()


# ---------------------------------------------------------------------------
# Groq client tests
# ---------------------------------------------------------------------------

class TestGroqLLMClient:
    def test_builds_correct_request_body(self):
        """Groq client sends the correct JSON shape to the endpoint."""
        client = GroqLLMClient(api_key="gsk_testkey", model=GROQ_DEFAULT_MODEL)
        captured_bodies: list[dict] = []

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode())
            captured_bodies.append(body)
            return _FakeHTTPResponse(_openai_success_body())

        with patch("urllib.request.urlopen", fake_urlopen):
            resp = client.invoke(_make_request())

        assert resp.provider == AIProvider.GROQ
        assert resp.model == "gpt-4o-mini"  # returned by fake body
        assert resp.finish_reason == "stop"
        assert resp.usage_tokens_in == 100
        assert resp.usage_tokens_out == 50

        body = captured_bodies[0]
        assert body["model"] == GROQ_DEFAULT_MODEL
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][1]["role"] == "user"
        assert body["response_format"] == {"type": "json_object"}

    def test_no_response_format_when_json_false(self):
        """response_format key is absent when response_format_json=False."""
        client = GroqLLMClient(api_key="gsk_testkey")
        captured_bodies: list[dict] = []

        def fake_urlopen(req, timeout):
            body = json.loads(req.data.decode())
            captured_bodies.append(body)
            return _FakeHTTPResponse(_openai_success_body())

        with patch("urllib.request.urlopen", fake_urlopen):
            client.invoke(_make_request(json_mode=False))

        assert "response_format" not in captured_bodies[0]

    def test_429_retries_once(self):
        """On 429, the client retries once after backoff."""
        import urllib.error

        client = GroqLLMClient(api_key="gsk_testkey")
        call_count = 0

        def fake_urlopen(req, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                err = urllib.error.HTTPError(
                    url="", code=429, msg="Too Many Requests", hdrs=MagicMock(), fp=MagicMock()
                )
                err.fp.read = lambda: b"rate limited"
                raise err
            return _FakeHTTPResponse(_openai_success_body())

        with patch("urllib.request.urlopen", fake_urlopen):
            with patch("time.sleep"):  # don't actually sleep
                resp = client.invoke(_make_request())

        assert call_count == 2
        assert resp.provider == AIProvider.GROQ

    def test_4xx_not_429_raises_error(self):
        """4xx other than 429 should raise LLMClientError after retry attempt."""
        import urllib.error

        client = GroqLLMClient(api_key="gsk_bad")

        def fake_urlopen(req, timeout):
            err = urllib.error.HTTPError(
                url="", code=401, msg="Unauthorized", hdrs=MagicMock(), fp=MagicMock()
            )
            err.fp.read = lambda: b"invalid api key"
            raise err

        with patch("urllib.request.urlopen", fake_urlopen):
            with pytest.raises(LLMClientError, match="HTTP 401"):
                client.invoke(_make_request())

    def test_connection_failure_raises_error(self):
        """Network-level error surfaces as LLMClientError."""
        client = GroqLLMClient(api_key="gsk_testkey")

        def fake_urlopen(req, timeout):
            raise OSError("connection refused")

        with patch("urllib.request.urlopen", fake_urlopen):
            with pytest.raises(LLMClientError, match="connection error"):
                client.invoke(_make_request())

    def test_timeout_surfaces_as_llm_client_error(self):
        """Timeout (socket timeout) surfaces as LLMClientError."""
        import socket

        client = GroqLLMClient(api_key="gsk_testkey")

        def fake_urlopen(req, timeout):
            raise socket.timeout("timed out")

        with patch("urllib.request.urlopen", fake_urlopen):
            with pytest.raises(LLMClientError):
                client.invoke(_make_request())


# ---------------------------------------------------------------------------
# Anthropic client tests
# ---------------------------------------------------------------------------

class TestAnthropicLLMClient:
    def test_builds_correct_request_body(self):
        """Anthropic client uses messages format and x-api-key header."""
        client = AnthropicLLMClient(api_key="sk-ant-testkey", model=ANTHROPIC_DEFAULT_MODEL)
        captured: list[dict] = []
        captured_headers: list[dict] = []

        def fake_urlopen(req, timeout):
            captured.append(json.loads(req.data.decode()))
            captured_headers.append(dict(req.headers))
            return _FakeHTTPResponse(_anthropic_success_body())

        with patch("urllib.request.urlopen", fake_urlopen):
            resp = client.invoke(_make_request())

        assert resp.provider == AIProvider.CLAUDE
        assert resp.finish_reason == "end_turn"

        body = captured[0]
        assert "system" in body
        assert "IMPORTANT: respond with valid JSON only" in body["system"]
        assert body["messages"][0]["role"] == "user"
        assert body["model"] == ANTHROPIC_DEFAULT_MODEL
        # anthropic-version header should be present
        assert any("anthropic-version" in k.lower() for k in captured_headers[0])

    def test_429_retries(self):
        """Anthropic 429 retries once."""
        import urllib.error

        client = AnthropicLLMClient(api_key="sk-ant-testkey")
        call_count = 0

        def fake_urlopen(req, timeout):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                err = urllib.error.HTTPError(
                    url="", code=429, msg="TooMany", hdrs=MagicMock(), fp=MagicMock()
                )
                err.fp.read = lambda: b"rate limited"
                raise err
            return _FakeHTTPResponse(_anthropic_success_body())

        with patch("urllib.request.urlopen", fake_urlopen):
            with patch("time.sleep"):
                resp = client.invoke(_make_request())

        assert call_count == 2
        assert resp.provider == AIProvider.CLAUDE


# ---------------------------------------------------------------------------
# OpenAI client tests
# ---------------------------------------------------------------------------

class TestOpenAILLMClient:
    def test_builds_correct_request_body(self):
        """OpenAI client sends the right format."""
        client = OpenAILLMClient(api_key="sk-openai-testkey", model=OPENAI_DEFAULT_MODEL)
        captured: list[dict] = []

        def fake_urlopen(req, timeout):
            captured.append(json.loads(req.data.decode()))
            return _FakeHTTPResponse(_openai_success_body(model=OPENAI_DEFAULT_MODEL))

        with patch("urllib.request.urlopen", fake_urlopen):
            resp = client.invoke(_make_request())

        assert resp.provider == AIProvider.OPENAI
        assert captured[0]["model"] == OPENAI_DEFAULT_MODEL
        assert captured[0]["response_format"] == {"type": "json_object"}

    def test_4xx_raises(self):
        """OpenAI 4xx raises LLMClientError."""
        import urllib.error

        client = OpenAILLMClient(api_key="sk-bad")

        def fake_urlopen(req, timeout):
            err = urllib.error.HTTPError(
                url="", code=403, msg="Forbidden", hdrs=MagicMock(), fp=MagicMock()
            )
            err.fp.read = lambda: b"forbidden"
            raise err

        with patch("urllib.request.urlopen", fake_urlopen):
            with pytest.raises(LLMClientError, match="HTTP 403"):
                client.invoke(_make_request())


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------

class TestResolveDefaultLlmClient:
    def _make_catalog(self, provider: AIProvider, is_default: bool = True, status: str = "valid"):
        from backend.app.ai.catalog import AIProviderCatalog
        from backend.app.ai.providers import AIServiceRecord, AIProviderStatus

        record = AIServiceRecord(
            name="Test Provider",
            provider=provider,
            is_default=is_default,
            status=AIProviderStatus(status),
            has_api_key=True,
            credentials_ref="ai-provider-credential:abc123def456",
        )

        catalog = MagicMock(spec=AIProviderCatalog)
        from backend.app.ai.providers import AIServiceList
        catalog.list_services.return_value = AIServiceList(services=(record,))
        return catalog

    def test_selects_default_valid_provider_groq(self):
        """Factory returns a GroqLLMClient for a default GROQ provider."""
        catalog = self._make_catalog(AIProvider.GROQ)
        with patch.dict("os.environ", {"GROQ_API_KEY": "gsk_validkey"}):
            client = resolve_default_llm_client(catalog)
        assert isinstance(client, GroqLLMClient)

    def test_selects_default_valid_provider_claude(self):
        """Factory returns AnthropicLLMClient for default CLAUDE provider."""
        catalog = self._make_catalog(AIProvider.CLAUDE)
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-valid"}):
            client = resolve_default_llm_client(catalog)
        assert isinstance(client, AnthropicLLMClient)

    def test_selects_default_valid_provider_openai(self):
        """Factory returns OpenAILLMClient for default OPENAI provider."""
        catalog = self._make_catalog(AIProvider.OPENAI)
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-valid"}):
            client = resolve_default_llm_client(catalog)
        assert isinstance(client, OpenAILLMClient)

    def test_raises_when_no_default(self):
        """Factory raises if no default provider is marked valid+default."""
        catalog = self._make_catalog(AIProvider.GROQ, is_default=False)
        with pytest.raises(LLMClientError, match="no default AI provider configured"):
            resolve_default_llm_client(catalog)

    def test_raises_when_status_not_valid(self):
        """Factory raises if default provider has status != VALID."""
        catalog = self._make_catalog(AIProvider.GROQ, is_default=True, status="draft")
        with pytest.raises(LLMClientError, match="no default AI provider configured"):
            resolve_default_llm_client(catalog)

    def test_raises_when_env_key_missing(self):
        """Factory raises if the API key env var is unset."""
        catalog = self._make_catalog(AIProvider.GROQ)
        env_without_key = {k: v for k, v in __import__("os").environ.items() if k != "GROQ_API_KEY"}
        with patch.dict("os.environ", env_without_key, clear=True):
            with pytest.raises(LLMClientError, match="no credentials"):
                resolve_default_llm_client(catalog)

"""LLM client abstraction — real HTTP, provider-specific implementations.

Each concrete client posts to the provider's chat-completion endpoint using
stdlib ``urllib.request``.  No new dependencies are introduced; ``httpx`` is
not in requirements.txt so urllib is the fallback.

Per the AI provider contract the catalog is the source of truth for WHICH
provider is default and whether a key exists.  The actual raw API key is
resolved from environment variables keyed by provider — the catalog stores
only a hash for deduplication, never the plaintext.

Env var convention (read at factory call time, never hardcoded):
  GROQ_API_KEY       — Groq
  ANTHROPIC_API_KEY  — Anthropic / Claude
  OPENAI_API_KEY     — OpenAI
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from backend.app.ai.providers import AIProvider


# ---------------------------------------------------------------------------
# Default model identifiers per provider
# These are content-not-config; provider enum values come from AIProvider.
# ---------------------------------------------------------------------------

GROQ_DEFAULT_MODEL = "llama-3.1-70b-versatile"
ANTHROPIC_DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"

# Env var names per provider — never hardcoded elsewhere.
_ENV_KEY_MAP: dict[AIProvider, str] = {
    AIProvider.GROQ: "GROQ_API_KEY",
    AIProvider.CLAUDE: "ANTHROPIC_API_KEY",
    AIProvider.OPENAI: "OPENAI_API_KEY",
    AIProvider.CODEX: "OPENAI_API_KEY",  # Codex re-uses OpenAI key
    AIProvider.FUTURE: "FUTURE_AI_API_KEY",
}

_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_TIMEOUT_SECONDS = 30
_RETRY_BACKOFF_SECONDS = 1


# ---------------------------------------------------------------------------
# Request / Response DTOs
# ---------------------------------------------------------------------------

class LLMRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    system_prompt: str
    user_prompt: str
    response_format_json: bool = True
    max_tokens: int = 4096
    temperature: float = 0.3


class LLMResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str
    provider: AIProvider
    model: str
    finish_reason: str
    usage_tokens_in: int | None = None
    usage_tokens_out: int | None = None


class LLMClientError(RuntimeError):
    """Raised for HTTP failures, connection errors, auth errors, or missing config."""


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class LLMClient(Protocol):
    def invoke(self, request: LLMRequest) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# Internal HTTP helper
# ---------------------------------------------------------------------------

def _http_post(url: str, headers: dict[str, str], body: dict) -> tuple[int, str]:
    """POST *body* to *url*.  Returns (status_code, response_text).

    Raises ``LLMClientError`` on connection-level failure (DNS, timeout, etc.).
    Never raises on HTTP error codes — those are returned as (status, body).
    """
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            **headers,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return exc.code, body_text
    except Exception as exc:
        raise LLMClientError(f"connection error calling {url}: {exc}") from exc


def _post_with_retry(url: str, headers: dict[str, str], body: dict) -> tuple[int, str]:
    """Call _http_post once; if 429/5xx, retry once after a short backoff."""
    status, text = _http_post(url, headers, body)
    if status in _RETRY_STATUS_CODES:
        time.sleep(_RETRY_BACKOFF_SECONDS)
        status, text = _http_post(url, headers, body)
    return status, text


# ---------------------------------------------------------------------------
# Groq client (OpenAI-compatible endpoint)
# ---------------------------------------------------------------------------

class GroqLLMClient:
    """Client for Groq's OpenAI-compatible chat-completion endpoint."""

    _BASE_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model: str = GROQ_DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    def invoke(self, request: LLMRequest) -> LLMResponse:
        body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.response_format_json:
            body["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self._api_key}"}
        status, text = _post_with_retry(self._BASE_URL, headers, body)

        if status not in {200, 201}:
            raise LLMClientError(
                f"Groq returned HTTP {status}: {text[:500]}"
            )

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMClientError(f"Groq response is not valid JSON: {text[:200]}") from exc

        choices = payload.get("choices") or []
        if not choices:
            raise LLMClientError(f"Groq returned no choices: {text[:200]}")

        choice = choices[0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason", "")
        usage = payload.get("usage", {})

        return LLMResponse(
            text=content,
            provider=AIProvider.GROQ,
            model=payload.get("model", self._model),
            finish_reason=finish_reason,
            usage_tokens_in=usage.get("prompt_tokens"),
            usage_tokens_out=usage.get("completion_tokens"),
        )


# ---------------------------------------------------------------------------
# Anthropic client (claude messages API)
# ---------------------------------------------------------------------------

class AnthropicLLMClient:
    """Client for Anthropic's messages endpoint."""

    _BASE_URL = "https://api.anthropic.com/v1/messages"
    _API_VERSION = "2023-06-01"

    def __init__(self, api_key: str, model: str = ANTHROPIC_DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    def invoke(self, request: LLMRequest) -> LLMResponse:
        system_prompt = request.system_prompt
        if request.response_format_json:
            system_prompt = (
                "IMPORTANT: respond with valid JSON only, no prose.\n\n" + system_prompt
            )

        body: dict = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "system": system_prompt,
            "messages": [
                {"role": "user", "content": request.user_prompt},
            ],
            "temperature": request.temperature,
        }

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._API_VERSION,
        }
        status, text = _post_with_retry(self._BASE_URL, headers, body)

        if status not in {200, 201}:
            raise LLMClientError(
                f"Anthropic returned HTTP {status}: {text[:500]}"
            )

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMClientError(
                f"Anthropic response is not valid JSON: {text[:200]}"
            ) from exc

        content_blocks = payload.get("content") or []
        content = "".join(
            block.get("text", "") for block in content_blocks if block.get("type") == "text"
        )
        finish_reason = payload.get("stop_reason", "")
        usage = payload.get("usage", {})

        return LLMResponse(
            text=content,
            provider=AIProvider.CLAUDE,
            model=payload.get("model", self._model),
            finish_reason=finish_reason,
            usage_tokens_in=usage.get("input_tokens"),
            usage_tokens_out=usage.get("output_tokens"),
        )


# ---------------------------------------------------------------------------
# OpenAI client
# ---------------------------------------------------------------------------

class OpenAILLMClient:
    """Client for OpenAI's chat-completion endpoint."""

    _BASE_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model: str = OPENAI_DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    def invoke(self, request: LLMRequest) -> LLMResponse:
        body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.response_format_json:
            body["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self._api_key}"}
        status, text = _post_with_retry(self._BASE_URL, headers, body)

        if status not in {200, 201}:
            raise LLMClientError(
                f"OpenAI returned HTTP {status}: {text[:500]}"
            )

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMClientError(
                f"OpenAI response is not valid JSON: {text[:200]}"
            ) from exc

        choices = payload.get("choices") or []
        if not choices:
            raise LLMClientError(f"OpenAI returned no choices: {text[:200]}")

        choice = choices[0]
        content = choice.get("message", {}).get("content", "")
        finish_reason = choice.get("finish_reason", "")
        usage = payload.get("usage", {})

        return LLMResponse(
            text=content,
            provider=AIProvider.OPENAI,
            model=payload.get("model", self._model),
            finish_reason=finish_reason,
            usage_tokens_in=usage.get("prompt_tokens"),
            usage_tokens_out=usage.get("completion_tokens"),
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def resolve_api_key_from_env(provider: AIProvider) -> str | None:
    """Read the raw API key for *provider* from the process environment.

    Returns None if the env var is unset or empty.
    """
    env_var = _ENV_KEY_MAP.get(provider)
    if not env_var:
        return None
    return os.environ.get(env_var, "").strip() or None


def resolve_default_llm_client(catalog: "AIProviderCatalog") -> LLMClient:  # type: ignore[name-defined]  # noqa: F821
    """Construct the LLM client for the catalog's default valid provider.

    Raises LLMClientError if:
    - no provider is marked is_default=True with status=VALID
    - the env var for the resolved provider is empty
    """
    from backend.app.ai.catalog import AIProviderCatalog
    from backend.app.ai.providers import AIProviderStatus

    services = catalog.list_services().services
    default_record = next(
        (
            s
            for s in services
            if s.is_default and s.status == AIProviderStatus.VALID
        ),
        None,
    )
    if default_record is None:
        raise LLMClientError("no default AI provider configured")

    api_key = resolve_api_key_from_env(default_record.provider)
    if not api_key:
        raise LLMClientError(
            f"default provider has no credentials: env var "
            f"'{_ENV_KEY_MAP.get(default_record.provider, '?')}' is unset or empty"
        )

    provider = default_record.provider
    if provider == AIProvider.GROQ:
        return GroqLLMClient(api_key=api_key)
    if provider == AIProvider.CLAUDE:
        return AnthropicLLMClient(api_key=api_key)
    if provider in {AIProvider.OPENAI, AIProvider.CODEX}:
        return OpenAILLMClient(api_key=api_key)

    raise LLMClientError(
        f"provider '{provider}' is configured as default but has no concrete LLM client implementation"
    )

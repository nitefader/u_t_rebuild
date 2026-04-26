"""System status — single source of truth for the operator UI nav badge.

The status endpoint reports what the running backend can actually do:
whether Alpaca credentials are present, whether the test stream is on,
which broker provider is wired. The frontend nav reads this once on
load and shows a small badge so the operator knows at a glance whether
streaming will work without having to open every page.
"""

from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from backend.app.api.system_settings_store import setting


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alpaca_credentials_present: bool
    alpaca_test_stream: bool
    alpaca_endpoint: str
    alpaca_data_feed: str
    operator_environment: str
    operator_environment_source: str
    operator_environment_conflict: str | None = None


_PAPER_ENDPOINT_HINT = "paper-api"
_KNOWN_ENVIRONMENTS = {"paper", "live"}


def _resolve_operator_environment(endpoint: str) -> tuple[str, str, str | None]:
    """Return (environment, source, conflict_message).

    UTOS_ENVIRONMENT is the source of truth. When unset, paper-vs-live is
    inferred from the URL substring (legacy fallback). When both are set
    and disagree, the explicit env wins but a conflict_message surfaces
    so the operator notices the misconfiguration instead of silently
    operating against the wrong account.
    """
    raw = os.getenv("UTOS_ENVIRONMENT")
    inferred = "paper" if _PAPER_ENDPOINT_HINT in endpoint else "live"
    if raw is None or raw == "":
        return inferred, "inferred_from_endpoint", None
    normalized = raw.strip().lower()
    if normalized in {"prod", "production"}:
        normalized = "live"
    if normalized not in _KNOWN_ENVIRONMENTS:
        return (
            normalized,
            "explicit",
            f"UTOS_ENVIRONMENT={raw!r} is not one of {sorted(_KNOWN_ENVIRONMENTS)}; using as-is",
        )
    if normalized != inferred:
        return (
            normalized,
            "explicit",
            f"UTOS_ENVIRONMENT={normalized!r} disagrees with ALPACA_BASE_URL "
            f"(URL implies {inferred!r}); using UTOS_ENVIRONMENT but please reconcile",
        )
    return normalized, "explicit", None


def system_status() -> SystemStatusResponse:
    has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))
    test_stream_raw = setting("alpaca_use_test_stream", fallback_env="ALPACA_USE_TEST_STREAM", default="0")
    test_stream = str(test_stream_raw) in ("1", "true", "True", True)
    endpoint = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    operator_environment, source, conflict = _resolve_operator_environment(endpoint)
    if test_stream:
        data_feed = "test"
    else:
        data_feed = str(setting("alpaca_data_feed", fallback_env="ALPACA_DATA_FEED", default="iex")).lower()
    return SystemStatusResponse(
        alpaca_credentials_present=has_creds,
        alpaca_test_stream=test_stream,
        alpaca_endpoint=endpoint,
        alpaca_data_feed=data_feed,
        operator_environment=operator_environment,
        operator_environment_source=source,
        operator_environment_conflict=conflict,
    )


router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status() -> SystemStatusResponse:
    return system_status()

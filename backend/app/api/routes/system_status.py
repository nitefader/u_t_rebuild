"""System status — single source of truth for the operator UI nav badge.

The status endpoint reports what the running backend can actually do:
whether Alpaca credentials are present, whether the test stream is on,
which broker provider is wired. The frontend nav reads this once on
load and shows a small badge so the operator knows at a glance whether
streaming will work without having to open every page.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict


try:  # pragma: no cover - exercised when FastAPI is installed.
    from fastapi import APIRouter
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]


class SystemStatusResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    alpaca_credentials_present: bool
    alpaca_test_stream: bool
    alpaca_endpoint: str
    alpaca_data_feed: str
    operator_environment: str


def system_status() -> SystemStatusResponse:
    has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY"))
    test_stream = os.getenv("ALPACA_USE_TEST_STREAM") == "1"
    endpoint = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
    is_paper = "paper-api" in endpoint
    operator_environment = os.getenv("UTOS_ENVIRONMENT") or ("paper" if is_paper else "live")
    if test_stream:
        data_feed = "test"
    else:
        data_feed = (os.getenv("ALPACA_DATA_FEED") or "iex").lower()
    return SystemStatusResponse(
        alpaca_credentials_present=has_creds,
        alpaca_test_stream=test_stream,
        alpaca_endpoint=endpoint,
        alpaca_data_feed=data_feed,
        operator_environment=operator_environment,
    )


if APIRouter is None:
    from backend.app.api.routes.operations import FallbackRouter

    router = FallbackRouter(prefix="/api/v1/system", tags=["system"])
else:
    router = APIRouter(prefix="/api/v1/system", tags=["system"])


@router.get("/status", response_model=SystemStatusResponse)
def get_system_status() -> SystemStatusResponse:
    return system_status()

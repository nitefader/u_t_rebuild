from __future__ import annotations

import os
from dataclasses import dataclass

from backend.app.api.system_settings_store import setting

from .alpaca import AlpacaMarketDataAdapter
from .models import ServicePurpose
from .resolver import Provider


@dataclass(frozen=True)
class ChartLabConfig:
    """Live market-data feed config retained for runtime hub selection."""

    streaming_enabled: bool
    test_stream: bool
    default_symbol: str
    data_feed: str
    routing_note: str = ""

    @classmethod
    def from_env(cls) -> "ChartLabConfig":
        test_service = _alpaca_service_for_purpose(ServicePurpose.TEST_STREAMING)
        live_service = _alpaca_service_for_purpose(ServicePurpose.LIVE_STREAMING)
        use_tags = test_service is not None or live_service is not None

        operator_override = _chart_lab_one_symbol_stream_override()
        if operator_override is not None:
            test_stream = operator_override
        elif use_tags:
            test_stream = test_service is not None
        else:
            test_stream_raw = setting("alpaca_use_test_stream", fallback_env="ALPACA_USE_TEST_STREAM", default="0")
            test_stream = str(test_stream_raw) in ("1", "true", "True", True)

        selected_service = test_service if test_stream else live_service
        has_configured_service_creds = bool(
            selected_service is not None
            and getattr(selected_service, "has_api_key", False)
            and getattr(selected_service, "has_api_secret", False)
        )
        has_creds = bool(os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_SECRET_KEY")) or has_configured_service_creds
        configured_symbol = setting("chart_lab_default_symbol", fallback_env="CHART_LAB_DEFAULT_SYMBOL", default="SPY")
        default_symbol = AlpacaMarketDataAdapter.TEST_SYMBOL if test_stream else str(configured_symbol)
        data_feed = "test" if test_stream else str(
            setting("alpaca_data_feed", fallback_env="ALPACA_DATA_FEED", default="iex")
        ).lower()

        return cls(
            streaming_enabled=has_creds,
            test_stream=test_stream,
            default_symbol=default_symbol,
            data_feed=data_feed,
            routing_note=_routing_note(operator_override=operator_override, use_tags=use_tags, test_stream=test_stream),
        )


def _chart_lab_one_symbol_stream_override() -> bool | None:
    try:
        from backend.app.api.system_settings_store import get_store

        raw = get_store().load()
        if "chart_lab_one_symbol_fakepaca" not in raw:
            return None
        return bool(raw["chart_lab_one_symbol_fakepaca"])
    except Exception:  # noqa: BLE001 - market-data config must degrade if settings fail.
        return None


def _alpaca_service_for_purpose(purpose: ServicePurpose):
    try:
        from backend.app.market_data.runtime import create_market_data_catalog_from_environment

        catalog = create_market_data_catalog_from_environment()
        return catalog.find_default_for(purpose, provider=Provider.ALPACA)
    except Exception:  # noqa: BLE001 - catalog errors fall back to env settings.
        return None


def _routing_note(*, operator_override: bool | None, use_tags: bool, test_stream: bool) -> str:
    if operator_override is True:
        return (
            "FAKEPACA is forced on for the one-symbol bar stream by the Market Data page toggle "
            "(system setting chart_lab_one_symbol_fakepaca). Broker Trade Update Streams on Operations are unchanged."
        )
    if operator_override is False:
        return (
            "The one-symbol bar stream uses real symbols and your configured data feed "
            "(Market Data toggle = Live). Broker Trade Update Streams on Operations are unchanged."
        )
    if use_tags and test_stream:
        return (
            "FAKEPACA is on because an Alpaca Market Data provider on the Providers page is tagged for "
            "Test streaming. Clear Test streaming or tag Live streaming on the Alpaca provider to chart real symbols."
        )
    if use_tags:
        return (
            "The one-symbol bar stream follows your Alpaca provider tagged for Live streaming. "
            "This WebSocket is market data, not broker order or fill updates on Operations."
        )
    if test_stream:
        return (
            "FAKEPACA is on from Settings (Test stream) or ALPACA_USE_TEST_STREAM in .env. "
            "Turn off the toggle in Settings or set the env var to 0 and restart the API."
        )
    return (
        "The one-symbol bar stream uses the symbol you enter and your data feed from Settings "
        "(or ALPACA_DATA_FEED). Broker Trade Update Streams on Operations are a different connection."
    )

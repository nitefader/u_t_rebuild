from __future__ import annotations

from dataclasses import dataclass

from .resolver import CostClass, LatencyClass, MarketDataCapabilities, Provider


@dataclass(frozen=True)
class ProviderCapabilityProfile:
    capabilities: MarketDataCapabilities
    source: str
    notes: tuple[str, ...] = ()


def provider_capability_profile(provider: Provider) -> ProviderCapabilityProfile:
    if provider == Provider.ALPACA:
        return ProviderCapabilityProfile(
            capabilities=MarketDataCapabilities(
                supports_historical=True,
                supports_streaming=True,
                supports_intraday=True,
                supports_daily=True,
                supports_weekly=False,
                supports_monthly=False,
                supports_realtime=True,
                supports_long_range_history=True,
                requires_credentials=True,
                cost_class=CostClass.STANDARD,
                latency_class=LatencyClass.LOW,
            ),
            source="docs:alpaca-market-data",
            notes=(
                "Alpaca documents historical market data APIs and websocket streams for real-time stock data.",
                "Credential and subscription entitlement can affect realtime market-data availability.",
            ),
        )
    if provider == Provider.YAHOO:
        return ProviderCapabilityProfile(
            capabilities=MarketDataCapabilities(
                supports_historical=True,
                supports_streaming=False,
                supports_intraday=False,
                supports_daily=True,
                supports_weekly=True,
                supports_monthly=True,
                supports_realtime=False,
                supports_long_range_history=True,
                requires_credentials=False,
                cost_class=CostClass.FREE,
                latency_class=LatencyClass.DELAYED,
            ),
            source="provider-profile:yahoo-historical",
            notes=(
                "Yahoo is modeled as historical-only in this system until validation proves otherwise.",
                "Intraday support remains disabled by default because coverage limits vary by interval and lookback range.",
            ),
        )
    return ProviderCapabilityProfile(
        capabilities=MarketDataCapabilities(),
        source="provider-profile:unknown",
        notes=("No provider capability profile is available yet.",),
    )

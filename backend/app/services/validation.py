from __future__ import annotations

from dataclasses import dataclass

from .models import AIProvider, ServiceValidationStatus
from .service_resolver import (
    CostClass,
    LatencyClass,
    MarketDataCapabilities,
    Provider,
    ServiceMode,
)


@dataclass(frozen=True)
class MarketDataValidationResult:
    status: ServiceValidationStatus
    message: str
    capabilities: MarketDataCapabilities


@dataclass(frozen=True)
class AIValidationResult:
    status: ServiceValidationStatus
    message: str


class MarketDataProviderValidator:
    def validate(
        self,
        *,
        provider: Provider,
        mode: ServiceMode,
        has_api_key: bool,
        has_api_secret: bool,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> MarketDataValidationResult:
        if provider == Provider.YAHOO:
            return MarketDataValidationResult(ServiceValidationStatus.VALID, "Yahoo historical provider validated.", yahoo_capabilities())
        if provider != Provider.ALPACA:
            return MarketDataValidationResult(ServiceValidationStatus.UNSUPPORTED_PROVIDER, "Unsupported market data provider.", MarketDataCapabilities())
        if mode not in {ServiceMode.PAPER, ServiceMode.LIVE}:
            return MarketDataValidationResult(ServiceValidationStatus.MODE_MISMATCH, "Alpaca market data requires paper or live mode.", alpaca_capabilities())
        if not has_api_key or not has_api_secret:
            return MarketDataValidationResult(ServiceValidationStatus.MISSING_CREDENTIALS, "Alpaca API key and secret are required.", alpaca_capabilities())
        if api_key is not None and len(api_key.strip()) < 6:
            return MarketDataValidationResult(ServiceValidationStatus.INVALID, "Alpaca API key shape is invalid.", alpaca_capabilities())
        if api_secret is not None and len(api_secret.strip()) < 8:
            return MarketDataValidationResult(ServiceValidationStatus.INVALID, "Alpaca API secret shape is invalid.", alpaca_capabilities())
        return MarketDataValidationResult(ServiceValidationStatus.VALID, "Alpaca credentials validated by configured validator.", alpaca_capabilities())


class AIProviderValidator:
    def validate(self, *, provider: AIProvider, has_api_key: bool, api_key: str | None = None) -> AIValidationResult:
        if not has_api_key:
            return AIValidationResult(ServiceValidationStatus.MISSING_CREDENTIALS, f"{provider.value} API key is required.")
        if provider == AIProvider.GROQ and api_key is not None and not api_key.startswith("gsk_"):
            return AIValidationResult(ServiceValidationStatus.INVALID, "Groq API key shape is invalid.")
        if provider not in {AIProvider.GROQ, AIProvider.CLAUDE, AIProvider.OPENAI, AIProvider.CODEX, AIProvider.FUTURE}:
            return AIValidationResult(ServiceValidationStatus.UNSUPPORTED_PROVIDER, "Unsupported AI provider.")
        return AIValidationResult(ServiceValidationStatus.VALID, f"{provider.value} credentials validated by configured validator.")


def alpaca_capabilities() -> MarketDataCapabilities:
    return MarketDataCapabilities(
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
    )


def yahoo_capabilities() -> MarketDataCapabilities:
    return MarketDataCapabilities(
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
    )

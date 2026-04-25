from __future__ import annotations

from dataclasses import dataclass

from .capability_profiles import provider_capability_profile
from .models import MarketDataValidationStatus
from .resolver import MarketDataCapabilities, Provider


@dataclass(frozen=True)
class MarketDataValidationResult:
    status: MarketDataValidationStatus
    message: str
    capabilities: MarketDataCapabilities
    capability_source: str = "validation"
    capability_notes: tuple[str, ...] = ()


class MarketDataProviderValidator:
    def validate(
        self,
        *,
        provider: Provider,
        has_api_key: bool,
        has_api_secret: bool,
        api_key: str | None = None,
        api_secret: str | None = None,
    ) -> MarketDataValidationResult:
        profile = provider_capability_profile(provider)
        if provider == Provider.YAHOO:
            return MarketDataValidationResult(
                MarketDataValidationStatus.VALID,
                "Yahoo historical provider validated.",
                profile.capabilities,
                profile.source,
                profile.notes,
            )
        if provider != Provider.ALPACA:
            return MarketDataValidationResult(
                MarketDataValidationStatus.UNSUPPORTED_PROVIDER,
                "Unsupported market data provider.",
                MarketDataCapabilities(),
            )
        if not has_api_key or not has_api_secret:
            return MarketDataValidationResult(
                MarketDataValidationStatus.MISSING_CREDENTIALS,
                "Alpaca API key and secret are required.",
                profile.capabilities,
                profile.source,
                profile.notes,
            )
        if api_key is not None and len(api_key.strip()) < 6:
            return MarketDataValidationResult(
                MarketDataValidationStatus.INVALID,
                "Alpaca API key shape is invalid.",
                profile.capabilities,
                profile.source,
                profile.notes,
            )
        if api_secret is not None and len(api_secret.strip()) < 8:
            return MarketDataValidationResult(
                MarketDataValidationStatus.INVALID,
                "Alpaca API secret shape is invalid.",
                profile.capabilities,
                profile.source,
                profile.notes,
            )
        return MarketDataValidationResult(
            MarketDataValidationStatus.VALID,
            "Alpaca credentials validated by configured validator.",
            profile.capabilities,
            profile.source,
            profile.notes,
        )


def alpaca_capabilities() -> MarketDataCapabilities:
    return provider_capability_profile(Provider.ALPACA).capabilities


def yahoo_capabilities() -> MarketDataCapabilities:
    return provider_capability_profile(Provider.YAHOO).capabilities

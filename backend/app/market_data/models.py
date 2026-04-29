"""Persistence shapes for market-data provider records.

Per plan_review.md A1, market-data records do not carry a system mode. Mode
(``TradingMode``) lives only on broker-side records (``BrokerAccount``); market
data feeds are mode-neutral.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain._base import utc_now

from .capability_profiles import provider_capability_profile
from .resolver import (
    MarketDataCapabilities,
    MarketDataServiceConfig,
    Provider,
    ServiceStatus,
    ServiceType,
)


MASKED_SECRET = "********"


class MarketDataValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING_CREDENTIALS = "missing_credentials"
    PROVIDER_UNREACHABLE = "provider_unreachable"
    UNSUPPORTED_PROVIDER = "unsupported_provider"
    DISABLED = "disabled"


class LiveStockMarketDataStreamState(StrEnum):
    OPEN = "open"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DEGRADED = "degraded"
    DOWN = "down"
    DISABLED = "disabled"


class LiveStockMarketDataStreamStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stream_id: str
    provider_id: UUID | None = None
    enabled_by_settings: bool
    open: bool
    connected: bool
    authenticated: bool
    status: LiveStockMarketDataStreamState
    subscribed_symbols: tuple[str, ...] = ()
    consumer_ids: tuple[str, ...] = ()
    last_message_at: datetime | None = None
    last_bar_at_by_symbol: dict[str, datetime] = Field(default_factory=dict)
    reconnect_count: int = Field(default=0, ge=0)
    last_error: str | None = None
    started_at: datetime | None = None

    @field_validator("subscribed_symbols")
    @classmethod
    def normalize_symbols(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(symbol.upper() for symbol in value)


class ServicePurpose(StrEnum):
    """Operator-driven role tags. Replaces .env bootstrap.

    A Service tagged ``LIVE_STREAMING`` is the canonical credential the
    runtime picks for a real broker stream; ``TEST_STREAMING`` is the
    FAKEPACA / 24-7 synthetic stream credential; ``BATCH_HISTORICAL``
    is the credential used for backtest / batch jobs. At most one
    Service may carry each purpose tag (single-canonical-default per
    purpose); set-default-for is unique-per-purpose like
    ``Pipeline.is_default_for_provider``.
    """

    LIVE_STREAMING = "live_streaming"
    TEST_STREAMING = "test_streaming"
    BATCH_HISTORICAL = "batch_historical"
    SIGNAL_PREVIEW = "signal_preview"
    RUNTIME_TRADING = "runtime_trading"


class MarketDataServiceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    provider: Provider
    service_type: ServiceType = ServiceType.MARKET_DATA
    status: ServiceStatus = ServiceStatus.DRAFT
    is_default: bool = False
    default_for: tuple[ServicePurpose, ...] = ()
    credentials_ref: str | None = None
    has_api_key: bool = False
    has_api_secret: bool = False
    api_key_shape_valid: bool = True
    api_secret_shape_valid: bool = True
    capabilities: MarketDataCapabilities = Field(default_factory=MarketDataCapabilities)
    capability_source: str | None = None
    capability_notes: tuple[str, ...] = ()
    capability_updated_at: datetime | None = None
    capability_manual_override: bool = False
    validation_status: MarketDataValidationStatus | None = None
    validation_message: str | None = None
    last_validated_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    disabled_at: datetime | None = None

    def to_resolver_config(self) -> MarketDataServiceConfig:
        return MarketDataServiceConfig(
            service_id=str(self.id),
            service_name=self.name,
            provider=self.provider,
            service_type=self.service_type,
            status=self.status,
            is_default=self.is_default,
            capabilities=self.capabilities,
            credentials_ref=self.credentials_ref,
            validation_status=self.validation_status.value if self.validation_status is not None else None,
            validation_message=self.validation_message,
        )

    @property
    def provider_limitations(self) -> tuple[str, ...]:
        if self.capability_notes:
            return self.capability_notes
        return provider_capability_profile(self.provider).notes


class DeleteMarketDataServiceRequest(BaseModel):
    """Hard-delete guard — operator must type the current service display name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confirm_service_name: str = Field(min_length=1)


class MarketDataServiceDeletionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    service_id: UUID
    message: str


class MarketDataServiceWrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    provider: Provider
    api_key: str | None = None
    api_secret: str | None = None
    capabilities: MarketDataCapabilities | None = None
    capability_notes: tuple[str, ...] = ()
    default_for: tuple[ServicePurpose, ...] = ()

    @field_validator("api_key", "api_secret")
    @classmethod
    def reject_masked_secret(cls, value: str | None) -> str | None:
        if value is not None and value.strip() == MASKED_SECRET:
            raise ValueError("masked credentials are not accepted as replacement secrets")
        return value


class MarketDataServiceList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[MarketDataServiceRecord, ...]

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain._base import utc_now

from .capability_profiles import provider_capability_profile
from .service_resolver import (
    MarketDataCapabilities,
    MarketDataServiceConfig,
    Provider,
    ServiceMode,
    ServiceStatus,
    ServiceType,
)


MASKED_SECRET = "********"


class AIProvider(StrEnum):
    GROQ = "groq"
    CLAUDE = "claude"
    OPENAI = "openai"
    CODEX = "codex"
    FUTURE = "future"


class AIServiceType(StrEnum):
    AI = "ai"


class AICapabilityLabel(StrEnum):
    FAST = "fast"
    REASONING = "reasoning"
    CODING = "coding"
    GENERAL = "general"
    UNKNOWN = "unknown"


class ServiceValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING_CREDENTIALS = "missing_credentials"
    MODE_MISMATCH = "mode_mismatch"
    PROVIDER_UNREACHABLE = "provider_unreachable"
    UNSUPPORTED_PROVIDER = "unsupported_provider"
    DISABLED = "disabled"


class MarketDataServiceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    provider: Provider
    service_type: ServiceType = ServiceType.MARKET_DATA
    mode: ServiceMode = ServiceMode.NONE
    status: ServiceStatus = ServiceStatus.DRAFT
    is_default: bool = False
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
    validation_status: ServiceValidationStatus | None = None
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
            mode=self.mode,
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


class AIServiceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    provider: AIProvider
    service_type: AIServiceType = AIServiceType.AI
    status: ServiceStatus = ServiceStatus.DRAFT
    is_default: bool = False
    credentials_ref: str | None = None
    has_api_key: bool = False
    capability_label: AICapabilityLabel = AICapabilityLabel.UNKNOWN
    validation_status: ServiceValidationStatus | None = None
    validation_message: str | None = None
    last_validated_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    disabled_at: datetime | None = None


class MarketDataServiceWrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    provider: Provider
    mode: ServiceMode = ServiceMode.NONE
    api_key: str | None = None
    api_secret: str | None = None
    capabilities: MarketDataCapabilities | None = None
    capability_notes: tuple[str, ...] = ()

    @field_validator("api_key", "api_secret")
    @classmethod
    def reject_masked_secret(cls, value: str | None) -> str | None:
        if value is not None and value.strip() == MASKED_SECRET:
            raise ValueError("masked credentials are not accepted as replacement secrets")
        return value


class AIServiceWrite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    provider: AIProvider
    api_key: str | None = None
    capability_label: AICapabilityLabel = AICapabilityLabel.UNKNOWN

    @field_validator("api_key")
    @classmethod
    def reject_masked_secret(cls, value: str | None) -> str | None:
        if value is not None and value.strip() == MASKED_SECRET:
            raise ValueError("masked credentials are not accepted as replacement secrets")
        return value


class MarketDataServiceList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[MarketDataServiceRecord, ...]


class AIServiceList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[AIServiceRecord, ...]

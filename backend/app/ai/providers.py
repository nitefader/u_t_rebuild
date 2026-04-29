"""AI provider records — credentials, capability labels, and validation status.

Per plan_review.md A3, AI services live under ``app.ai`` (not the deleted
``app.services`` bucket). API surface is mounted under ``/api/v1/ai/providers``
and never shares wiring with market-data.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain._base import utc_now


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


class AIProviderStatus(StrEnum):
    DRAFT = "draft"
    VALID = "valid"
    INVALID = "invalid"
    DISABLED = "disabled"


class AIValidationStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING_CREDENTIALS = "missing_credentials"
    UNSUPPORTED_PROVIDER = "unsupported_provider"
    DISABLED = "disabled"


class AIServiceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1)
    provider: AIProvider
    service_type: AIServiceType = AIServiceType.AI
    status: AIProviderStatus = AIProviderStatus.DRAFT
    is_default: bool = False
    credentials_ref: str | None = None
    has_api_key: bool = False
    capability_label: AICapabilityLabel = AICapabilityLabel.UNKNOWN
    validation_status: AIValidationStatus | None = None
    validation_message: str | None = None
    last_validated_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    disabled_at: datetime | None = None


class DeleteAIServiceRequest(BaseModel):
    """Hard-delete guard — operator must type the current provider display name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confirm_service_name: str = Field(min_length=1)


class AIServiceDeletionResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    service_id: UUID
    message: str


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


class AIServiceList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    services: tuple[AIServiceRecord, ...]

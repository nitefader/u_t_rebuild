from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, utc_now


class ProgramStatus(StrEnum):
    DRAFT = "draft"
    FROZEN = "frozen"
    DEPRECATED = "deprecated"


class ValidationStatus(StrEnum):
    NOT_VALIDATED = "not_validated"
    VALID = "valid"
    BLOCKED = "blocked"


class ProgramVersion(DomainSchema):
    id: UUID
    program_id: UUID
    name: str
    version: int = Field(ge=1)
    status: ProgramStatus = ProgramStatus.DRAFT
    strategy_version_id: UUID
    strategy_controls_version_id: UUID
    risk_profile_version_id: UUID
    execution_style_version_id: UUID
    universe_snapshot_id: UUID
    validation_status: ValidationStatus = ValidationStatus.NOT_VALIDATED
    created_at: datetime = Field(default_factory=utc_now)
    frozen_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_inline_behavior(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {
                "conditions",
                "feature_refs",
                "indicators",
                "risk",
                "risk_settings",
                "execution_policy",
                "session_windows",
                "symbols",
                "broker_account_id",
                "deployment_status",
                "runtime_state",
                "live_universe_cache",
            }
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"program version cannot contain inline behavior: {sorted(present)}")
        return data

    @model_validator(mode="after")
    def validate_frozen_timestamp(self) -> "ProgramVersion":
        if self.status == ProgramStatus.FROZEN and self.frozen_at is None:
            raise ValueError("frozen program version requires frozen_at")
        return self

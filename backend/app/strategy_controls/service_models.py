"""Pydantic request/response models for StrategyControlsService."""

from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.domain.strategy_controls import (
    AllowedDirections,
    SessionPreference,
    SessionWindow,
    Weekday,
    _WEEKDAY_ORDER,
)
from backend.app.strategy_controls.models import StrategyControlsVersionRecord


class StrategyControlsDraft(BaseModel):
    """All operator-editable fields of StrategyControlsVersion.

    Excludes: id, strategy_controls_id, version, created_at.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    timeframe: str = Field(min_length=1)
    allowed_directions: AllowedDirections = AllowedDirections.LONG
    higher_timeframe_confirmation_required: bool = False
    session_preference: SessionPreference = SessionPreference.REGULAR_ONLY
    session_windows: list[SessionWindow] = Field(default_factory=list)
    avoid_first_minutes: int | None = Field(default=None, ge=0)
    no_new_entries_after: time | None = None
    force_flat_by: time | None = None
    time_based_exit_after_bars: int | None = Field(default=None, ge=1)
    time_based_exit_after_minutes: int | None = Field(default=None, ge=1)
    time_based_exit_after_days: int | None = Field(default=None, ge=1)
    cooldown_bars: int | None = Field(default=None, ge=0)
    cooldown_minutes: int | None = Field(default=None, ge=0)
    max_trades_per_session: int | None = Field(default=None, ge=1)
    max_trades_per_day: int | None = Field(default=None, ge=1)
    earnings_news_blackout_enabled: bool = False
    max_consecutive_losses_halt: int | None = Field(default=None, ge=1)
    skip_power_hour: bool = False
    day_of_week_restrictions: list[Weekday] = Field(default_factory=list)
    feature_refs: list[str] = Field(default_factory=list)
    regime_filter_refs: list[str] = Field(default_factory=list)

    @field_validator("day_of_week_restrictions", mode="before")
    @classmethod
    def normalize_day_restrictions(cls, v: object) -> list[Weekday]:
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            unique = list(dict.fromkeys(Weekday(d) for d in v))
            return sorted(unique, key=lambda d: _WEEKDAY_ORDER[d])
        return list(v)  # type: ignore[arg-type]


class StrategyControlsVersionSummary(BaseModel):
    """Compact summary entry used in history lists."""

    model_config = ConfigDict(frozen=True)

    version_id: UUID
    version: int
    saved_at: datetime


class StrategyControlsLibrarySummary(BaseModel):
    """One row in the library list (one per strategy_controls_id)."""

    model_config = ConfigDict(frozen=True)

    strategy_controls_id: UUID
    name: str
    head_version_id: UUID
    head_version_number: int
    is_default: bool
    retired_at: datetime | None
    usage_count: int


class StrategyControlsLibrary(BaseModel):
    """Full library detail: head version + version history."""

    model_config = ConfigDict(frozen=True)

    strategy_controls_id: UUID
    name: str
    is_default: bool
    retired_at: datetime | None
    head: StrategyControlsVersionRecord
    history: list[StrategyControlsVersionSummary]


class StrategyControlsUsedByResponse(BaseModel):
    """List of deployment ids that reference this library."""

    model_config = ConfigDict(frozen=True)

    deployment_ids: list[UUID]

from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, utc_now


class SessionName(StrEnum):
    PREMARKET = "premarket"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"


class SessionWindow(DomainSchema):
    session: SessionName = SessionName.REGULAR
    start: time
    end: time

    @model_validator(mode="after")
    def validate_window(self) -> "SessionWindow":
        if self.start >= self.end:
            raise ValueError("session window start must be before end")
        return self


class StrategyControlsVersion(DomainSchema):
    id: UUID
    strategy_controls_id: UUID
    version: int = Field(ge=1)
    name: str
    timeframe: str
    session_windows: list[SessionWindow] = Field(default_factory=list)
    cooldown_bars: int | None = Field(default=None, ge=0)
    cooldown_minutes: int | None = Field(default=None, ge=0)
    max_trades_per_session: int | None = Field(default=None, ge=1)
    max_trades_per_day: int | None = Field(default=None, ge=1)
    event_blackout_enabled: bool = False
    feature_refs: list[str] = Field(default_factory=list)
    regime_filter_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_cooldown(self) -> "StrategyControlsVersion":
        if self.cooldown_bars is not None and self.cooldown_minutes is not None:
            raise ValueError("use cooldown_bars or cooldown_minutes, not both")
        return self

from __future__ import annotations

from datetime import datetime, time
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from ._base import DomainSchema, utc_now


class SessionName(StrEnum):
    PREMARKET = "premarket"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"


class Weekday(StrEnum):
    MON = "MON"
    TUE = "TUE"
    WED = "WED"
    THU = "THU"
    FRI = "FRI"


_WEEKDAY_ORDER: dict[Weekday, int] = {
    Weekday.MON: 0,
    Weekday.TUE: 1,
    Weekday.WED: 2,
    Weekday.THU: 3,
    Weekday.FRI: 4,
}


class SessionWindow(DomainSchema):
    session: SessionName = SessionName.REGULAR
    start: time
    end: time

    @model_validator(mode="after")
    def validate_window(self) -> "SessionWindow":
        if self.start >= self.end:
            raise ValueError("session window start must be before end")
        return self


# TradingHorizon lives here for historical reasons; the actual operator-facing
# horizon field lives on Deployment (backend/app/deployments/models.py).
# Deployment imports TradingHorizon from this module.
class TradingHorizon(StrEnum):
    SCALPING = "scalping"
    INTRADAY = "intraday"
    SWING = "swing"
    POSITION = "position"
    OTHER = "other"


class AllowedDirections(StrEnum):
    LONG = "long"
    SHORT = "short"
    BOTH = "both"


class SessionPreference(StrEnum):
    REGULAR_ONLY = "regular_only"
    REGULAR_AND_EXTENDED = "regular_and_extended"


class StrategyControlsVersion(DomainSchema):
    id: UUID
    strategy_controls_id: UUID
    version: int = Field(ge=1)
    name: str
    timeframe: str
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
    day_of_week_restrictions: tuple[Weekday, ...] = Field(default_factory=tuple)
    feature_refs: list[str] = Field(default_factory=list)
    regime_filter_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("day_of_week_restrictions", mode="before")
    @classmethod
    def normalize_day_restrictions(cls, v: object) -> tuple[Weekday, ...]:
        if v is None:
            return ()
        if isinstance(v, (list, tuple)):
            unique = list(dict.fromkeys(Weekday(d) for d in v))
            return tuple(sorted(unique, key=lambda d: _WEEKDAY_ORDER[d]))
        return v  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_cooldown(self) -> "StrategyControlsVersion":
        if self.cooldown_bars is not None and self.cooldown_minutes is not None:
            raise ValueError("use cooldown_bars or cooldown_minutes, not both")
        return self

    @model_validator(mode="after")
    def validate_time_based_exit(self) -> "StrategyControlsVersion":
        set_units = sum(
            1
            for value in (
                self.time_based_exit_after_bars,
                self.time_based_exit_after_minutes,
                self.time_based_exit_after_days,
            )
            if value is not None
        )
        if set_units > 1:
            raise ValueError(
                "time-based exit accepts at most one of bars / minutes / days"
            )
        return self

    @model_validator(mode="after")
    def validate_force_flat_after_no_new_entries(self) -> "StrategyControlsVersion":
        if (
            self.no_new_entries_after is not None
            and self.force_flat_by is not None
            and self.force_flat_by < self.no_new_entries_after
        ):
            raise ValueError(
                "force_flat_by must be at or after no_new_entries_after"
            )
        return self

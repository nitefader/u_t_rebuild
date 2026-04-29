"""Durable discovery schedules for Screeners and Watchlist refreshes.

Schedules are intentionally outside the trading spine. They can create
ScreenerRun evidence or WatchlistSnapshot entry-universe evidence; they never
submit orders, mutate Account state, or write broker truth.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from enum import StrEnum
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.domain._base import utc_now


class DiscoveryScheduleTargetKind(StrEnum):
    SCREENER_RUN = "screener_run"
    WATCHLIST_REFRESH = "watchlist_refresh"


class DiscoveryScheduleCadence(StrEnum):
    EVERY_N_MINUTES = "every_n_minutes"
    DAILY = "daily"
    WEEKLY = "weekly"


class DiscoveryScheduleStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class DiscoveryScheduleExecutionStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DiscoveryScheduleTrigger(StrEnum):
    DUE = "due"
    RUN_NOW = "run_now"


class DiscoveryScheduleApprovalPolicy(StrEnum):
    OPERATOR_REVIEW = "operator_review"
    AUTO_SNAPSHOT = "auto_snapshot"


WEEKDAYS_ET: tuple[int, ...] = (0, 1, 2, 3, 4)


class DiscoveryScheduleWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    target_kind: DiscoveryScheduleTargetKind
    screener_id: UUID | None = None
    screener_version_id: UUID | None = None
    watchlist_id: UUID | None = None
    cadence: DiscoveryScheduleCadence = DiscoveryScheduleCadence.DAILY
    interval_minutes: int | None = Field(default=None, ge=1, le=720)
    time_of_day: str | None = "09:15"
    weekdays: tuple[int, ...] = WEEKDAYS_ET
    timezone_name: str = "America/New_York"
    session_start: str | None = None
    session_end: str | None = None
    approval_policy: DiscoveryScheduleApprovalPolicy = DiscoveryScheduleApprovalPolicy.OPERATOR_REVIEW
    enabled: bool = True

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if not value:
            raise ValueError("at least one weekday is required")
        invalid = [day for day in value if day < 0 or day > 6]
        if invalid:
            raise ValueError("weekdays must use 0=Monday through 6=Sunday")
        return tuple(dict.fromkeys(value))

    @field_validator("time_of_day", "session_start", "session_end")
    @classmethod
    def _valid_time_text(cls, value: str | None) -> str | None:
        if value in {None, ""}:
            return None
        _parse_time(value)
        return value

    @model_validator(mode="after")
    def _valid_target_and_cadence(self) -> "DiscoveryScheduleWriteRequest":
        if self.target_kind == DiscoveryScheduleTargetKind.SCREENER_RUN:
            if self.screener_id is None or self.screener_version_id is None:
                raise ValueError("screener schedules require screener_id and screener_version_id")
            if self.watchlist_id is not None:
                raise ValueError("screener schedules cannot carry watchlist_id")
        if self.target_kind == DiscoveryScheduleTargetKind.WATCHLIST_REFRESH:
            if self.watchlist_id is None:
                raise ValueError("watchlist refresh schedules require watchlist_id")
            if self.screener_id is not None or self.screener_version_id is not None:
                raise ValueError("watchlist refresh schedules cannot carry screener ids")
        if self.cadence == DiscoveryScheduleCadence.EVERY_N_MINUTES and self.interval_minutes is None:
            raise ValueError("every_n_minutes schedules require interval_minutes")
        if self.cadence in {DiscoveryScheduleCadence.DAILY, DiscoveryScheduleCadence.WEEKLY} and self.time_of_day is None:
            raise ValueError("daily and weekly schedules require time_of_day")
        if (self.session_start is None) != (self.session_end is None):
            raise ValueError("session_start and session_end must be provided together")
        if self.session_start is not None and self.session_end is not None:
            if _parse_time(self.session_end) <= _parse_time(self.session_start):
                raise ValueError("session_end must be after session_start")
        try:
            ZoneInfo(self.timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone {self.timezone_name!r}") from exc
        return self


class DiscoverySchedulePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    cadence: DiscoveryScheduleCadence | None = None
    interval_minutes: int | None = Field(default=None, ge=1, le=720)
    time_of_day: str | None = None
    weekdays: tuple[int, ...] | None = None
    timezone_name: str | None = None
    session_start: str | None = None
    session_end: str | None = None
    approval_policy: DiscoveryScheduleApprovalPolicy | None = None
    enabled: bool | None = None

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, value: tuple[int, ...] | None) -> tuple[int, ...] | None:
        if value is None:
            return None
        return DiscoveryScheduleWriteRequest._valid_weekdays(value)

    @field_validator("time_of_day", "session_start", "session_end")
    @classmethod
    def _valid_time_text(cls, value: str | None) -> str | None:
        return DiscoveryScheduleWriteRequest._valid_time_text(value)


class DiscoverySchedule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schedule_id: UUID = Field(default_factory=uuid4)
    name: str
    target_kind: DiscoveryScheduleTargetKind
    screener_id: UUID | None = None
    screener_version_id: UUID | None = None
    watchlist_id: UUID | None = None
    cadence: DiscoveryScheduleCadence = DiscoveryScheduleCadence.DAILY
    interval_minutes: int | None = None
    time_of_day: str | None = "09:15"
    weekdays: tuple[int, ...] = WEEKDAYS_ET
    timezone_name: str = "America/New_York"
    session_start: str | None = None
    session_end: str | None = None
    approval_policy: DiscoveryScheduleApprovalPolicy = DiscoveryScheduleApprovalPolicy.OPERATOR_REVIEW
    enabled: bool = True
    status: DiscoveryScheduleStatus = DiscoveryScheduleStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_attempt_at: datetime | None = None
    last_success_at: datetime | None = None
    next_run_at: datetime | None = None
    last_status: DiscoveryScheduleExecutionStatus | None = None
    last_error: str | None = None
    last_screener_run_id: UUID | None = None
    last_watchlist_snapshot_id: UUID | None = None
    execution_count: int = 0
    audit_events: tuple[dict[str, object], ...] = Field(default_factory=tuple)


class DiscoveryScheduleExecution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: UUID = Field(default_factory=uuid4)
    schedule_id: UUID
    schedule_name: str
    target_kind: DiscoveryScheduleTargetKind
    trigger: DiscoveryScheduleTrigger
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    status: DiscoveryScheduleExecutionStatus = DiscoveryScheduleExecutionStatus.RUNNING
    screener_run_id: UUID | None = None
    watchlist_snapshot_id: UUID | None = None
    added_symbols: tuple[str, ...] = ()
    removed_symbols: tuple[str, ...] = ()
    stayed_symbols: tuple[str, ...] = ()
    error: str | None = None
    audit_events: tuple[dict[str, object], ...] = Field(default_factory=tuple)


class DiscoveryScheduleListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedules: tuple[DiscoverySchedule, ...] = ()


class DiscoveryScheduleExecutionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executions: tuple[DiscoveryScheduleExecution, ...] = ()


def schedule_from_request(
    request: DiscoveryScheduleWriteRequest,
    *,
    now: datetime | None = None,
) -> DiscoverySchedule:
    now = now or utc_now()
    schedule = DiscoverySchedule(
        name=request.name.strip(),
        target_kind=request.target_kind,
        screener_id=request.screener_id,
        screener_version_id=request.screener_version_id,
        watchlist_id=request.watchlist_id,
        cadence=request.cadence,
        interval_minutes=request.interval_minutes,
        time_of_day=request.time_of_day,
        weekdays=request.weekdays,
        timezone_name=request.timezone_name,
        session_start=request.session_start,
        session_end=request.session_end,
        approval_policy=request.approval_policy,
        enabled=request.enabled,
        status=DiscoveryScheduleStatus.ACTIVE if request.enabled else DiscoveryScheduleStatus.PAUSED,
        created_at=now,
        updated_at=now,
    )
    return schedule.model_copy(update={"next_run_at": next_run_at(schedule, after=now)})


def next_run_at(schedule: DiscoverySchedule, *, after: datetime) -> datetime | None:
    if not schedule.enabled or schedule.status != DiscoveryScheduleStatus.ACTIVE:
        return None
    zone = ZoneInfo(schedule.timezone_name)
    local_after = after.astimezone(zone)
    if schedule.cadence == DiscoveryScheduleCadence.EVERY_N_MINUTES:
        return _next_interval_run(schedule, local_after)
    return _next_fixed_time_run(schedule, local_after)


def _next_interval_run(schedule: DiscoverySchedule, local_after: datetime) -> datetime | None:
    interval = timedelta(minutes=schedule.interval_minutes or 60)
    candidate = local_after + interval
    start_text = schedule.session_start
    end_text = schedule.session_end
    if start_text is None or end_text is None:
        return candidate.astimezone(timezone.utc)
    start_time = _parse_time(start_text)
    end_time = _parse_time(end_text)
    zone = ZoneInfo(schedule.timezone_name)
    for day_offset in range(0, 14):
        day = (candidate + timedelta(days=day_offset)).date()
        if day.weekday() not in schedule.weekdays:
            continue
        session_start = datetime.combine(day, start_time, tzinfo=zone)
        session_end = datetime.combine(day, end_time, tzinfo=zone)
        if candidate < session_start:
            return session_start.astimezone(timezone.utc)
        if session_start <= candidate <= session_end:
            return candidate.astimezone(timezone.utc)
        candidate = datetime.combine(day + timedelta(days=1), start_time, tzinfo=zone)
    return None


def _next_fixed_time_run(schedule: DiscoverySchedule, local_after: datetime) -> datetime | None:
    zone = ZoneInfo(schedule.timezone_name)
    run_time = _parse_time(schedule.time_of_day or "09:15")
    for day_offset in range(0, 370):
        day = (local_after + timedelta(days=day_offset)).date()
        if day.weekday() not in schedule.weekdays:
            continue
        candidate = datetime.combine(day, run_time, tzinfo=zone)
        if candidate <= local_after:
            continue
        if schedule.session_start is not None and schedule.session_end is not None:
            start_time = _parse_time(schedule.session_start)
            end_time = _parse_time(schedule.session_end)
            local_time = candidate.time().replace(second=0, microsecond=0)
            if not (start_time <= local_time <= end_time):
                continue
        return candidate.astimezone(timezone.utc)
    return None


def _parse_time(value: str) -> time:
    try:
        hour_text, minute_text = value.split(":", 1)
        return time(hour=int(hour_text), minute=int(minute_text))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("time must be HH:MM") from exc

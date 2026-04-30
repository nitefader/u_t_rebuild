from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain._base import utc_now
from backend.app.domain.strategy_controls import TradingHorizon


class RuntimeError(ValueError):
    """Raised when the internal runtime cannot make a safe decision."""


class RuntimeStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    PAUSED = "paused"
    KILLED = "killed"
    ERROR = "error"
    BLOCKED_RECOVERY = "blocked_recovery"
    RECOVERED_READY = "recovered_ready"


class RuntimeEventType(StrEnum):
    BAR_RECEIVED = "bar_received"
    FEATURE_UPDATED = "feature_updated"
    SIGNAL_CANDIDATE = "signal_candidate"
    SIGNAL_BLOCKED = "signal_blocked"
    SIGNAL_PLAN_CREATED = "signal_plan_created"
    SIGNAL_PLAN_BLOCKED = "signal_plan_blocked"
    RUNTIME_STATE_UPDATED = "runtime_state_updated"


class DeploymentContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    strategy_version_id: UUID | None = None
    strategy_version: int | None = None
    mode: str = "internal_stream"
    status: RuntimeStatus = RuntimeStatus.READY
    risk_horizon: TradingHorizon | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def reject_broker_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            migrated = dict(data)
            legacy_program = migrated.pop("program", None)
            if legacy_program is not None:
                migrated.setdefault("strategy_version_id", getattr(legacy_program, "strategy_version_id", None))
                migrated.setdefault("strategy_version", getattr(legacy_program, "version", None))
            forbidden = {"broker_account_id", "alpaca_account_id", "client_order_id", "broker_order_id"}
            present = forbidden.intersection(migrated)
            if present:
                raise ValueError(f"deployment context cannot contain broker fields: {sorted(present)}")
            return migrated
        return data


class RuntimeState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    status: RuntimeStatus = RuntimeStatus.READY
    processed_bar_count: int = 0
    candidate_intent_count: int = 0
    signal_plan_count: int = 0
    last_bar_timestamp_by_symbol_timeframe: dict[str, datetime] = Field(default_factory=dict)
    last_signal_timestamp: datetime | None = None
    last_signal_plan_timestamp: datetime | None = None
    last_governor_decision: dict[str, object] | None = None
    last_order_id: UUID | None = None
    last_broker_sync_timestamp: datetime | None = None
    last_error: str | None = None

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_runtime_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            migrated = dict(data)
            if "execution_intent_count" in migrated and "signal_plan_count" not in migrated:
                migrated["signal_plan_count"] = migrated.pop("execution_intent_count")
            if "last_execution_intent_timestamp" in migrated and "last_signal_plan_timestamp" not in migrated:
                migrated["last_signal_plan_timestamp"] = migrated.pop("last_execution_intent_timestamp")
            return migrated
        return data


class RuntimeEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    timestamp: datetime
    event_type: RuntimeEventType
    deployment_id: UUID
    symbol: str | None = None
    timeframe: str | None = None
    message: str
    details: dict[str, object] = Field(default_factory=dict)

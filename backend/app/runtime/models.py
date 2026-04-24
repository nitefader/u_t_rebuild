from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import CandidateSide, IntentType, OrderType, ProgramVersion, TimeInForce
from backend.app.domain._base import utc_now


class RuntimeError(ValueError):
    """Raised when the internal runtime cannot make a safe decision."""


class RuntimeStatus(StrEnum):
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    KILLED = "killed"
    ERROR = "error"


class RuntimeEventType(StrEnum):
    BAR_RECEIVED = "bar_received"
    FEATURE_UPDATED = "feature_updated"
    SIGNAL_CANDIDATE = "signal_candidate"
    SIGNAL_BLOCKED = "signal_blocked"
    EXECUTION_INTENT_CREATED = "execution_intent_created"
    EXECUTION_INTENT_BLOCKED = "execution_intent_blocked"
    RUNTIME_STATE_UPDATED = "runtime_state_updated"


class DeploymentContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    program: ProgramVersion
    mode: str = "internal_stream"
    status: RuntimeStatus = RuntimeStatus.READY
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def reject_broker_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {"broker_account_id", "alpaca_account_id", "client_order_id", "broker_order_id"}
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"deployment context cannot contain broker fields: {sorted(present)}")
        return data


class RuntimeState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    status: RuntimeStatus = RuntimeStatus.READY
    processed_bar_count: int = 0
    candidate_intent_count: int = 0
    execution_intent_count: int = 0
    last_bar_timestamp_by_symbol_timeframe: dict[str, datetime] = Field(default_factory=dict)
    last_signal_timestamp: datetime | None = None
    last_execution_intent_timestamp: datetime | None = None
    last_error: str | None = None


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


class ExecutionIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    program_version_id: UUID
    symbol: str
    side: CandidateSide
    intent_type: IntentType
    qty: float = Field(gt=0)
    order_type: OrderType
    time_in_force: TimeInForce
    timestamp: datetime
    signal_name: str
    reason: str
    features_used: dict[str, object] = Field(default_factory=dict)
    stop_candidate: float | None = None
    target_candidate: float | None = None
    governor_approved: bool = False
    governor_reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_order_and_broker_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {"order_id", "broker_order_id", "client_order_id", "alpaca_order_id", "filled_qty", "fill_price"}
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"execution intent cannot contain order/fill fields: {sorted(present)}")
        return data


class RuntimeDecisionBatch(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    state: RuntimeState
    events: tuple[RuntimeEvent, ...]
    execution_intents: tuple[ExecutionIntent, ...]

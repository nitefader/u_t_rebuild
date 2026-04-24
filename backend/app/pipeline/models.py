from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers import BrokerOrderResult
from backend.app.domain import CandidateTradeIntent
from backend.app.governor import GovernorDecision
from backend.app.orders import InternalOrder
from backend.app.runtime import ExecutionIntent


class PipelineEventType(StrEnum):
    CANDIDATE_TRADE_INTENT = "candidate_trade_intent"
    EXECUTION_INTENT = "execution_intent"
    GOVERNOR_DECISION = "governor_decision"
    ORDER_CREATED = "order_created"
    BROKER_RESULT = "broker_result"
    LEDGER_UPDATE = "ledger_update"
    FEATURE_UPDATED = "feature_updated"
    SIGNAL_BLOCKED = "signal_blocked"


class PipelineEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    timestamp: datetime
    deployment_id: UUID
    event_type: PipelineEventType
    symbol: str | None = None
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class PipelineResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    events: tuple[PipelineEvent, ...]
    candidate_intents: tuple[CandidateTradeIntent, ...] = ()
    execution_intents: tuple[ExecutionIntent, ...] = ()
    governor_decisions: tuple[GovernorDecision, ...] = ()
    orders: tuple[InternalOrder, ...] = ()
    broker_results: tuple[BrokerOrderResult, ...] = ()
    ledger_updates: tuple[InternalOrder, ...] = ()

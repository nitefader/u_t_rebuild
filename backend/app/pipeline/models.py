from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers import BrokerOrderResult
from backend.app.domain import AccountSignalPlanEvaluation, CandidateTradeIntent, SignalPlan
from backend.app.governor import GovernorDecision
from backend.app.orders import InternalOrder


class PipelineEventType(StrEnum):
    CANDIDATE_TRADE_INTENT = "candidate_trade_intent"
    GOVERNOR_DECISION = "governor_decision"
    ORDER_CREATED = "order_created"
    BROKER_RESULT = "broker_result"
    LEDGER_UPDATE = "ledger_update"
    FEATURE_UPDATED = "feature_updated"
    SIGNAL_BLOCKED = "signal_blocked"
    PROTECTION_PLACED = "protection_placed"
    PROTECTION_NAKED = "protection_naked"
    # W2-A-1a (audit P0 #1, pre-T-7 bundle): emitted whenever
    # _governor_candidate_inputs falls back to a gating-time proxy because the
    # SignalPlan stop is encoded as post_fill_pct (concrete stop_price is
    # unresolvable until BrokerSync confirms the entry fill). Operations sees
    # which gates ran on a proxy vs. a concrete stop.
    GOVERNOR_CANDIDATE_OPEN_RISK_PROXIED = "governor_candidate_open_risk_proxied_from_post_fill_pct"
    # W2-A adversarial-critic fix #3: emitted when the orchestrator's
    # in-memory evaluation cannot be persisted to the runtime store
    # (SQLite IntegrityError, disk full, schema mismatch). The in-memory
    # bucket is preserved so the bar's PipelineResult is still consistent;
    # the loop continues so accounts later in the fanout do not silently
    # die because account #N's persist write raised. Operations sees the
    # exact failure and the operator can drain the gap.
    EVALUATION_PERSIST_FAILED = "evaluation_persist_failed"
    SIGNAL_PLAN_PERSIST_FAILED = "signal_plan_persist_failed"


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
    signal_plans: tuple[SignalPlan, ...] = ()
    account_evaluations: tuple[AccountSignalPlanEvaluation, ...] = ()
    governor_decisions: tuple[GovernorDecision, ...] = ()
    orders: tuple[InternalOrder, ...] = ()
    broker_results: tuple[BrokerOrderResult, ...] = ()
    ledger_updates: tuple[InternalOrder, ...] = ()

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers.models import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderMapping,
    BrokerPositionSnapshot,
    BrokerSyncState,
)
from backend.app.runtime.daily_account_state import DailyAccountState
from backend.app.control_plane.service import ControlPlaneState
from backend.app.domain import AccountSignalPlanEvaluation
from backend.app.governor.models import GovernorDecision, GovernorPolicy
from backend.app.orders.models import InternalOrder, InternalOrderStatus
from backend.app.pipeline.models import PipelineEvent
from backend.app.runtime.models import RuntimeEvent, RuntimeState, RuntimeStatus


class DeploymentSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    status: RuntimeStatus
    is_running: bool
    account_id: UUID | None = None
    strategy_version_id: UUID | None = None
    strategy_version: int | None = None


class AccountSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    snapshot: BrokerAccountSnapshot | None = None
    sync_state: BrokerSyncState | None = None
    open_orders_count: int = 0
    positions_count: int = 0
    is_paused: bool = False
    is_killed: bool = False


class InternalOrderLedgerSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    total_count: int = 0
    open_count: int = 0
    terminal_count: int = 0
    by_status: dict[str, int] = Field(default_factory=dict)
    by_intent: dict[str, int] = Field(default_factory=dict)


class FlattenRequestResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    status: str
    reason: str
    scope: str
    target_id: UUID
    result: object | None = None


class RuntimeOverview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    system_recovery_active: bool
    global_kill_active: bool
    control_state: ControlPlaneState
    broker_accounts: tuple[AccountSummary, ...] = ()
    deployments: tuple[DeploymentSummary, ...] = ()
    stale_sync_accounts: tuple[BrokerSyncState, ...] = ()
    blocked_deployments: tuple[DeploymentSummary, ...] = ()
    open_orders_count: int = 0
    open_positions_count: int = 0
    latest_governor_decisions: tuple[GovernorDecision, ...] = ()
    latest_broker_sync_timestamp: datetime | None = None
    latest_runtime_event_timestamp: datetime | None = None
    research_evidence_summary: tuple["ResearchEvidenceSummary", ...] = ()


class OperatorPositionView(BaseModel):
    """Operator-facing wrapper around a BrokerPositionSnapshot.

    T-5 of the Strategy-to-Broker Bracket Execution Program. Adds the
    operator-visible ``protection_status`` derived from the orders
    ledger so the Open Positions card surfaces naked exposure
    immediately.

    ``protection_status`` is one of:
    - ``protected`` — at least one open child stop order references the
      entry that opened this position.
    - ``pending_protection`` — entry filled but no protective child has
      been accepted yet (in-flight protective placement).
    - ``naked`` — entry filled, ProtectivePlacer / OrderManager could
      not place a stop child (placement failed or rejected). Operator
      action required.
    - ``unknown`` — unable to derive (no ``opening_signal_plan_id`` on
      the position, or origin is not a SignalPlan trade).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot: BrokerPositionSnapshot
    protection_status: str = "unknown"
    protective_order_count: int = 0


class AccountOperations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    broker_account_snapshot: BrokerAccountSnapshot | None = None
    broker_sync_freshness: BrokerSyncState | None = None
    open_broker_orders: tuple[BrokerOpenOrderSnapshot, ...] = ()
    internal_order_ledger_summary: InternalOrderLedgerSummary
    positions: tuple[BrokerPositionSnapshot, ...] = ()
    position_views: tuple[OperatorPositionView, ...] = ()
    deployments: tuple[DeploymentSummary, ...] = ()
    is_paused: bool = False
    is_killed: bool = False


class AccountSignalPlanEvaluationListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluations: tuple[AccountSignalPlanEvaluation, ...] = ()


class DeploymentOperations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    runtime_status: RuntimeStatus | None = None
    strategy_version_id: UUID | None = None
    strategy_version: int | None = None
    broker_account_id: UUID | None = None
    governor_id: str
    governor_state: GovernorPolicy | None = None
    last_market_data_timestamp: datetime | None = None
    last_broker_sync_timestamp: datetime | None = None
    last_decision_timestamp: datetime | None = None
    runtime_loop_state: RuntimeStatus | None = None
    last_signal_timestamp: datetime | None = None
    last_governor_decision: dict[str, object] | None = None
    last_order_id: UUID | None = None
    last_runtime_error: str | None = None
    open_orders: tuple[InternalOrder, ...] = ()
    trades: tuple[BrokerFillUpdateEvent | object, ...] = ()
    fills: tuple[BrokerFillUpdateEvent, ...] = ()
    latest_pipeline_events: tuple[PipelineEvent | RuntimeEvent, ...] = ()
    latest_governor_decisions: tuple[GovernorDecision, ...] = ()


class OrderDetail(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    internal_order: InternalOrder
    broker_mapping: BrokerOrderMapping | None = None
    broker_account_id: UUID
    deployment_id: UUID | None = None
    strategy_version_id: UUID | None = None
    broker_order_id: str | None = None
    broker_status: str = "unknown_stale"
    broker_sync_timestamp: datetime | None = None
    fills: tuple[BrokerFillUpdateEvent, ...] = ()
    trade_summary: dict[str, object] = Field(default_factory=dict)


class DailyRiskStateResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    state: DailyAccountState | None = None
    cooldown_remaining_minutes: float | None = None


class ResearchEvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_type: str
    count: int = Field(ge=0)
    latest_created_at: datetime | None = None


OPEN_ORDER_STATUSES = {
    InternalOrderStatus.CREATED,
    InternalOrderStatus.PENDING_SUBMISSION,
    InternalOrderStatus.SUBMITTED,
    InternalOrderStatus.ACCEPTED,
    InternalOrderStatus.PARTIALLY_FILLED,
}


TERMINAL_ORDER_STATUSES = {
    InternalOrderStatus.FILLED,
    InternalOrderStatus.CANCELED,
    InternalOrderStatus.REJECTED,
    InternalOrderStatus.FAILED,
}

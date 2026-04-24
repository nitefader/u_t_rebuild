from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers.models import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerPositionSnapshot,
    BrokerSyncState,
)
from backend.app.control_plane.service import ControlPlaneState
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
    program_id: UUID | None = None
    program_version: int | None = None


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


class AccountOperations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    broker_account_snapshot: BrokerAccountSnapshot | None = None
    broker_sync_freshness: BrokerSyncState | None = None
    open_broker_orders: tuple[BrokerOpenOrderSnapshot, ...] = ()
    internal_order_ledger_summary: InternalOrderLedgerSummary
    positions: tuple[BrokerPositionSnapshot, ...] = ()
    deployments: tuple[DeploymentSummary, ...] = ()
    is_paused: bool = False
    is_killed: bool = False


class DeploymentOperations(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    runtime_status: RuntimeStatus | None = None
    program_id: UUID | None = None
    program_version: int | None = None
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

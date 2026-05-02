from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from backend.app.domain._base import utc_now
from backend.app.domain.trading_mode import BROKER_MODES, TradingMode


class BrokerAdapterError(ValueError):
    """Raised when broker adapter boundary input or output is invalid."""


class BrokerOrderStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    PARTIAL_FILL = "partial_fill"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    PENDING_CANCEL = "pending_cancel"
    REPLACED = "replaced"
    SUSPENDED = "suspended"
    DONE_FOR_DAY = "done_for_day"


class BrokerPositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class BrokerReconciliationIssueType(StrEnum):
    MISSING_LOCAL_ORDER = "missing_local_order"
    MISSING_BROKER_ORDER = "missing_broker_order"
    MISMATCHED_FILL = "mismatched_fill"
    POSITION_MISMATCH = "position_mismatch"
    STALE_SYNC = "stale_sync"


class AccountTradeSyncState(StrEnum):
    OPEN = "open"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DEGRADED = "degraded"
    DOWN = "down"
    OPERATOR_PAUSED = "operator_paused"
    CREDENTIALS_INVALID = "credentials_invalid"


class AccountTradeSyncStatus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    provider: str
    broker_mode: TradingMode
    enabled: bool
    open: bool
    connected: bool
    authenticated: bool
    status: AccountTradeSyncState
    last_event_at: datetime | None = None
    last_sync_write_at: datetime | None = None
    reconnect_count: int = Field(default=0, ge=0)
    last_error: str | None = None
    started_at: datetime | None = None
    operator_paused_at: datetime | None = None

    @model_validator(mode="after")
    def pause_state_is_explicit(self) -> "AccountTradeSyncStatus":
        if self.status == AccountTradeSyncState.OPERATOR_PAUSED and self.operator_paused_at is None:
            raise ValueError("operator-paused Account Trade Sync requires operator_paused_at")
        if self.status == AccountTradeSyncState.CREDENTIALS_INVALID and self.authenticated:
            raise ValueError("credentials-invalid Account Trade Sync cannot be authenticated")
        return self


class BrokerOrderResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    status: BrokerOrderStatus
    broker_order_id: str | None = None
    broker_status: str | None = None
    filled_quantity: float = Field(default=0, ge=0)
    filled_avg_price: float | None = Field(default=None, ge=0)
    remaining_quantity: float | None = Field(default=None, ge=0)
    reason: str | None = None
    received_at: datetime = Field(default_factory=utc_now)
    submitted_at: datetime | None = None
    updated_at: datetime | None = None
    filled_at: datetime | None = None
    canceled_at: datetime | None = None
    reject_code: str | None = None
    raw_status: str | None = None
    broker_reference: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "BrokerOrderResult":
        if self.status == BrokerOrderStatus.REJECTED and not self.reason:
            raise ValueError("rejected broker result requires reason")
        if self.status in {BrokerOrderStatus.PARTIAL_FILL, BrokerOrderStatus.FILLED} and self.filled_quantity <= 0:
            raise ValueError(f"{self.status.value} broker result requires filled_quantity > 0")
        if self.remaining_quantity is not None and self.remaining_quantity < 0:
            raise ValueError("remaining_quantity cannot be negative")
        return self


class BrokerAccountSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    account_id: UUID
    equity: float = Field(ge=0)
    cash: float
    buying_power: float = Field(ge=0)
    daytrading_buying_power: float = Field(default=0, ge=0)
    regt_buying_power: float | None = Field(default=None, ge=0)
    non_marginable_buying_power: float | None = Field(default=None, ge=0)
    multiplier: float | None = Field(default=None, ge=0)
    portfolio_value: float | None = Field(default=None, ge=0)
    long_market_value: float | None = None
    short_market_value: float | None = None
    initial_margin: float | None = Field(default=None, ge=0)
    maintenance_margin: float | None = Field(default=None, ge=0)
    last_maintenance_margin: float | None = Field(default=None, ge=0)
    last_equity: float | None = Field(default=None, ge=0)
    sma: float | None = None
    daytrade_count: int | None = Field(default=None, ge=0)
    trade_suspended_by_user: bool = False
    transfers_blocked: bool = False
    crypto_status: str | None = None
    currency: str | None = None
    accrued_fees: float | None = None
    pending_transfer_in: float | None = None
    pending_transfer_out: float | None = None
    is_pattern_day_trader: bool = Field(
        default=False,
        validation_alias=AliasChoices("is_pattern_day_trader", "pattern_day_trader"),
    )
    trading_blocked: bool = False
    account_status: str = "unknown"
    external_account_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now, validation_alias=AliasChoices("timestamp", "last_synced_at"))
    provider: str | None = None
    mode: TradingMode | None = None
    account_blocked: bool = False
    shorting_enabled: bool = False

    @property
    def pattern_day_trader(self) -> bool:
        return self.is_pattern_day_trader

    @property
    def last_synced_at(self) -> datetime:
        return self.timestamp

    @model_validator(mode="after")
    def validate_broker_mode(self) -> "BrokerAccountSnapshot":
        if self.mode is not None and self.mode not in BROKER_MODES:
            raise ValueError(f"broker account snapshot requires BROKER mode, got {self.mode.value}")
        return self


_AdoptionStatus = Literal["managed", "unmanaged", "adopted_by_guardian"]
_AdoptionReason = Literal["owner_unknown", "owner_deployment_down_unprotected"]


class BrokerPositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    account_id: UUID
    symbol: str
    qty: float = Field(validation_alias=AliasChoices("qty", "quantity"))
    side: BrokerPositionSide
    avg_entry_price: float = Field(ge=0)
    market_value: float
    unrealized_pl: float = 0
    deployment_id: UUID | None = None
    strategy_id: UUID | None = None
    opening_signal_plan_id: UUID | None = None
    position_lineage_id: UUID | None = None
    # M2 (HARD.MD P0-2) — true when the position has no matched lineage AND
    # no Guardian adopted it. Surfaced to the operator as an "Unmanaged"
    # badge and included in Governor concentration evaluation so silent
    # broker-side positions cannot bypass per-Account caps.
    unmanaged_broker_position: bool = False
    # M11 Guardian Assignment — adoption lineage. All None on a normal
    # managed position; populated by ``BrokerSync._enrich_position_snapshot_with_lineage``
    # when the Account's Guardian Deployment adopts an orphan or
    # owner-down-unprotected position. One-way: never auto-cleared.
    adoption_status: _AdoptionStatus | None = None
    adoption_reason: _AdoptionReason | None = None
    original_owner_deployment_id: UUID | None = None
    original_owner_deployment_name: str | None = None
    deployment_name: str | None = None
    # M11 FR11.4 case 4 — set when the position has a matched lineage but
    # the owner Deployment is not healthy. ``owner_self_protected=True``
    # means the broker has stop/stop-limit/trailing-stop orders open that
    # cover the full position quantity in the closing direction; in that
    # case Guardian intentionally does NOT adopt (operator pause case).
    owner_deployment_healthy: bool | None = None
    owner_self_protected: bool | None = None
    status: str | None = None
    timestamp: datetime = Field(default_factory=utc_now, validation_alias=AliasChoices("timestamp", "last_synced_at"))

    @property
    def quantity(self) -> float:
        return self.qty

    @property
    def last_synced_at(self) -> datetime:
        return self.timestamp

    @model_validator(mode="after")
    def normalize_position_side(self) -> "BrokerPositionSnapshot":
        if self.qty > 0 and self.side != BrokerPositionSide.LONG:
            raise ValueError("positive quantity requires long side")
        if self.qty < 0 and self.side != BrokerPositionSide.SHORT:
            raise ValueError("negative quantity requires short side")
        return self


class BrokerOpenOrderSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float = Field(gt=0)
    filled_qty: float = Field(default=0, ge=0)
    status: BrokerOrderStatus
    order_type: str
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    timestamp: datetime = Field(default_factory=utc_now)


class BrokerOrderUpdateEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    client_order_id: str
    status: BrokerOrderStatus
    broker_order_id: str | None = None
    symbol: str | None = None
    side: str | None = None
    qty: float | None = Field(default=None, gt=0)
    broker_status: str | None = None
    order_type: str | None = None
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    filled_quantity: float = Field(default=0, ge=0)
    filled_avg_price: float | None = Field(default=None, ge=0)
    remaining_quantity: float | None = Field(default=None, ge=0)
    reason: str | None = None
    event_at: datetime = Field(default_factory=utc_now)
    submitted_at: datetime | None = None
    updated_at: datetime | None = None
    filled_at: datetime | None = None
    canceled_at: datetime | None = None
    reject_code: str | None = None
    raw_status: str | None = None
    broker_reference: str | None = None


class BrokerFillUpdateEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    client_order_id: str
    symbol: str
    qty: float = Field(gt=0)
    price: float = Field(ge=0)
    side: str
    broker_order_id: str | None = None
    broker_execution_id: str | None = None
    event_at: datetime = Field(default_factory=utc_now)


class BrokerSyncState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    last_sync_at: datetime
    last_event_at: datetime | None = None
    last_poll_sync_at: datetime | None = None
    last_successful_sync_at: datetime | None = None
    is_stale: bool
    stale_reason: str | None = None


class BrokerPositionDelta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    expected_qty: float
    broker_qty: float
    delta_qty: float


class BrokerOrderMapping(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    broker_order_id: str
    provider: str
    account_id: UUID
    created_at: datetime = Field(default_factory=utc_now)
    last_synced_at: datetime = Field(default_factory=utc_now)


class BrokerReconciliationIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    issue_type: BrokerReconciliationIssueType
    account_id: UUID
    symbol: str | None = None
    order_id: UUID | None = None
    client_order_id: str | None = None
    broker_order_id: str | None = None
    message: str
    expected: float | str | None = None
    actual: float | str | None = None
    action: str = "flag_only"
    detected_at: datetime = Field(default_factory=utc_now)


class BrokerReconciliationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    checked_at: datetime = Field(default_factory=utc_now)
    updated_order_count: int = 0
    broker_position_count: int = 0
    issues: tuple[BrokerReconciliationIssue, ...] = ()
    matched_orders: tuple[str, ...] = ()
    unmatched_broker_orders: tuple[BrokerOpenOrderSnapshot, ...] = ()
    unmatched_internal_orders: tuple[str, ...] = ()
    position_deltas: tuple[BrokerPositionDelta, ...] = ()
    sync_status: BrokerSyncState | None = None

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    @property
    def is_stale(self) -> bool:
        if self.sync_status is not None:
            return self.sync_status.is_stale
        return any(issue.issue_type == BrokerReconciliationIssueType.STALE_SYNC for issue in self.issues)


class BrokerErrorEvent(BaseModel):
    """Structured broker error event per Playbook §17 error taxonomy.

    Every broker error that crosses a subsystem boundary (preflight rejection,
    order submission failure, stream disruption, reconciliation mismatch,
    credentials problem) is emitted as a ``BrokerErrorEvent``.  The fields map
    directly to the §17 schema so the Operations API can surface them with
    operator-readable next steps rather than raw exceptions.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    family: Literal["preflight", "submit", "stream", "reconcile", "credentials"]
    severity: Literal["info", "warning", "error", "critical"]
    source: str  # e.g. "alpaca_adapter" / "broker_sync" / "order_manager"
    operator_advisory: str  # human-readable next step for the operator
    raw_broker_code: str | None = None
    raw_broker_message: str | None = None
    account_id: UUID | None = None
    symbol: str | None = None
    occurred_at: datetime = Field(default_factory=utc_now)

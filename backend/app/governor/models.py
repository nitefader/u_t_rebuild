from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.domain._base import utc_now
from backend.app.orders.models import InternalOrderIntent
from backend.app.runtime.daily_account_state import DailyAccountState


class GovernorPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    global_kill_active: bool = False
    paused_account_ids: frozenset[UUID] = frozenset()
    paused_deployment_ids: frozenset[UUID] = frozenset()
    max_open_positions: int | None = Field(default=None, ge=0)
    max_symbol_concentration_pct: float | None = Field(default=None, gt=0, le=100)
    max_gross_exposure_pct: float | None = Field(default=None, gt=0)
    max_net_exposure_pct: float | None = Field(default=None, gt=0)
    max_open_risk_pct: float | None = Field(default=None, gt=0)
    # Slice B: set True by the GovernorPolicyResolver when a risk_horizon was
    # supplied AND the per-horizon plan lookup returned None (Account has not
    # mapped a RiskPlan for this horizon). The Governor's evaluate() rejects
    # entry signals with rule_id="account_missing_risk_plan_for_horizon" when
    # this flag is True. Defaults False so legacy callers are unaffected.
    requires_risk_plan: bool = False
    # T-7: daily risk guardrails. All default None so existing callers are unaffected.
    max_daily_loss_pct: float | None = Field(default=None, gt=0, le=100)
    max_drawdown_pct: float | None = Field(default=None, gt=0, le=100)
    cooldown_after_loss_minutes: int | None = Field(default=None, gt=0)


class BrokerSyncFreshness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    is_stale: bool = False
    last_synced_at: datetime | None = None
    checked_at: datetime = Field(default_factory=utc_now)
    reason: str | None = None


class PositionSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    deployment_id: UUID
    symbol: str
    quantity: float
    market_value: float = 0
    open_risk: float = Field(default=0, ge=0)


class UnmanagedPositionSummary(BaseModel):
    """M2 (HARD.MD P0-2) — broker-only position the Governor must still see.

    Manual or unknown-origin positions don't have a SignalPlan lineage,
    so they cannot be expressed as ``PositionSummary`` (which requires
    ``deployment_id``). The Governor's per-Account concentration gates
    must still account for them or they silently bypass the cap.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    symbol: str
    quantity: float
    market_value: float = 0


class PendingOpenSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    deployment_id: UUID
    symbol: str
    quantity: float = Field(gt=0)
    market_value: float = Field(ge=0)
    open_risk: float = Field(default=0, ge=0)


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    equity: float | None = Field(default=None, gt=0)
    positions: tuple[PositionSummary, ...] = ()
    # M2 — unmanaged broker positions classified by BrokerSync. Included in
    # concentration / gross / net evaluations alongside managed positions
    # so silent broker-side exposure cannot bypass per-Account caps.
    unmanaged_positions: tuple[UnmanagedPositionSummary, ...] = ()
    pending_opens: tuple[PendingOpenSummary, ...] = ()

    def open_position_count(self) -> int:
        managed = sum(1 for position in self.positions if position.quantity != 0)
        unmanaged = sum(1 for position in self.unmanaged_positions if position.quantity != 0)
        return managed + unmanaged

    def symbol_market_value(self, symbol: str) -> float:
        normalized_symbol = symbol.upper()
        managed = sum(
            abs(position.market_value)
            for position in self.positions
            if position.symbol.upper() == normalized_symbol
        )
        unmanaged = sum(
            abs(position.market_value)
            for position in self.unmanaged_positions
            if position.symbol.upper() == normalized_symbol
        )
        return managed + unmanaged

    def pending_symbol_market_value(self, symbol: str) -> float:
        normalized_symbol = symbol.upper()
        return sum(open_order.market_value for open_order in self.pending_opens if open_order.symbol.upper() == normalized_symbol)

    def gross_market_value(self) -> float:
        managed = sum(abs(position.market_value) for position in self.positions)
        unmanaged = sum(abs(position.market_value) for position in self.unmanaged_positions)
        return managed + unmanaged

    def net_market_value(self) -> float:
        managed = sum(position.market_value for position in self.positions)
        unmanaged = sum(position.market_value for position in self.unmanaged_positions)
        return managed + unmanaged

    def pending_market_value(self) -> float:
        return sum(open_order.market_value for open_order in self.pending_opens)

    def open_risk(self) -> float:
        # Unmanaged positions don't carry open_risk — they predate any
        # SignalPlan and have no risk-resolver lineage.
        return sum(position.open_risk for position in self.positions)

    def pending_open_risk(self) -> float:
        return sum(open_order.open_risk for open_order in self.pending_opens)

    def unmanaged_position_count(self) -> int:
        return sum(1 for position in self.unmanaged_positions if position.quantity != 0)

    def unmanaged_gross_market_value(self) -> float:
        return sum(abs(position.market_value) for position in self.unmanaged_positions)


class GovernorRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    deployment_id: UUID
    symbol: str
    runtime_state: object
    broker_sync: BrokerSyncFreshness
    portfolio: PortfolioSnapshot
    execution_intent: object | None = None
    signal_plan_id: UUID | None = None
    position_lineage_id: UUID | None = None
    order_intent: InternalOrderIntent | None = None
    candidate_market_value: float = Field(default=0, ge=0)
    candidate_open_risk: float = Field(default=0, ge=0)
    daily_state: DailyAccountState | None = None
    # Reference time for time-based gates (cooldown, etc). Live callers may
    # omit; replay/backtest MUST pass the bar/signal timestamp so cooldown
    # measures elapsed market time, not wall-clock.
    evaluated_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def derive_canonical_fields_from_execution_intent(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        intent = data.get("execution_intent")
        if intent is None:
            return data
        derived = dict(data)
        if "deployment_id" not in derived and hasattr(intent, "deployment_id"):
            derived["deployment_id"] = intent.deployment_id
        if "symbol" not in derived and hasattr(intent, "symbol"):
            derived["symbol"] = intent.symbol
        return derived

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class GovernorDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    approved: bool
    reason: str
    rule_id: str
    projected_state: dict[str, object] | None = None

    @classmethod
    def approve(cls, *, reason: str = "approved", rule_id: str = "allow", projected_state: dict[str, object] | None = None) -> "GovernorDecision":
        return cls(approved=True, reason=reason, rule_id=rule_id, projected_state=projected_state)

    @classmethod
    def reject(cls, *, reason: str, rule_id: str, projected_state: dict[str, object] | None = None) -> "GovernorDecision":
        return cls(approved=False, reason=reason, rule_id=rule_id, projected_state=projected_state)

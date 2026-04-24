from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain._base import utc_now
from backend.app.orders.models import InternalOrderIntent


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
    program_id: UUID
    symbol: str
    quantity: float
    market_value: float = 0
    open_risk: float = Field(default=0, ge=0)


class PendingOpenSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    deployment_id: UUID
    program_id: UUID
    symbol: str
    quantity: float = Field(gt=0)
    market_value: float = Field(ge=0)
    open_risk: float = Field(default=0, ge=0)


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    equity: float | None = Field(default=None, gt=0)
    positions: tuple[PositionSummary, ...] = ()
    pending_opens: tuple[PendingOpenSummary, ...] = ()

    def open_position_count(self) -> int:
        return sum(1 for position in self.positions if position.quantity != 0)

    def symbol_market_value(self, symbol: str) -> float:
        normalized_symbol = symbol.upper()
        return sum(abs(position.market_value) for position in self.positions if position.symbol.upper() == normalized_symbol)

    def pending_symbol_market_value(self, symbol: str) -> float:
        normalized_symbol = symbol.upper()
        return sum(open_order.market_value for open_order in self.pending_opens if open_order.symbol.upper() == normalized_symbol)

    def gross_market_value(self) -> float:
        return sum(abs(position.market_value) for position in self.positions)

    def net_market_value(self) -> float:
        return sum(position.market_value for position in self.positions)

    def pending_market_value(self) -> float:
        return sum(open_order.market_value for open_order in self.pending_opens)

    def open_risk(self) -> float:
        return sum(position.open_risk for position in self.positions)

    def pending_open_risk(self) -> float:
        return sum(open_order.open_risk for open_order in self.pending_opens)


class GovernorRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    execution_intent: object
    runtime_state: object
    broker_sync: BrokerSyncFreshness
    portfolio: PortfolioSnapshot
    order_intent: InternalOrderIntent | None = None
    candidate_market_value: float = Field(default=0, ge=0)
    candidate_open_risk: float = Field(default=0, ge=0)


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

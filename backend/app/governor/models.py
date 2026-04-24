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


class PortfolioSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    positions: tuple[PositionSummary, ...] = ()

    def open_position_count(self) -> int:
        return sum(1 for position in self.positions if position.quantity != 0)

    def symbol_market_value(self, symbol: str) -> float:
        normalized_symbol = symbol.upper()
        return sum(abs(position.market_value) for position in self.positions if position.symbol.upper() == normalized_symbol)

    def gross_market_value(self) -> float:
        return sum(abs(position.market_value) for position in self.positions)


class GovernorRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    execution_intent: object
    runtime_state: object
    broker_sync: BrokerSyncFreshness
    portfolio: PortfolioSnapshot
    order_intent: InternalOrderIntent | None = None


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

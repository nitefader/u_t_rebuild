"""RiskDecisionCard — traceable sizing artifact for every sized SignalPlan.

RiskPlan belongs to the Account or selected research run. SignalPlan describes
the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan,
and current account or simulated account state to produce a RiskDecisionCard.
No simulated or real order may be created without that RiskDecisionCard.

See ``RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT.md`` §5.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field

from ._base import DomainSchema, JsonDict, utc_now


class RiskDecisionMode(StrEnum):
    BACKTEST = "backtest"
    SIM_LAB = "sim_lab"
    BROKER_PAPER = "broker_paper"
    BROKER_LIVE = "broker_live"
    WALK_FORWARD = "walk_forward"
    OPTIMIZATION = "optimization"


class RiskDecisionStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    REDUCED = "reduced"
    CAPPED = "capped"
    SKIPPED = "skipped"
    REQUIRES_OPERATOR = "requires_operator"


class RiskCalculationStep(DomainSchema):
    """One row of the RiskDecisionCard formula trace.

    Each step records a named formula, its inputs as a JSON object, and the
    scalar output — operator can replay the calculation end-to-end.
    """

    name: str = Field(min_length=1)
    formula: str = Field(min_length=1)
    inputs: JsonDict = Field(default_factory=dict)
    output: float


class RiskDecisionCard(DomainSchema):
    """Traceable sizing decision artifact emitted by RiskResolver.

    Persisted by the runtime store so any trade / order / fill / sim event can
    deep-link back to *why* a position size was approved or rejected.
    """

    # Identity
    risk_decision_id: UUID = Field(default_factory=uuid4)
    mode: RiskDecisionMode
    run_id: UUID
    session_id: UUID | None = None
    account_id: UUID | None = None
    simulated_account_id: UUID | None = None

    # Lineage
    strategy_id: UUID
    strategy_version_id: UUID
    deployment_id: UUID | None = None
    signal_plan_id: UUID
    candidate_trade_intent_id: UUID | None = None
    feature_snapshot_id: UUID | None = None

    # Context
    symbol: str = Field(min_length=1)
    side: str = Field(min_length=1)
    lifecycle_intent: str = Field(min_length=1)
    timestamp: datetime

    # Risk policy snapshot
    risk_plan_id: UUID
    risk_plan_version_id: UUID
    risk_score: float | None = None
    risk_tier: str | None = None
    config_fingerprint: str | None = None

    # Account / simulated-account state
    account_equity: float
    account_cash: float
    buying_power: float
    current_price: float = Field(gt=0)
    entry_price: float | None = None
    stop_price: float | None = None
    stop_distance: float | None = None
    stop_distance_pct: float | None = None

    # Sizing
    sizing_method: str = Field(min_length=1)
    formula_used: str = Field(min_length=1)
    raw_quantity: float = 0
    rounded_quantity: float = 0
    final_quantity: float = 0
    final_notional: float = 0
    rejected_quantity: float | None = None
    capped_quantity: float | None = None

    # Exposure projections
    max_loss_estimate: float | None = None
    risk_amount_requested: float | None = None
    risk_amount_allowed: float | None = None
    buying_power_required: float | None = None
    projected_gross_exposure: float | None = None
    projected_net_exposure: float | None = None
    projected_symbol_exposure: float | None = None
    projected_open_risk: float | None = None

    # Existing position context
    existing_position_quantity: float = 0
    existing_position_notional: float = 0
    existing_open_orders_count: int = 0
    existing_open_order_notional: float = 0

    # Rules
    fractional_quantity_allowed: bool = True
    whole_share_rounding: str = "floor"
    constraints_applied: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    # Decision
    decision: RiskDecisionStatus
    reason_codes: tuple[str, ...] = ()
    human_summary: str = Field(min_length=1)

    # Calculation trace (machine-readable formula steps)
    calculation_steps: tuple[RiskCalculationStep, ...] = ()

    # Provenance
    risk_resolver_version: str = "risk_resolver/v1"
    created_at: datetime = Field(default_factory=utc_now)


def card_payload_dump(card: RiskDecisionCard) -> dict[str, Any]:
    """Persistence helper — serialize for SQLite payload column."""
    return card.model_dump(mode="json")

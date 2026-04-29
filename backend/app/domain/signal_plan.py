from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, JsonDict, utc_now
from .execution_style import OrderType, TimeInForce
from .strategy import LogicalExitRule


class SignalPlanIntent(StrEnum):
    OPEN = "open"
    CLOSE = "close"
    REDUCE = "reduce"
    TARGET = "target"
    STOP = "stop"
    TRAIL = "trail"
    BREAKEVEN = "breakeven"
    RUNNER = "runner"
    LOGICAL_EXIT = "logical_exit"


class SignalPlanSide(StrEnum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class SignalPlanStatus(StrEnum):
    CREATED = "created"
    PUBLISHED = "published"
    EXPIRED = "expired"
    PARTIALLY_EXECUTED = "partially_executed"
    EXECUTED = "executed"
    SUPERSEDED = "superseded"
    CANCELED = "canceled"
    FAILED = "failed"


class SignalPlanTargetAction(StrEnum):
    REDUCE = "reduce"
    CLOSE = "close"


class SignalPlanRunnerManagement(StrEnum):
    HOLD = "hold"
    TRAIL = "trail"
    LOGICAL_EXIT = "logical_exit"
    MANUAL_REVIEW = "manual_review"


class SignalPlanLogicalExitScope(StrEnum):
    FULL_POSITION = "full_position"
    RUNNER = "runner"
    REMAINING_QUANTITY = "remaining_quantity"


class SignalPlanEntry(DomainSchema):
    order_type: OrderType = OrderType.MARKET
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    time_in_force_preference: TimeInForce | None = None
    extended_hours_preference: bool | None = None
    entry_window: str | None = None


class SignalPlanStop(DomainSchema):
    type: str = "none"
    stop_price: float | None = Field(default=None, gt=0)
    trailing_amount: float | None = Field(default=None, gt=0)
    trailing_percent: float | None = Field(default=None, gt=0)
    rule: str | None = None
    required: bool = False


class SignalPlanTarget(DomainSchema):
    label: str = Field(min_length=1, max_length=64)
    action: SignalPlanTargetAction = SignalPlanTargetAction.REDUCE
    quantity_pct: float = Field(gt=0, le=100)
    price: float | None = Field(default=None, gt=0)
    rule: str | None = None
    order_type_preference: OrderType | None = None


class SignalPlanRunner(DomainSchema):
    quantity_pct: float = Field(ge=0, le=100)
    management: SignalPlanRunnerManagement = SignalPlanRunnerManagement.HOLD
    trail_rule: str | None = None
    logical_exit_rule: str | None = None


class SignalPlanLogicalExit(DomainSchema):
    rule: LogicalExitRule
    action: SignalPlanTargetAction = SignalPlanTargetAction.CLOSE
    quantity_pct: float | None = Field(default=None, gt=0, le=100)
    applies_to: SignalPlanLogicalExitScope = SignalPlanLogicalExitScope.REMAINING_QUANTITY


class SignalPlan(DomainSchema):
    signal_plan_id: UUID
    deployment_id: UUID
    strategy_id: UUID
    strategy_version_id: UUID
    watchlist_snapshot_id: UUID | None = None
    symbol: str
    side: SignalPlanSide
    intent: SignalPlanIntent
    status: SignalPlanStatus = SignalPlanStatus.CREATED
    entry: SignalPlanEntry | None = None
    stop: SignalPlanStop | None = None
    targets: tuple[SignalPlanTarget, ...] = ()
    runner: SignalPlanRunner | None = None
    logical_exit: SignalPlanLogicalExit | None = None
    related_position_lineage_id: UUID | None = None
    opening_signal_plan_id: UUID | None = None
    supersedes_signal_plan_id: UUID | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    published_at: datetime | None = None
    reason: str = "signal_plan_created"
    feature_snapshot: JsonDict = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def reject_account_execution_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {
                "account_id",
                "broker_account_id",
                "qty",
                "quantity",
                "shares",
                "notional",
                "resolved_quantity",
                "final_quantity",
                "order_id",
                "client_order_id",
                "broker_order_id",
                "governor_approved",
                "approved",
            }
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"signal plan cannot contain account execution fields: {sorted(present)}")
        return data

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "SignalPlan":
        normalized_symbol = self.symbol.upper()
        if normalized_symbol != self.symbol:
            raise ValueError("signal plan symbol must be uppercase")
        if self.intent == SignalPlanIntent.OPEN and self.opening_signal_plan_id is not None:
            raise ValueError("opening signal plan cannot reference opening_signal_plan_id")
        if self.intent != SignalPlanIntent.OPEN and self.opening_signal_plan_id is None and self.related_position_lineage_id is None:
            raise ValueError("position-management signal plan requires opening_signal_plan_id or related_position_lineage_id")
        target_pct = sum(target.quantity_pct for target in self.targets)
        runner_pct = self.runner.quantity_pct if self.runner is not None else 0
        if target_pct + runner_pct > 100:
            raise ValueError("target plus runner quantity percentages cannot exceed 100")
        target_labels = [target.label.strip().casefold() for target in self.targets]
        if len(set(target_labels)) != len(target_labels):
            raise ValueError("signal plan target labels must be unique")
        reserved_leg_labels = {"entry", "stop", "runner"}
        conflicting_labels = sorted(reserved_leg_labels.intersection(target_labels))
        if conflicting_labels:
            raise ValueError(f"signal plan target labels cannot use reserved lifecycle labels: {conflicting_labels}")
        return self


class AccountEvaluationStatus(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    NEEDS_OPERATOR_ATTENTION = "needs_operator_attention"
    DEFERRED = "deferred"
    STALE = "stale"


class AccountParticipationDecision(StrEnum):
    PARTICIPATE = "participate"
    IGNORE = "ignore"
    REJECT = "reject"
    DEFER = "defer"
    REQUIRES_OPERATOR = "requires_operator"


class RiskResolvedLegAllocation(DomainSchema):
    leg_label: str
    lifecycle_intent: SignalPlanIntent
    resolved_quantity: float = Field(gt=0)
    quantity_pct: float | None = Field(default=None, gt=0, le=100)
    source: str = "risk_resolver"


class RiskResolverResult(DomainSchema):
    account_id: UUID
    signal_plan_id: UUID
    allowed: bool
    resolved_quantity: float | None = Field(default=None, gt=0)
    resolved_notional: float | None = Field(default=None, gt=0)
    max_loss: float | None = Field(default=None, ge=0)
    stop_distance: float | None = Field(default=None, ge=0)
    buying_power_required: float | None = Field(default=None, ge=0)
    projected_exposure: float | None = Field(default=None, ge=0)
    projected_concentration: float | None = Field(default=None, ge=0)
    leg_allocations: tuple[RiskResolvedLegAllocation, ...] = ()
    fractional_quantity_allowed: bool | None = None
    quantity_rounding_policy: str | None = None
    existing_position_context: JsonDict = Field(default_factory=dict)
    related_open_orders: tuple[UUID, ...] = ()
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def require_quantity_when_allowed(self) -> "RiskResolverResult":
        if self.allowed and self.resolved_quantity is None and self.resolved_notional is None:
            raise ValueError("allowed risk result requires resolved_quantity or resolved_notional")
        return self


class GovernorDecisionStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    BLOCKED = "blocked"
    DEGRADED = "degraded"
    REQUIRES_OPERATOR = "requires_operator"


class GovernorDecisionTrace(DomainSchema):
    governor_decision_id: UUID
    account_id: UUID
    signal_plan_id: UUID
    status: GovernorDecisionStatus
    approved: bool
    reasons: tuple[str, ...] = ()
    violations: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    evaluated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def approval_matches_status(self) -> "GovernorDecisionTrace":
        if self.approved and self.status != GovernorDecisionStatus.APPROVED:
            raise ValueError("approved governor decision must use approved status")
        if not self.approved and self.status == GovernorDecisionStatus.APPROVED:
            raise ValueError("approved status requires approved=true")
        return self


class AccountSignalPlanEvaluation(DomainSchema):
    evaluation_id: UUID
    account_id: UUID
    signal_plan_id: UUID
    deployment_id: UUID
    strategy_id: UUID
    status: AccountEvaluationStatus
    participation_decision: AccountParticipationDecision
    risk_resolver_result: RiskResolverResult | None = None
    governor_decision: GovernorDecisionTrace | None = None
    created_at: datetime = Field(default_factory=utc_now)
    evaluated_at: datetime | None = None
    rejection_reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class PositionExplanationContext(DomainSchema):
    account_id: UUID
    position_lineage_id: UUID
    symbol: str
    side: SignalPlanSide
    current_quantity: float
    average_entry: float | None = Field(default=None, ge=0)
    current_market_value: float | None = Field(default=None, ge=0)
    unrealized_pnl: float | None = None
    opening_signal_plan_id: UUID
    current_signal_plan_ids: tuple[UUID, ...] = ()
    deployment_id: UUID
    strategy_id: UUID
    account_evaluation_ids: tuple[UUID, ...] = ()
    governor_decision_ids: tuple[UUID, ...] = ()
    order_ids: tuple[UUID, ...] = ()
    fill_ids: tuple[UUID, ...] = ()
    active_stop: JsonDict | None = None
    active_targets: tuple[JsonDict, ...] = ()
    runner_state: JsonDict | None = None
    logical_exit_state: JsonDict | None = None
    sync_state: JsonDict = Field(default_factory=dict)
    unresolved_risks: tuple[str, ...] = ()
    explanation_generated_at: datetime = Field(default_factory=utc_now)

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from ._base import DomainSchema, JsonDict, utc_now


class ConditionOperator(StrEnum):
    GT = "gt"
    GREATER_THAN = "greater_than"
    GTE = "gte"
    LT = "lt"
    LESS_THAN = "less_than"
    LTE = "lte"
    EQ = "eq"
    CROSS_ABOVE = "cross_above"
    CROSS_BELOW = "cross_below"


class CandidateSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class IntentType(StrEnum):
    ENTRY = "entry"
    EXIT = "exit"


class ConditionNode(DomainSchema):
    kind: Literal["condition"] = "condition"
    left_feature: str
    operator: ConditionOperator
    right_feature: str | None = None
    right_value: float | int | str | bool | None = None
    label: str | None = None

    @model_validator(mode="after")
    def require_right_operand(self) -> "ConditionNode":
        if self.right_feature is None and self.right_value is None:
            raise ValueError("condition requires right_feature or right_value")
        if self.right_feature is not None and self.right_value is not None:
            raise ValueError("condition may use right_feature or right_value, not both")
        return self


class ConditionGroup(DomainSchema):
    kind: Literal["group"] = "group"
    operator: Literal["all", "any", "and", "or"]
    children: list[ConditionExpression] = Field(min_length=1)
    label: str | None = None


ConditionExpression = Annotated[ConditionNode | ConditionGroup, Field(discriminator="kind")]
ConditionGroup.model_rebuild()


class LogicalExitRuleKind(StrEnum):
    """Doctrine: ``logical_exit`` is the only exit intent.

    Time-based, bar-count, session, feature, and hybrid exits all map to
    ``SignalPlan.intent = logical_exit`` with the payload's ``rule.kind``
    distinguishing the source. Never add a top-level sibling intent for
    any exit flavor.
    """

    FEATURE_CONDITION = "feature_condition"
    BARS_SINCE_ENTRY = "bars_since_entry"
    TIME_IN_POSITION_SECONDS = "time_in_position_seconds"
    TIME_OF_DAY_ET = "time_of_day_et"
    MINUTES_BEFORE_SESSION_CLOSE = "minutes_before_session_close"
    SESSION_WINDOW = "session_window"
    HYBRID = "hybrid"


def _valid_hhmm(text: str) -> bool:
    parts = text.split(":")
    if len(parts) != 2:
        return False
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
    except ValueError:
        return False
    return 0 <= hours <= 23 and 0 <= minutes <= 59


class LogicalExitRule(DomainSchema):
    """Structured logical-exit payload supporting feature / time / bar / session / hybrid.

    Mutually-exclusive optionals — exactly one kind-specific payload populates
    per ``kind``, except ``HYBRID`` which composes ``children`` with
    ``operator`` ('all' = AND, 'any' = OR).

    Examples:
    - exit after 20 bars → ``kind=BARS_SINCE_ENTRY, bars=20``
    - exit after 30 minutes → ``kind=TIME_IN_POSITION_SECONDS, seconds=1800``
    - exit at 15:55 ET → ``kind=TIME_OF_DAY_ET, time_of_day_et='15:55'``
    - exit 5 min before close → ``kind=MINUTES_BEFORE_SESSION_CLOSE, minutes_before_close=5``
    - exit when RSI crosses below EMA → ``kind=FEATURE_CONDITION, feature_condition=<tree>``
    - reduce 50% after 15 minutes → ``kind=TIME_IN_POSITION_SECONDS, seconds=900``
      paired with ``SignalPlanLogicalExit.action=reduce, quantity_pct=50``
    """

    kind: LogicalExitRuleKind
    feature_condition: ConditionNode | ConditionGroup | None = None
    bars: int | None = Field(default=None, gt=0)
    seconds: int | None = Field(default=None, gt=0)
    time_of_day_et: str | None = None
    minutes_before_close: int | None = Field(default=None, gt=0)
    session: Literal["regular", "extended", "premarket", "afterhours"] | None = None
    children: tuple["LogicalExitRule", ...] = ()
    operator: Literal["all", "any"] | None = None
    label: str | None = None

    @model_validator(mode="after")
    def validate_kind_payload(self) -> "LogicalExitRule":
        kind = self.kind
        if kind == LogicalExitRuleKind.FEATURE_CONDITION:
            if self.feature_condition is None:
                raise ValueError("feature_condition kind requires feature_condition payload")
        elif kind == LogicalExitRuleKind.BARS_SINCE_ENTRY:
            if self.bars is None:
                raise ValueError("bars_since_entry kind requires bars > 0")
        elif kind == LogicalExitRuleKind.TIME_IN_POSITION_SECONDS:
            if self.seconds is None:
                raise ValueError("time_in_position_seconds kind requires seconds > 0")
        elif kind == LogicalExitRuleKind.TIME_OF_DAY_ET:
            if not self.time_of_day_et:
                raise ValueError("time_of_day_et kind requires time_of_day_et 'HH:MM'")
            if not _valid_hhmm(self.time_of_day_et):
                raise ValueError("time_of_day_et must be 'HH:MM' (24h)")
        elif kind == LogicalExitRuleKind.MINUTES_BEFORE_SESSION_CLOSE:
            if self.minutes_before_close is None:
                raise ValueError(
                    "minutes_before_session_close kind requires minutes_before_close > 0"
                )
        elif kind == LogicalExitRuleKind.SESSION_WINDOW:
            if self.session is None:
                raise ValueError("session_window kind requires session value")
        elif kind == LogicalExitRuleKind.HYBRID:
            if not self.children:
                raise ValueError("hybrid kind requires children")
            if self.operator not in {"all", "any"}:
                raise ValueError("hybrid kind requires operator 'all' or 'any'")
        return self


LogicalExitRule.model_rebuild()


class SignalRule(DomainSchema):
    """A strategy rule that emits a CandidateTradeIntent when its condition fires.

    Doctrine: ``logical_exit`` is the only exit intent. Time / bar / session /
    feature / hybrid exits all map under it. For exit rules that depend on
    position age, bars-since-entry, time-of-day, session windows, or hybrid
    of those with feature conditions, attach a typed ``logical_exit_rule``.
    Pure feature-condition exits keep using ``condition`` only.
    """

    name: str
    side: CandidateSide
    intent_type: IntentType
    condition: ConditionExpression | None = None
    logical_exit_rule: LogicalExitRule | None = None
    stop_candidate_feature: str | None = None
    target_candidate_feature: str | None = None

    @model_validator(mode="after")
    def require_at_least_one_evaluator(self) -> "SignalRule":
        if self.condition is None and self.logical_exit_rule is None:
            raise ValueError(
                "signal rule requires at least one of: condition, logical_exit_rule"
            )
        if self.intent_type == IntentType.ENTRY and self.logical_exit_rule is not None:
            raise ValueError("entry rules cannot carry logical_exit_rule")
        return self


class StrategyVersion(DomainSchema):
    id: UUID
    strategy_id: UUID
    version: int = Field(ge=1)
    name: str
    description: str | None = None
    feature_refs: list[str] = Field(default_factory=list)
    entry_rules: list[SignalRule] = Field(default_factory=list)
    exit_rules: list[SignalRule] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def reject_runtime_ownership_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {
                "account_id",
                "account_ids",
                "account_risk",
                "broker_account_id",
                "buying_power",
                "deployment_id",
                "execution_policy",
                "max_loss",
                "position_size",
                "position_sizing",
                "risk",
                "risk_per_trade_pct",
                "risk_profile_id",
                "risk_profile_version_id",
                "risk_settings",
                "runtime_overrides",
                "runtime_state",
                "sizing_method",
                "symbol_list",
                "symbols",
                "universe",
                "universe_id",
                "universe_snapshot_id",
                "watchlist",
                "watchlist_id",
                "watchlist_ids",
            }
            present = forbidden.intersection(data)
            if present:
                raise ValueError(
                    "strategy version cannot own risk, account, universe, watchlist, "
                    f"or runtime fields: {sorted(present)}"
                )
        return data

    @model_validator(mode="after")
    def require_signal_rules(self) -> "StrategyVersion":
        if not self.entry_rules and not self.exit_rules:
            raise ValueError("strategy version requires at least one entry or exit rule")
        return self


class CandidateTradeIntent(DomainSchema):
    timestamp: datetime
    symbol: str
    side: CandidateSide
    intent_type: IntentType
    signal_name: str
    reason: str = "signal_condition_true"
    feature_values_used: JsonDict = Field(default_factory=dict)
    stop_candidate: float | None = None
    target_candidate: float | None = None
    diagnostics: JsonDict = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def reject_execution_fields(cls, data: object) -> object:
        if isinstance(data, dict):
            forbidden = {
                "qty",
                "quantity",
                "order_type",
                "time_in_force",
                "broker_account_id",
                "approval_status",
                "approved",
            }
            present = forbidden.intersection(data)
            if present:
                raise ValueError(f"candidate trade intent cannot contain execution fields: {sorted(present)}")
        return data

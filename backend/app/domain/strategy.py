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


class SignalRule(DomainSchema):
    name: str
    side: CandidateSide
    intent_type: IntentType
    condition: ConditionExpression
    stop_candidate_feature: str | None = None
    target_candidate_feature: str | None = None


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

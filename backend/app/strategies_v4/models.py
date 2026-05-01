"""Draft input models for StrategyVersion v4.

StrategyVersionV4Draft contains only the operator-editable fields.
Derived fields (id, strategy_v4_id, version, created_at, feature_requirements,
validation_status) are computed at save time.
"""
from __future__ import annotations

import math
import re
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_ALIAS_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_ALIAS_VALUE_RE = re.compile(r"^\d+[mhdw]$")


class StrategyIdentityV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[str] = Field(default_factory=list)
    direction: Literal["long", "short", "both"] = "both"


class StrategyEntryV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expression_text: str


class StrategyEntriesV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    long: StrategyEntryV4Draft | None = None
    short: StrategyEntryV4Draft | None = None

    @model_validator(mode="after")
    def at_least_one(self) -> "StrategyEntriesV4Draft":
        if self.long is None and self.short is None:
            raise ValueError("at least one of entries.long or entries.short must be set")
        return self


class StrategyVariableV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(pattern=r"^[a-z_][a-z0-9_]*$")
    expression_text: str
    kind: Literal["expression", "timeframe"] = "expression"


class OnFillActionV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["be_exact", "be_plus", "be_minus", "tighten_atr", "tighten_pct", "leave"]
    offset_value: float | None = None

    @model_validator(mode="after")
    def validate_offset(self) -> "OnFillActionV4Draft":
        needs_offset = {"be_plus", "be_minus", "tighten_atr", "tighten_pct"}
        no_offset = {"be_exact", "leave"}
        if self.kind in needs_offset and self.offset_value is None:
            raise ValueError(f"offset_value required for on_fill_action.kind='{self.kind}'")
        if self.kind in no_offset and self.offset_value is not None:
            raise ValueError(f"offset_value must be None for on_fill_action.kind='{self.kind}'")
        return self


class StrategyStopV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    mode: Literal["simple", "expression"]
    scope: str = "all"
    simple_type: Literal["%", "ATR", "$", "R"] | None = None
    simple_value: float | None = None
    expression_text: str | None = None
    # Client-only cache from Monaco validate; overwritten at save — must be accepted on POST body.
    feature_requirements: list[str] | None = None

    @model_validator(mode="after")
    def validate_stop_mode(self) -> "StrategyStopV4Draft":
        if self.mode == "simple":
            if self.simple_type is None:
                raise ValueError("simple_type required when mode='simple'")
            if self.simple_value is None:
                raise ValueError("simple_value required when mode='simple'")
        elif self.mode == "expression":
            if self.expression_text is None:
                raise ValueError("expression_text required when mode='expression'")
        return self


class StrategyLegV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    position: int = Field(ge=1)
    kind: Literal["target", "runner"]
    size_pct: float = Field(gt=0.0, le=1.0)
    target_type: Literal["%", "ATR", "$", "R", "feature", "trail-ATR", "trail-%", "trail-$"]
    target_value: float | None = None
    on_fill_action: OnFillActionV4Draft


class StrategyLogicalExitV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID = Field(default_factory=uuid4)
    template_id: Literal["no_progress", "opposite_cross", "session_end", "bars_since"]
    params: dict[str, Any] = Field(default_factory=dict)


class StrategyLogicalExitsV4Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    long: list[StrategyLogicalExitV4Draft] = Field(default_factory=list)
    short: list[StrategyLogicalExitV4Draft] = Field(default_factory=list)


class StrategyVersionV4Draft(BaseModel):
    """Operator-supplied fields. id/version/created_at/feature_requirements are derived."""
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    identity: StrategyIdentityV4Draft = Field(default_factory=StrategyIdentityV4Draft)
    default_strategy_controls_version_id: UUID | None = None
    default_execution_plan_version_id: UUID | None = None

    timeframe_aliases: dict[str, str] = Field(default_factory=dict)

    variables: list[StrategyVariableV4Draft] = Field(default_factory=list)
    entries: StrategyEntriesV4Draft
    stops: list[StrategyStopV4Draft]
    legs: list[StrategyLegV4Draft] = Field(default_factory=list)
    logical_exits: StrategyLogicalExitsV4Draft = Field(
        default_factory=StrategyLogicalExitsV4Draft
    )

    @field_validator("timeframe_aliases")
    @classmethod
    def validate_timeframe_aliases(cls, v: dict[str, str]) -> dict[str, str]:
        for key, value in v.items():
            if not _ALIAS_KEY_RE.match(key):
                raise ValueError(
                    f"timeframe_aliases key '{key}' must match ^[a-z_][a-z0-9_]*$"
                )
            if not _ALIAS_VALUE_RE.match(value):
                raise ValueError(
                    f"timeframe_aliases value '{value}' for key '{key}' must match ^\\d+[mhdw]$"
                )
        return v

    @model_validator(mode="after")
    def validate_stops_nonempty(self) -> "StrategyVersionV4Draft":
        if len(self.stops) == 0:
            raise ValueError("at least one stop is required")
        return self

    @model_validator(mode="after")
    def validate_legs(self) -> "StrategyVersionV4Draft":
        if len(self.legs) == 0:
            return self
        legs = sorted(self.legs, key=lambda l: l.position)
        for idx, leg in enumerate(legs, start=1):
            if leg.position != idx:
                raise ValueError(
                    f"leg positions must be contiguous 1..N; position {idx} missing"
                )
        runners = [l for l in legs if l.kind == "runner"]
        if len(runners) > 1:
            raise ValueError("at most one runner leg allowed")
        total = sum(l.size_pct for l in legs)
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(f"sum of leg size_pct must equal 1.0 (got {total})")
        return self

    @model_validator(mode="after")
    def validate_variable_names_unique(self) -> "StrategyVersionV4Draft":
        names = [v.name for v in self.variables]
        if len(names) != len(set(names)):
            seen: set[str] = set()
            for n in names:
                if n in seen:
                    raise ValueError(f"variable name '{n}' appears more than once")
                seen.add(n)
        return self

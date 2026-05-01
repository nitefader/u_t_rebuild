"""Domain models for StrategyVersion v4.

Lives alongside (but never modifies) the legacy strategy.py domain.
All v4 types use the _v4 suffix or live under this module.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from ._base import DomainSchema

_ALIAS_KEY_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
_ALIAS_VALUE_RE = re.compile(r"^\d+[mhdw]$")


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class ValidationStatusV4(DomainSchema):
    valid: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


class StrategyVariableV4(DomainSchema):
    name: str = Field(pattern=r"^[a-z_][a-z0-9_]*$")
    expression_text: str
    kind: Literal["expression", "timeframe"] = "expression"
    feature_requirements: tuple[str, ...] = ()


class StrategyEntryV4(DomainSchema):
    expression_text: str
    feature_requirements: tuple[str, ...] = ()


class StrategyEntriesV4(DomainSchema):
    long: StrategyEntryV4 | None = None
    short: StrategyEntryV4 | None = None

    @model_validator(mode="after")
    def at_least_one_entry(self) -> "StrategyEntriesV4":
        if self.long is None and self.short is None:
            raise ValueError("at least one of entries.long or entries.short must be set")
        return self


class StrategyStopV4(DomainSchema):
    id: UUID = Field(default_factory=uuid4)
    mode: Literal["simple", "expression"]
    scope: str = "all"  # 'all' or 'leg-N'
    simple_type: Literal["%", "ATR", "$", "R"] | None = None
    simple_value: float | None = None
    expression_text: str | None = None
    feature_requirements: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_stop_mode(self) -> "StrategyStopV4":
        if self.mode == "simple":
            if self.simple_type is None:
                raise ValueError("simple_type required when mode='simple'")
            if self.simple_value is None:
                raise ValueError("simple_value required when mode='simple'")
        elif self.mode == "expression":
            if self.expression_text is None:
                raise ValueError("expression_text required when mode='expression'")
        return self


class OnFillActionV4(DomainSchema):
    kind: Literal["be_exact", "be_plus", "be_minus", "tighten_atr", "tighten_pct", "leave"]
    offset_value: float | None = None

    @model_validator(mode="after")
    def validate_offset(self) -> "OnFillActionV4":
        needs_offset = {"be_plus", "be_minus", "tighten_atr", "tighten_pct"}
        no_offset = {"be_exact", "leave"}
        if self.kind in needs_offset and self.offset_value is None:
            raise ValueError(f"offset_value required for on_fill_action.kind='{self.kind}'")
        if self.kind in no_offset and self.offset_value is not None:
            raise ValueError(f"offset_value must be None for on_fill_action.kind='{self.kind}'")
        return self


class StrategyLegV4(DomainSchema):
    id: UUID = Field(default_factory=uuid4)
    position: int = Field(ge=1)
    kind: Literal["target", "runner"]
    size_pct: float = Field(gt=0.0, le=1.0)
    target_type: Literal["%", "ATR", "$", "R", "feature", "trail-ATR", "trail-%", "trail-$"]
    target_value: float | None = None
    on_fill_action: OnFillActionV4


class StrategyLogicalExitV4(DomainSchema):
    id: UUID = Field(default_factory=uuid4)
    template_id: Literal["no_progress", "opposite_cross", "session_end", "bars_since"]
    params: dict[str, str | int | float | bool] = Field(default_factory=dict)


class StrategyLogicalExitsV4(DomainSchema):
    long: tuple[StrategyLogicalExitV4, ...] = ()
    short: tuple[StrategyLogicalExitV4, ...] = ()


class StrategyIdentityV4(DomainSchema):
    tags: tuple[str, ...] = ()
    direction: Literal["long", "short", "both"] = "both"


# ---------------------------------------------------------------------------
# Root domain model
# ---------------------------------------------------------------------------

class StrategyVersionV4(DomainSchema):
    id: UUID = Field(default_factory=uuid4)
    strategy_v4_id: UUID = Field(default_factory=uuid4)
    version: int = Field(ge=1)
    name: str
    description: str | None = None
    identity: StrategyIdentityV4 = Field(default_factory=StrategyIdentityV4)
    default_strategy_controls_version_id: UUID | None = None
    default_execution_plan_version_id: UUID | None = None

    timeframe_aliases: dict[str, str] = Field(default_factory=dict)

    variables: tuple[StrategyVariableV4, ...] = ()
    entries: StrategyEntriesV4
    stops: tuple[StrategyStopV4, ...]
    legs: tuple[StrategyLegV4, ...]
    logical_exits: StrategyLogicalExitsV4 = Field(default_factory=StrategyLogicalExitsV4)

    feature_requirements: tuple[str, ...] = ()
    validation_status: ValidationStatusV4 = Field(
        default_factory=lambda: ValidationStatusV4(valid=True)
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    def validate_stops_nonempty(self) -> "StrategyVersionV4":
        if len(self.stops) == 0:
            raise ValueError("at least one stop is required")
        return self

    @model_validator(mode="after")
    def validate_legs(self) -> "StrategyVersionV4":
        if len(self.legs) == 0:
            return self  # legs may be empty during draft construction
        legs = sorted(self.legs, key=lambda l: l.position)
        # positions must be contiguous 1..N
        for idx, leg in enumerate(legs, start=1):
            if leg.position != idx:
                raise ValueError(
                    f"leg positions must be contiguous 1..N; position {idx} missing"
                )
        # at most one runner
        runners = [l for l in legs if l.kind == "runner"]
        if len(runners) > 1:
            raise ValueError("at most one runner leg allowed")
        # sum of size_pct == 1.0
        total = sum(l.size_pct for l in legs)
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"sum of leg size_pct must equal 1.0 (got {total})"
            )
        return self

    @model_validator(mode="after")
    def validate_variable_names_unique(self) -> "StrategyVersionV4":
        names = [v.name for v in self.variables]
        if len(names) != len(set(names)):
            seen: set[str] = set()
            for n in names:
                if n in seen:
                    raise ValueError(f"variable name '{n}' appears more than once")
                seen.add(n)
        return self

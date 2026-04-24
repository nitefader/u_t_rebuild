from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import (
    ConditionGroup,
    ConditionNode,
    ExecutionStyleVersion,
    ProgramVersion,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    UniverseSnapshot,
)

from .key import make_feature_key
from .parser import parse_feature_expression
from .registry import FeatureRegistry, registry
from .spec import FeatureSpec, FeatureValidationError


class FeaturePlanError(ValueError):
    """Raised when feature planning cannot produce a valid all-or-nothing plan."""


class FeaturePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    program_version_id: UUID
    consumer: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    feature_specs: tuple[FeatureSpec, ...]
    feature_keys: tuple[str, ...]
    warmup_by_timeframe: dict[str, int]


class ResolvedProgramComponents(BaseModel):
    """Resolved component set for a reference-only ProgramVersion."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    program: ProgramVersion
    strategy: StrategyVersion
    strategy_controls: StrategyControlsVersion
    risk_profile: RiskProfileVersion
    execution_style: ExecutionStyleVersion
    universe: UniverseSnapshot

    @model_validator(mode="after")
    def validate_references_match_program(self) -> "ResolvedProgramComponents":
        mismatches: list[str] = []
        if self.program.strategy_version_id != self.strategy.id:
            mismatches.append("strategy_version_id")
        if self.program.strategy_controls_version_id != self.strategy_controls.id:
            mismatches.append("strategy_controls_version_id")
        if self.program.risk_profile_version_id != self.risk_profile.id:
            mismatches.append("risk_profile_version_id")
        if self.program.execution_style_version_id != self.execution_style.id:
            mismatches.append("execution_style_version_id")
        if self.program.universe_snapshot_id != self.universe.id:
            mismatches.append("universe_snapshot_id")
        if mismatches:
            raise ValueError(f"resolved components do not match program references: {mismatches}")
        return self


def _condition_feature_refs(condition: ConditionNode | ConditionGroup) -> Iterable[str]:
    if isinstance(condition, ConditionNode):
        yield condition.left_feature
        if condition.right_feature is not None:
            yield condition.right_feature
        return
    for child in condition.children:
        yield from _condition_feature_refs(child)


def _strategy_feature_refs(strategy: StrategyVersion) -> Iterable[str]:
    yield from strategy.feature_refs
    for rule in [*strategy.entry_rules, *strategy.exit_rules]:
        yield from _condition_feature_refs(rule.condition)
        if rule.stop_candidate_feature is not None:
            yield rule.stop_candidate_feature
        if rule.target_candidate_feature is not None:
            yield rule.target_candidate_feature


def collect_feature_refs(components: ResolvedProgramComponents) -> list[str]:
    refs: list[str] = []
    refs.extend(_strategy_feature_refs(components.strategy))
    refs.extend(components.strategy_controls.feature_refs)
    refs.extend(components.strategy_controls.regime_filter_refs)
    refs.extend(components.risk_profile.feature_refs)
    refs.extend(components.execution_style.feature_refs)
    return refs


def build_feature_plan(
    components: ResolvedProgramComponents,
    *,
    consumer: str,
    feature_registry: FeatureRegistry = registry,
) -> FeaturePlan:
    specs_by_key: dict[str, FeatureSpec] = {}
    errors: list[str] = []

    for feature_ref in collect_feature_refs(components):
        try:
            spec = parse_feature_expression(feature_ref, feature_registry)
            feature_registry.require_consumer_support(spec.kind, consumer)
            specs_by_key.setdefault(make_feature_key(spec), spec)
        except (FeatureValidationError, ValueError) as exc:
            errors.append(f"{feature_ref}: {exc}")

    if errors:
        raise FeaturePlanError(f"feature planning failed: {errors}")

    feature_keys = tuple(sorted(specs_by_key))
    feature_specs = tuple(specs_by_key[key] for key in feature_keys)
    timeframes = tuple(sorted({spec.timeframe for spec in feature_specs}))
    symbols = tuple(sorted({item.symbol.upper() for item in components.universe.symbols}))
    warmup_by_timeframe: dict[str, int] = {}
    for spec in feature_specs:
        warmup_by_timeframe[spec.timeframe] = max(
            warmup_by_timeframe.get(spec.timeframe, 0),
            feature_registry.warmup_bars(spec),
        )

    return FeaturePlan(
        program_version_id=components.program.id,
        consumer=consumer,
        symbols=symbols,
        timeframes=timeframes,
        feature_specs=feature_specs,
        feature_keys=feature_keys,
        warmup_by_timeframe=warmup_by_timeframe,
    )

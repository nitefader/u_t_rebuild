from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.domain import (
    ConditionGroup,
    ConditionNode,
    ExecutionStyleVersion,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    UniverseSnapshot,
)

from .key import make_feature_key
from .parser import parse_feature_expression
from .registry import FeatureRegistry, FeatureRegistryEntry, registry
from .spec import FeatureSpec, FeatureValidationError


# ---------------------------------------------------------------------------
# Per-FeatureKey data requirements (Phase 1 §11 deliverable 1)
# ---------------------------------------------------------------------------

INTRADAY_TIMEFRAMES = frozenset({"1m", "5m", "15m", "30m", "1h", "4h"})

# Consumer → data requirement projection. Used to translate a FeatureSpec +
# Program consumer into a per-FeatureKey ``FeatureDataRequirement`` so the
# resolver can pick a pipeline per FeatureKey instead of per Deployment.
_LIVE_CONSUMERS = frozenset({"live", "runtime", "paper", "sim_stream"})
_HISTORICAL_CONSUMERS = frozenset({"backtest", "sim_replay", "optimization", "walk_forward"})
_INSPECTION_CONSUMERS = frozenset({"chart_lab"})
_PORTFOLIO_CONSUMERS = frozenset({"portfolio_governor"})


class FeaturePlanError(ValueError):
    """Raised when feature planning cannot produce a valid all-or-nothing plan."""


class FeatureDataRequirement(BaseModel):
    """Per-FeatureKey data demand projection.

    Computed at plan-build time from ``(FeatureSpec, consumer, registry entry)``.
    Consumed by the resolver / FeatureEngine subscription manager to pick a
    pipeline per FeatureKey (not per Deployment) — multiple FeatureKeys in the
    same Deployment may resolve to different pipelines.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_key: str
    timeframe: str
    instrument_class: str
    requires_streaming: bool
    requires_realtime: bool
    requires_intraday: bool
    requires_historical: bool
    requires_long_range_history: bool
    warmup_bars: int


class FeaturePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    strategy_version_id: UUID
    consumer: str
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    feature_specs: tuple[FeatureSpec, ...]
    feature_keys: tuple[str, ...]
    warmup_by_timeframe: dict[str, int]
    data_requirements: tuple[FeatureDataRequirement, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_program_version_id(cls, data: object) -> object:
        if isinstance(data, dict):
            migrated = dict(data)
            if "program_version_id" in migrated and "strategy_version_id" not in migrated:
                migrated["strategy_version_id"] = migrated.pop("program_version_id")
            return migrated
        return data


class ResolvedDeploymentComponents(BaseModel):
    """Resolved reusable components selected by a Deployment."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    strategy: StrategyVersion
    strategy_controls: StrategyControlsVersion
    risk_profile: RiskProfileVersion
    execution_style: ExecutionStyleVersion
    universe: UniverseSnapshot

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_program_component(cls, data: object) -> object:
        if isinstance(data, dict):
            migrated = dict(data)
            legacy_program = migrated.pop("program", None)
            if legacy_program is not None:
                mismatches: list[str] = []
                if getattr(legacy_program, "strategy_version_id", None) != getattr(migrated.get("strategy"), "id", None):
                    mismatches.append("strategy_version_id")
                if getattr(legacy_program, "strategy_controls_version_id", None) != getattr(
                    migrated.get("strategy_controls"), "id", None
                ):
                    mismatches.append("strategy_controls_version_id")
                if getattr(legacy_program, "risk_profile_version_id", None) != getattr(migrated.get("risk_profile"), "id", None):
                    mismatches.append("risk_profile_version_id")
                if getattr(legacy_program, "execution_style_version_id", None) != getattr(
                    migrated.get("execution_style"), "id", None
                ):
                    mismatches.append("execution_style_version_id")
                if getattr(legacy_program, "universe_snapshot_id", None) != getattr(migrated.get("universe"), "id", None):
                    mismatches.append("universe_snapshot_id")
                if mismatches:
                    raise ValueError(f"resolved components do not match legacy program references: {mismatches}")
            return migrated
        return data

    @model_validator(mode="after")
    def validate_reusable_component_boundaries(self) -> "ResolvedDeploymentComponents":
        mismatches: list[str] = []
        if hasattr(self.strategy, "risk_profile_version_id"):
            mismatches.append("strategy_version_risk_profile_version_id")
        if hasattr(self.universe, "risk_profile_version_id"):
            mismatches.append("universe_risk_profile_version_id")
        if mismatches:
            raise ValueError(f"reusable component boundary violation: {mismatches}")
        return self


def _condition_feature_refs(condition: ConditionNode | ConditionGroup | None) -> Iterable[str]:
    if condition is None:
        return
    if isinstance(condition, ConditionNode):
        yield condition.left_feature
        if condition.right_feature is not None:
            yield condition.right_feature
        return
    for child in condition.children:
        yield from _condition_feature_refs(child)


def _logical_exit_feature_refs(rule: object) -> Iterable[str]:
    """Recursively pull feature refs out of a LogicalExitRule tree.

    Time / bar / session / clock kinds carry no feature refs. FEATURE_CONDITION
    and HYBRID kinds may. Doctrine: ``logical_exit`` is the only exit intent;
    feature lookups embedded inside it must still join the FeaturePlan so the
    spine has the values at evaluation time.
    """
    if rule is None:
        return
    feature_condition = getattr(rule, "feature_condition", None)
    if feature_condition is not None:
        yield from _condition_feature_refs(feature_condition)
    children = getattr(rule, "children", ())
    for child in children:
        yield from _logical_exit_feature_refs(child)


def _strategy_feature_refs(strategy: StrategyVersion) -> Iterable[str]:
    yield from strategy.feature_refs
    for rule in [*strategy.entry_rules, *strategy.exit_rules]:
        yield from _condition_feature_refs(rule.condition)
        yield from _logical_exit_feature_refs(rule.logical_exit_rule)
        if rule.stop_candidate_feature is not None:
            yield rule.stop_candidate_feature
        if rule.target_candidate_feature is not None:
            yield rule.target_candidate_feature


def collect_feature_refs(components: ResolvedDeploymentComponents) -> list[str]:
    refs: list[str] = []
    refs.extend(_strategy_feature_refs(components.strategy))
    refs.extend(components.strategy_controls.feature_refs)
    refs.extend(components.strategy_controls.regime_filter_refs)
    refs.extend(components.risk_profile.feature_refs)
    refs.extend(components.execution_style.feature_refs)
    return refs


def build_feature_plan(
    components: ResolvedDeploymentComponents,
    *,
    consumer: str,
    feature_registry: FeatureRegistry = registry,
) -> FeaturePlan:
    return _build_plan(
        strategy_version_id=components.strategy.id,
        feature_refs=collect_feature_refs(components),
        symbols=tuple(sorted({item.symbol.upper() for item in components.universe.symbols})),
        default_timeframe=components.strategy_controls.timeframe,
        consumer=consumer,
        feature_registry=feature_registry,
    )


def build_strategy_only_feature_plan(
    strategy: StrategyVersion,
    *,
    default_timeframe: str,
    consumer: str = "chart_lab",
    feature_registry: FeatureRegistry = registry,
) -> FeaturePlan:
    """Build a FeaturePlan from a StrategyVersion alone — no Deployment needed.

    Used by Chart Lab strategy-preview: the operator picks any saved Strategy
    (any version, including drafts) and we derive its features without binding
    a Watchlist / RiskProfile / ExecutionStyle. Symbol is supplied at preview
    time, not by a UniverseSnapshot, so ``symbols`` on the returned plan is
    intentionally empty — the caller passes the chosen symbol into the
    feature engine separately.
    """
    return _build_plan(
        strategy_version_id=strategy.id,
        feature_refs=list(_strategy_feature_refs(strategy)),
        symbols=(),
        default_timeframe=default_timeframe,
        consumer=consumer,
        feature_registry=feature_registry,
    )


def _build_plan(
    *,
    strategy_version_id: UUID,
    feature_refs: Iterable[str],
    symbols: tuple[str, ...],
    default_timeframe: str,
    consumer: str,
    feature_registry: FeatureRegistry,
) -> FeaturePlan:
    specs_by_key: dict[str, FeatureSpec] = {}
    errors: list[str] = []

    for feature_ref in feature_refs:
        try:
            spec = parse_feature_expression(
                feature_ref,
                feature_registry,
                default_timeframe=default_timeframe,
            )
            feature_registry.require_consumer_support(spec.kind, consumer)
            specs_by_key.setdefault(make_feature_key(spec), spec)
        except (FeatureValidationError, ValueError) as exc:
            errors.append(f"{feature_ref}: {exc}")

    if errors:
        raise FeaturePlanError(f"feature planning failed: {errors}")

    feature_keys = tuple(sorted(specs_by_key))
    feature_specs = tuple(specs_by_key[key] for key in feature_keys)
    timeframes = tuple(sorted({spec.timeframe for spec in feature_specs}))
    warmup_by_timeframe: dict[str, int] = {}
    for spec in feature_specs:
        warmup_by_timeframe[spec.timeframe] = max(
            warmup_by_timeframe.get(spec.timeframe, 0),
            feature_registry.warmup_bars(spec),
        )

    data_requirements = tuple(
        _build_data_requirement(
            feature_key=feature_keys[index],
            spec=feature_specs[index],
            consumer=consumer,
            entry=feature_registry.get(feature_specs[index].kind),
            warmup_bars=feature_registry.warmup_bars(feature_specs[index]),
        )
        for index in range(len(feature_keys))
    )

    return FeaturePlan(
        strategy_version_id=strategy_version_id,
        consumer=consumer,
        symbols=symbols,
        timeframes=timeframes,
        feature_specs=feature_specs,
        feature_keys=feature_keys,
        warmup_by_timeframe=warmup_by_timeframe,
        data_requirements=data_requirements,
    )


def _build_data_requirement(
    *,
    feature_key: str,
    spec: FeatureSpec,
    consumer: str,
    entry: FeatureRegistryEntry,
    warmup_bars: int,
) -> FeatureDataRequirement:
    is_portfolio_feature = entry.instrument_class == "portfolio_state"
    is_live_consumer = consumer in _LIVE_CONSUMERS
    is_historical_consumer = consumer in _HISTORICAL_CONSUMERS
    is_inspection_consumer = consumer in _INSPECTION_CONSUMERS

    # Portfolio features operate on internal portfolio state — no streaming or
    # historical market-data subscription is implied.
    if is_portfolio_feature:
        return FeatureDataRequirement(
            feature_key=feature_key,
            timeframe=spec.timeframe,
            instrument_class=entry.instrument_class,
            requires_streaming=False,
            requires_realtime=False,
            requires_intraday=False,
            requires_historical=False,
            requires_long_range_history=False,
            warmup_bars=warmup_bars,
        )

    requires_streaming = is_live_consumer
    requires_realtime = is_live_consumer
    requires_intraday = spec.timeframe in INTRADAY_TIMEFRAMES
    requires_historical = is_historical_consumer or is_inspection_consumer
    requires_long_range_history = (
        is_historical_consumer
        and spec.timeframe in {"1d", "1w", "1mo"}
    )

    return FeatureDataRequirement(
        feature_key=feature_key,
        timeframe=spec.timeframe,
        instrument_class=entry.instrument_class,
        requires_streaming=requires_streaming,
        requires_realtime=requires_realtime,
        requires_intraday=requires_intraday,
        requires_historical=requires_historical,
        requires_long_range_history=requires_long_range_history,
        warmup_bars=warmup_bars,
    )

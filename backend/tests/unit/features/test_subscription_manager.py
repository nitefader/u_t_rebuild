from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.domain import (
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import CandidateSide, IntentType, SignalRule
from backend.app.features import (
    FeaturePlan,
    ResolvedProgramComponents,
    SubscriptionDelta,
    SubscriptionEntry,
    SubscriptionManager,
    build_feature_plan,
)


def _components(refs: list[str]) -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    condition = ConditionNode(left_feature=refs[0], operator=ConditionOperator.GT, right_feature=refs[0])
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="S",
        feature_refs=refs,
        entry_rules=[
            SignalRule(name="entry", side=CandidateSide.LONG, intent_type=IntentType.ENTRY, condition=condition)
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id, strategy_controls_id=uuid4(), version=1, name="C", timeframe="5m"
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="R",
        sizing_method=PositionSizingMethod.RISK_PERCENT_EQUITY,
        risk_per_trade_pct=0.5,
    )
    execution = ExecutionStyleVersion(
        id=execution_id, execution_style_id=uuid4(), version=1, name="E", entry_order_type=OrderType.MARKET
    )
    universe = UniverseSnapshot(
        id=universe_id, universe_id=uuid4(), version=1, name="U", symbols=[UniverseSymbol(symbol="SPY")]
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="P",
        version=1,
        strategy_version_id=strategy_id,
        strategy_controls_version_id=controls_id,
        risk_profile_version_id=risk_id,
        execution_style_version_id=execution_id,
        universe_snapshot_id=universe_id,
    )
    return ResolvedProgramComponents(
        program=program,
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _plan(refs: list[str], consumer: str = "paper") -> FeaturePlan:
    return build_feature_plan(_components(refs), consumer=consumer)


def _const_resolver(pipeline_id: str | None = "pipeline-default"):
    return lambda spec, key: pipeline_id


def _per_timeframe_resolver(mapping: dict[str, str | None]):
    def _resolve(spec, key):
        return mapping.get(spec.timeframe)
    return _resolve


# ---------------------------------------------------------------------------
# Dedup at FeatureKey level
# ---------------------------------------------------------------------------


def test_two_deployments_needing_same_feature_key_subscribe_once() -> None:
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]"])

    d1 = uuid4()
    d2 = uuid4()
    delta1 = mgr.register_plan(d1, plan, _const_resolver())
    delta2 = mgr.register_plan(d2, plan, _const_resolver())

    # First Deployment created the subscriptions.
    assert {change.feature_key for change in delta1.added} == set(plan.feature_keys)
    # Second Deployment attached as a consumer; no new subscriptions.
    assert delta2.added == ()
    assert {change.feature_key for change in delta2.unchanged} == set(plan.feature_keys)
    for feature_key in plan.feature_keys:
        assert mgr.consumer_count(feature_key) == 2


def test_dedup_is_at_feature_key_level_not_symbol_level() -> None:
    """FeatureKey carries timeframe + params; symbol is universe-level. Two
    Deployments with overlapping FeatureKeys share subscriptions even though
    other parts of their plans differ.
    """
    mgr = SubscriptionManager()
    plan_a = _plan(["5m.close[0]", "5m.ema:length=20[0]"])
    plan_b = _plan(["5m.close[0]"])  # subset overlap

    a = uuid4()
    b = uuid4()
    delta_a = mgr.register_plan(a, plan_a, _const_resolver())
    delta_b = mgr.register_plan(b, plan_b, _const_resolver())

    shared_keys = set(plan_a.feature_keys) & set(plan_b.feature_keys)
    a_only_keys = set(plan_a.feature_keys) - set(plan_b.feature_keys)

    # B should not have added any new subscriptions for the shared keys.
    assert {change.feature_key for change in delta_b.added}.isdisjoint(shared_keys)

    for shared_key in shared_keys:
        assert mgr.consumer_count(shared_key) == 2
    for a_only_key in a_only_keys:
        assert mgr.consumer_count(a_only_key) == 1


# ---------------------------------------------------------------------------
# Unregister lifecycle
# ---------------------------------------------------------------------------


def test_unregister_one_consumer_keeps_subscription_when_others_remain() -> None:
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]"])
    a = uuid4()
    b = uuid4()
    mgr.register_plan(a, plan, _const_resolver())
    mgr.register_plan(b, plan, _const_resolver())

    delta = mgr.unregister_plan(a)

    assert delta.removed == ()
    assert {change.feature_key for change in delta.unchanged} == set(plan.feature_keys)
    for feature_key in plan.feature_keys:
        assert mgr.consumer_count(feature_key) == 1
        assert mgr.subscription_for(feature_key) is not None


def test_unregister_last_consumer_removes_subscription() -> None:
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]"])
    deployment = uuid4()
    mgr.register_plan(deployment, plan, _const_resolver())

    delta = mgr.unregister_plan(deployment)

    assert {change.feature_key for change in delta.removed} == set(plan.feature_keys)
    for feature_key in plan.feature_keys:
        assert mgr.subscription_for(feature_key) is None
        assert mgr.consumer_count(feature_key) == 0


def test_unregister_unknown_deployment_is_a_noop() -> None:
    mgr = SubscriptionManager()
    delta = mgr.unregister_plan(uuid4())
    assert delta == SubscriptionDelta()


def test_re_register_with_same_plan_is_idempotent() -> None:
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]"])
    deployment = uuid4()

    first = mgr.register_plan(deployment, plan, _const_resolver())
    second = mgr.register_plan(deployment, plan, _const_resolver("pipeline-other"))

    assert first.added != ()
    assert second.added == ()
    assert second.removed == ()
    # consumer count remains 1 — no double-counting.
    for feature_key in plan.feature_keys:
        assert mgr.consumer_count(feature_key) == 1


def test_re_register_with_different_plan_swaps_subscriptions() -> None:
    mgr = SubscriptionManager()
    deployment = uuid4()
    plan_a = _plan(["5m.close[0]", "5m.ema:length=20[0]"])
    plan_b = _plan(["5m.close[0]"])

    mgr.register_plan(deployment, plan_a, _const_resolver())
    delta = mgr.register_plan(deployment, plan_b, _const_resolver())

    a_only = set(plan_a.feature_keys) - set(plan_b.feature_keys)
    assert {change.feature_key for change in delta.removed} == a_only
    for removed_key in a_only:
        assert mgr.subscription_for(removed_key) is None


# ---------------------------------------------------------------------------
# Pipeline-per-FeatureKey resolution (§I FINAL: "the normal case")
# ---------------------------------------------------------------------------


def test_one_deployment_can_resolve_different_pipelines_per_feature_key() -> None:
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]", "1d.prior_day_high[0]"], consumer="sim_replay")
    resolver = _per_timeframe_resolver({"5m": "alpaca-premium", "1d": "yahoo-historical"})

    deployment = uuid4()
    delta = mgr.register_plan(deployment, plan, resolver)

    pipelines = {change.feature_key: change.pipeline_id for change in delta.added}
    timeframes_by_key = {key: spec.timeframe for key, spec in zip(plan.feature_keys, plan.feature_specs)}
    seen_pipelines = set()
    for feature_key, pipeline_id in pipelines.items():
        if timeframes_by_key[feature_key] == "5m":
            assert pipeline_id == "alpaca-premium"
        if timeframes_by_key[feature_key] == "1d":
            assert pipeline_id == "yahoo-historical"
        seen_pipelines.add(pipeline_id)
    assert "alpaca-premium" in seen_pipelines
    assert "yahoo-historical" in seen_pipelines


def test_unresolved_pipeline_id_is_surfaced_in_delta() -> None:
    """When the pipeline_resolver returns None for a FeatureKey, the entry is
    created with pipeline_id=None and the key is listed in ``unresolved`` so
    operators see what's missing.
    """
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]"])
    deployment = uuid4()

    delta = mgr.register_plan(deployment, plan, _const_resolver(None))

    assert delta.unresolved == plan.feature_keys
    for feature_key in plan.feature_keys:
        entry = mgr.subscription_for(feature_key)
        assert entry is not None
        assert entry.pipeline_id is None


# ---------------------------------------------------------------------------
# Map shape
# ---------------------------------------------------------------------------


def test_subscription_for_returns_frozen_view_with_consumer_set() -> None:
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]"])
    a = uuid4()
    b = uuid4()
    mgr.register_plan(a, plan, _const_resolver())
    mgr.register_plan(b, plan, _const_resolver())

    feature_key = plan.feature_keys[0]
    entry = mgr.subscription_for(feature_key)
    assert isinstance(entry, SubscriptionEntry)
    assert entry.consumer_deployment_ids == frozenset({a, b})
    assert entry.pipeline_id == "pipeline-default"


def test_all_subscriptions_returns_sorted_immutable_view() -> None:
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]", "5m.ema:length=20[0]"])
    mgr.register_plan(uuid4(), plan, _const_resolver())

    subs = mgr.all_subscriptions()
    assert isinstance(subs, tuple)
    assert {s.feature_key for s in subs} == set(plan.feature_keys)
    # Sorted by feature_key for deterministic operator-facing output.
    assert list(subs) == sorted(subs, key=lambda s: s.feature_key)


def test_register_plan_dedups_consumer_count_when_same_deployment_registers_twice_with_same_plan() -> None:
    mgr = SubscriptionManager()
    plan = _plan(["5m.close[0]"])
    deployment = uuid4()
    mgr.register_plan(deployment, plan, _const_resolver())
    mgr.register_plan(deployment, plan, _const_resolver())
    for feature_key in plan.feature_keys:
        assert mgr.consumer_count(feature_key) == 1

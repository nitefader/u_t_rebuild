"""Phase 1 §11 exit-gate evidence.

A Deployment can declare feature demand, resolve a pipeline per FeatureKey,
and attach data demand without any direct provider call:

    FeaturePlanner -> PipelineRegistry -> SubscriptionManager

Two Deployments with overlapping FeaturePlans must share one subscription
per ``FeatureKey``. The same Deployment may resolve different FeatureKeys to
different pipelines (per plan_review §I FINAL).
"""

from __future__ import annotations

from uuid import uuid4

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
    ResolvedProgramComponents,
    SubscriptionManager,
    build_feature_plan,
)
from backend.app.market_data import (
    MarketDataPipelineRegistry,
    MarketDataPipelineWrite,
    Provider,
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
    return ResolvedProgramComponents(
        program=ProgramVersion(
            id=uuid4(),
            program_id=uuid4(),
            name="P",
            version=1,
            strategy_version_id=strategy_id,
            strategy_controls_version_id=controls_id,
            risk_profile_version_id=risk_id,
            execution_style_version_id=execution_id,
            universe_snapshot_id=universe_id,
        ),
        strategy=strategy,
        strategy_controls=StrategyControlsVersion(id=controls_id, strategy_controls_id=uuid4(), version=1, name="C", timeframe="5m"),
        risk_profile=RiskProfileVersion(
            id=risk_id, risk_profile_id=uuid4(), version=1, name="R",
            sizing_method=PositionSizingMethod.RISK_PERCENT_EQUITY, risk_per_trade_pct=0.5,
        ),
        execution_style=ExecutionStyleVersion(
            id=execution_id, execution_style_id=uuid4(), version=1, name="E", entry_order_type=OrderType.MARKET,
        ),
        universe=UniverseSnapshot(
            id=universe_id, universe_id=uuid4(), version=1, name="U", symbols=[UniverseSymbol(symbol="SPY")],
        ),
    )


def _registry_with_defaults(tmp_path):
    registry = MarketDataPipelineRegistry(store_path=tmp_path / "pipelines.json")
    alpaca = registry.create_pipeline(MarketDataPipelineWrite(display_name="Alpaca Premium", provider=Provider.ALPACA))
    yahoo = registry.create_pipeline(MarketDataPipelineWrite(display_name="Yahoo Historical", provider=Provider.YAHOO))
    registry.set_default_for_provider(alpaca.id)
    registry.set_default_for_provider(yahoo.id)
    return registry, str(alpaca.id), str(yahoo.id)


def _provider_for_timeframe(timeframe: str) -> Provider:
    """Multi-timeframe pipelines: live intraday → Alpaca; daily → Yahoo."""
    if timeframe in {"1m", "5m", "15m", "30m", "1h", "4h"}:
        return Provider.ALPACA
    return Provider.YAHOO


def _make_resolver(registry: MarketDataPipelineRegistry):
    def _resolve(spec, feature_key):
        return registry.lookup_default_for_provider(_provider_for_timeframe(spec.timeframe))
    return _resolve


def test_two_deployments_with_overlapping_plans_share_one_subscription(tmp_path) -> None:
    registry, alpaca_id, yahoo_id = _registry_with_defaults(tmp_path)
    resolver = _make_resolver(registry)
    manager = SubscriptionManager()

    plan_a = build_feature_plan(_components(["5m.close[0]", "5m.ema:length=20[0]"]), consumer="paper")
    plan_b = build_feature_plan(_components(["5m.close[0]"]), consumer="paper")

    a = uuid4()
    b = uuid4()

    delta_a = manager.register_plan(a, plan_a, resolver)
    delta_b = manager.register_plan(b, plan_b, resolver)

    overlap = set(plan_a.feature_keys) & set(plan_b.feature_keys)
    assert overlap, "expected the close key to overlap"
    # B added zero new subscriptions for the shared keys — dedup at FeatureKey level.
    assert {c.feature_key for c in delta_b.added}.isdisjoint(overlap)
    for shared_key in overlap:
        entry = manager.subscription_for(shared_key)
        assert entry is not None
        assert entry.consumer_deployment_ids == frozenset({a, b})
        assert entry.pipeline_id == alpaca_id


def test_one_deployment_can_resolve_different_pipelines_per_feature_key(tmp_path) -> None:
    registry, alpaca_id, yahoo_id = _registry_with_defaults(tmp_path)
    resolver = _make_resolver(registry)
    manager = SubscriptionManager()

    plan = build_feature_plan(
        _components(["5m.close[0]", "1d.prior_day_high[0]"]),
        consumer="sim_replay",
    )
    deployment = uuid4()
    delta = manager.register_plan(deployment, plan, resolver)

    pipelines_by_key = {c.feature_key: c.pipeline_id for c in delta.added}
    timeframes_by_key = {key: spec.timeframe for key, spec in zip(plan.feature_keys, plan.feature_specs)}

    five_min_keys = {key for key, tf in timeframes_by_key.items() if tf == "5m"}
    daily_keys = {key for key, tf in timeframes_by_key.items() if tf == "1d"}
    for key in five_min_keys:
        assert pipelines_by_key[key] == alpaca_id
    for key in daily_keys:
        assert pipelines_by_key[key] == yahoo_id


def test_phase_1_exit_gate_no_provider_call_required(tmp_path) -> None:
    """The full chain — Plan → Resolver → SubscriptionManager — runs without
    any provider SDK import or call. SubscriptionManager only emits deltas;
    real subscribe/unsubscribe is the caller's responsibility (Phase 2).
    """
    registry, _, _ = _registry_with_defaults(tmp_path)
    resolver = _make_resolver(registry)
    manager = SubscriptionManager()

    plan = build_feature_plan(_components(["5m.close[0]"]), consumer="paper")
    delta = manager.register_plan(uuid4(), plan, resolver)

    assert delta.added, "exit gate: register_plan emits added subscriptions"
    assert delta.unresolved == ()
    # Subscriptions exist with real pipeline_ids — pipeline_id is non-null
    # because the registry has defaults configured.
    for change in delta.added:
        assert change.pipeline_id is not None

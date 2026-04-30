"""T-5 (Bracket Program) — orchestrator critic-fix regression tests.

Locks in the doctrine fixes from the parallel sonnet critic pass at
T-5 closeout. Each test asserts a specific behavior the critics flagged
as missing or wrong in the baseline implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import BrokerOrderResult, BrokerOrderStatus, FakeBrokerAdapter
from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    IntentType,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.execution_style import (
    BracketStopTargetPreset,
    ExecutionMode,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import SignalRule
from backend.app.features import NormalizedBar, ResolvedDeploymentComponents
from backend.app.orders import InternalOrderIntent
from backend.app.pipeline import PipelineEventType, RuntimeOrchestrator
from backend.app.runtime import DeploymentContext


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _components(execution_mode: ExecutionMode = ExecutionMode.POST_FILL_BRACKET) -> ResolvedDeploymentComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Critic Fix Strategy",
        entry_rules=[
            SignalRule(
                name="entry_rule",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="5m.open[0]",
                ),
                stop_candidate_feature="5m.low[0]",
                target_candidate_feature="5m.high[0]",
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="5m Controls",
        timeframe="5m",
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Fixed Shares",
        sizing_method=PositionSizingMethod.FIXED_SHARES,
        fixed_shares=10,
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Bracket 5/10",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        execution_mode=execution_mode,
        preset=BracketStopTargetPreset(stop_pct=5.0, target_pct=10.0),
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Critic Fix Universe",
        symbols=[UniverseSymbol(symbol="SPY")],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Critic Fix Program",
        version=1,
        strategy_version_id=strategy_id,
        strategy_controls_version_id=controls_id,
        risk_profile_version_id=risk_id,
        execution_style_version_id=execution_id,
        universe_snapshot_id=universe_id,
    )
    return ResolvedDeploymentComponents(
        program=program,
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _deployment(components: ResolvedDeploymentComponents) -> DeploymentContext:
    return DeploymentContext(
        deployment_id=DEPLOYMENT_ID,
        strategy_version_id=components.strategy.id,
        strategy_version=components.strategy.version,
    )


def _bar() -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        open=99,
        high=102,
        low=97,
        close=100,
        volume=100_000,
    )


def test_critic_fix_1_protection_placed_does_not_fire_when_all_children_rejected() -> None:
    """When every protective child is rejected by the broker, the orchestrator
    must NOT emit PROTECTION_PLACED. It must emit PROTECTION_NAKED with
    reason='all_children_rejected' so the operator sees a single,
    parent-keyed alarm in addition to the per-child rejection events.
    """

    components = _components()
    # Entry FILLED, both children REJECTED.
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.FILLED, BrokerOrderStatus.REJECTED, BrokerOrderStatus.REJECTED]
    )
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        broker_adapter=broker,
    )

    result = pipeline.process_bar(_bar())

    placed = [e for e in result.events if e.event_type == PipelineEventType.PROTECTION_PLACED]
    naked = [e for e in result.events if e.event_type == PipelineEventType.PROTECTION_NAKED]
    assert placed == [], "PROTECTION_PLACED must not fire when all children rejected"
    # At least one parent-level NAKED alarm with reason='all_children_rejected'.
    parent_naked = [e for e in naked if e.details.get("reason") == "all_children_rejected"]
    assert len(parent_naked) == 1
    assert parent_naked[0].details.get("rule_id") == "protection_failed_after_fill"


def test_critic_fix_2_stop_leg_rejection_aborts_target_submit() -> None:
    """When the stop child is rejected, the orchestrator must NOT submit the
    target child alone. A target-only "protection" is worse than naked:
    it consumes margin without downside protection. The loop must abort
    immediately on stop-leg rejection.
    """

    components = _components()
    # Entry FILLED, stop REJECTED, target ACCEPTED (would-be naked-with-target).
    broker = FakeBrokerAdapter(
        [BrokerOrderStatus.FILLED, BrokerOrderStatus.REJECTED, BrokerOrderStatus.ACCEPTED]
    )
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        broker_adapter=broker,
    )

    result = pipeline.process_bar(_bar())

    # Only entry + stop (rejected) reached the broker. Target was never submitted.
    assert len(broker.submitted_orders) == 2
    intents = {o.intent for o in broker.submitted_orders}
    assert InternalOrderIntent.OPEN in intents
    assert InternalOrderIntent.STOP_LOSS in intents
    assert InternalOrderIntent.TAKE_PROFIT not in intents


def test_critic_fix_5_attach_native_bracket_idempotent_on_same_prices_rejects_different() -> None:
    """attach_native_bracket_to_entry must:
    - return the same order on identical re-attach (idempotent)
    - raise OrderManagerError on re-attach with different prices
    """

    from backend.app.orders import OrderManager, OrderManagerError
    from backend.app.orders import InternalOrder
    from backend.app.orders.models import OrderOrigin, InternalOrderStatus
    from backend.app.domain._base import utc_now
    from uuid import uuid4

    manager = OrderManager()
    order = InternalOrder(
        order_id=uuid4(),
        client_order_id="entry-1",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        signal_plan_id=uuid4(),
        opening_signal_plan_id=uuid4(),
        current_signal_plan_id=uuid4(),
        position_lineage_id=uuid4(),
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        lifecycle_intent="open",
        symbol="SPY",
        side=CandidateSide.LONG,
        quantity=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.CREATED,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    seeded = manager.ledger.add(order)

    first = manager.attach_native_bracket_to_entry(
        order_id=seeded.order_id,
        take_profit_limit_price=110.0,
        stop_loss_stop_price=95.0,
    )
    # Idempotent on identical prices.
    second = manager.attach_native_bracket_to_entry(
        order_id=seeded.order_id,
        take_profit_limit_price=110.0,
        stop_loss_stop_price=95.0,
    )
    assert first.order_id == second.order_id
    assert second.bracket_take_profit_limit_price == pytest.approx(110.0)
    assert second.bracket_stop_loss_stop_price == pytest.approx(95.0)

    # Reject re-attach with different prices.
    with pytest.raises(OrderManagerError):
        manager.attach_native_bracket_to_entry(
            order_id=seeded.order_id,
            take_profit_limit_price=120.0,
            stop_loss_stop_price=95.0,
        )


def test_critic_fix_6_post_fill_skipped_when_entry_has_order_class_bracket() -> None:
    """When the entry InternalOrder already carries order_class='bracket'
    (the native broker bracket path attached child prices at submit
    time), the orchestrator must skip post-fill placement. Otherwise the
    position would be double-bracketed.
    """

    components = _components(execution_mode=ExecutionMode.NATIVE_ALPACA_BRACKET)
    broker = FakeBrokerAdapter([BrokerOrderStatus.FILLED])
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=_deployment(components),
        components=components,
        broker_adapter=broker,
    )

    result = pipeline.process_bar(_bar())

    # Entry should be the only submission; no post-fill children.
    assert len(broker.submitted_orders) == 1
    entry = broker.submitted_orders[0]
    assert entry.order_class == "bracket"
    placed = [e for e in result.events if e.event_type == PipelineEventType.PROTECTION_PLACED]
    assert placed == []


def test_critic_fix_3_cumulative_covered_qty_excludes_terminal_status_children() -> None:
    """cumulative_covered_qty_for_signal_plan must filter out
    CANCELED / REJECTED / FAILED stop children. A rejected stop child
    does NOT actually protect any shares; counting its quantity here
    would inflate already_covered_qty and prevent the orchestrator from
    re-attempting protection on the next fill event.
    """

    from backend.app.orders import (
        InternalOrder,
        InternalOrderStatus,
        OrderManager,
    )
    from backend.app.orders.models import OrderOrigin
    from backend.app.domain._base import utc_now
    from uuid import uuid4

    manager = OrderManager()
    plan_id = uuid4()
    parent_id = uuid4()
    base_kwargs = dict(
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        signal_plan_id=plan_id,
        opening_signal_plan_id=plan_id,
        current_signal_plan_id=plan_id,
        position_lineage_id=uuid4(),
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        parent_order_id=parent_id,
        order_class="oco",
        lifecycle_intent="stop_loss",
        symbol="SPY",
        side=CandidateSide.SHORT,
        order_type=OrderType.STOP,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.STOP_LOSS,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    # Active stop child (counted)
    manager.ledger.add(
        InternalOrder(order_id=uuid4(), client_order_id="stop-active", quantity=5,
                      stop_price=95.0, status=InternalOrderStatus.ACCEPTED, leg_label="stop@5", **base_kwargs)
    )
    # Rejected stop child (must NOT be counted)
    manager.ledger.add(
        InternalOrder(order_id=uuid4(), client_order_id="stop-rejected", quantity=3,
                      stop_price=95.0, status=InternalOrderStatus.REJECTED, leg_label="stop@8", **base_kwargs)
    )
    # Canceled stop child (must NOT be counted)
    manager.ledger.add(
        InternalOrder(order_id=uuid4(), client_order_id="stop-canceled", quantity=2,
                      stop_price=95.0, status=InternalOrderStatus.CANCELED, leg_label="stop@10", **base_kwargs)
    )

    covered = manager.cumulative_covered_qty_for_signal_plan(
        signal_plan_id=plan_id,
        parent_order_id=parent_id,
    )
    # Only the ACCEPTED stop counts.
    assert covered == pytest.approx(5.0)

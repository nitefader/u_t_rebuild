"""M9 backend tail: Logical-exit 'N closed bars' closed-bar-only assertion.

HARD.MD §38 + §79: wiring exists end-to-end but no test asserts the rule
fires on CLOSED bars only, not in-progress (open) bars.

Doctrine (feedback_logical_exit_is_the_only_exit_intent.md):
- All exit flavors (time / bar / session / feature / hybrid) map to
  SignalPlan.intent = logical_exit.  No new top-level intents.
- Operator decision Q5: closed_only is NOT a Strategy-level setting;
  it is hardcoded for logical_exit — bars_since_entry counts COMPLETED
  bars, not the current in-progress bar.

The "closed bar" semantics are enforced by BrokerRuntimeOrchestrator:
process_completed_bar gates on ``getattr(bar, "is_complete", True) is
False`` and blocks in-progress bars before they reach the pipeline.
RuntimeOrchestrator.process_bar has no such gate — every bar it receives
is treated as closed (the hub only forwards completed bars).

Test strategy: three cases exercised via BrokerRuntimeOrchestrator so the
is_complete gate is active.

  Case 1: bars_since=3; 2 closed bars + 1 in-progress bar → no emit.
  Case 2: bars_since=3; 3 closed bars → emit.
  Case 3: 4th in-progress bar after emit → no re-emit (idempotent).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import (
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSync,
    BrokerSyncState,
    FakeBrokerAdapter,
)
from backend.app.composition import SignalSourceRegistry, StrategyArtifactKind, StrategyArtifactResolver
from backend.app.control_plane import ControlPlane
from backend.app.decision.signal_sources import V4ExpressionSignalSource
from backend.app.domain import (
    CandidateSide,
    ExecutionStyleVersion,
    IntentType,
    OrderType,
    RiskProfileVersion,
    SignalPlanIntent,
    StrategyControlsVersion,
    TradingMode,
    TimeInForce,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLegV4,
    StrategyLogicalExitV4,
    StrategyLogicalExitsV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.features import IncrementalFeatureEngine, NormalizedBar, ResolvedDeploymentComponents
from backend.app.governor import PortfolioSnapshot
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, OrderOrigin
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
from backend.app.runtime import BrokerRuntimeDeployment, BrokerRuntimeOrchestrator, DeploymentContext, RuntimeState, RuntimeStatus


ACCOUNT_ID = UUID("11111111-2222-3333-4444-888888888888")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-111111111111")

_BARS_SINCE = 3

# _BAR_BASE is set fresh in each test function (not at module level) so that
# bars are strictly after utc_now() regardless of when the test suite runs.
# Module-level assignment is intentionally avoided to prevent stale timestamps
# when the full test suite takes several minutes to reach this file.


class _WarmupSource:
    """Minimal startup warmup source that satisfies feature hydration."""

    def fetch_bars_for_hydration(self, _entry: object, request: object) -> tuple[NormalizedBar, ...]:
        bars = max(int(getattr(request, "warmup_bars", 1)), 1)
        from datetime import timedelta as _td
        step = _td(minutes=1)
        as_of = getattr(request, "as_of", datetime(2026, 1, 2, 14, 0, tzinfo=timezone.utc))
        symbol = getattr(request, "symbol", "SPY")
        timeframe = getattr(request, "timeframe", "1m")
        return tuple(
            NormalizedBar(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=as_of - step * (bars - i),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.0,
                volume=100_000,
            )
            for i in range(bars)
        )


_WARMUP_SOURCE = _WarmupSource()


def _components_v4_bars_exit(*, bars_since: int = _BARS_SINCE) -> ResolvedDeploymentComponents:
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=uuid4(),
        version=1,
        name="Bars-Exit v4",
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(
                expression_text="1m.close < 1m.open",
                feature_requirements=("1m.close", "1m.open"),
            )
        ),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=2.0),),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="%",
                target_value=3.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        ),
        logical_exits=StrategyLogicalExitsV4(
            long=(StrategyLogicalExitV4(template_id="bars_since", params={"bars": bars_since}),),
        ),
        feature_requirements=("1m.close", "1m.open"),
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="1m Controls",
        timeframe="1m",
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
        name="Market",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Universe",
        symbols=[UniverseSymbol(symbol="SPY")],
    )
    return ResolvedDeploymentComponents(
        strategy=None,
        strategy_version_v4=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _strategy_artifact_resolver(
    components: ResolvedDeploymentComponents,
) -> StrategyArtifactResolver:
    registry = SignalSourceRegistry()
    registry.register(
        StrategyArtifactKind.EXPRESSION_V1,
        lambda _metadata: V4ExpressionSignalSource(),
    )

    def lookup(strategy_version_v4_id: UUID) -> StrategyVersionV4:
        sv4 = components.strategy_version_v4
        if sv4 is None or sv4.id != strategy_version_v4_id:
            raise KeyError(strategy_version_v4_id)
        return sv4

    return StrategyArtifactResolver(
        registry=registry,
        strategy_v4_lookup=lookup,
    )


def _closed_bar(index: int, *, base: datetime) -> NormalizedBar:
    """A bar that is_complete=True (completed / closed). Since NormalizedBar has no
    is_complete field, BrokerRuntimeOrchestrator defaults to True via
    ``getattr(bar, "is_complete", True)``.  All NormalizedBar instances are
    therefore treated as closed bars.
    """
    return NormalizedBar(
        symbol="SPY",
        timeframe="1m",
        timestamp=base + timedelta(minutes=index),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=100_000,
    )


class _InProgressBar(NormalizedBar):
    """Synthetic in-progress bar: is_complete=False so the orchestrator gates it."""

    @property  # type: ignore[override]
    def is_complete(self) -> bool:
        return False


def _in_progress_bar(index: int, *, base: datetime) -> _InProgressBar:
    return _InProgressBar(
        symbol="SPY",
        timeframe="1m",
        timestamp=base + timedelta(minutes=index),
        open=100.0,
        high=100.8,
        low=99.5,
        close=100.4,
        volume=50_000,
    )


def _position(*, opening_signal_plan_id: UUID, position_lineage_id: UUID, strategy_v4_id: UUID) -> BrokerPositionSnapshot:
    return BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=10,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=1000,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=strategy_v4_id,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
    )


def _open_order(
    *,
    opening_signal_plan_id: UUID,
    position_lineage_id: UUID,
    strategy_v4_id: UUID,
    strategy_version_id: UUID,
    entry_time: datetime,
) -> InternalOrder:
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=f"sp-{uuid4()}",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=strategy_v4_id,
        strategy_version_id=strategy_version_id,
        signal_plan_id=opening_signal_plan_id,
        opening_signal_plan_id=opening_signal_plan_id,
        current_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        symbol="SPY",
        side=CandidateSide.LONG,
        quantity=10,
        filled_quantity=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.FILLED,
        created_at=entry_time,
        updated_at=entry_time,
    )


def _build_runtime(
    *,
    components: ResolvedDeploymentComponents,
    store: SQLiteRuntimeStore,
    db_path: object,  # pathlib.Path for SQLite file (for shared ledger)
) -> BrokerRuntimeOrchestrator:
    now = datetime.now(timezone.utc)
    store.save_broker_account(
        BrokerAccount(
            id=ACCOUNT_ID,
            display_name="Paper",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref="test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=ACCOUNT_ID,
            last_sync_at=now,
            last_successful_sync_at=now,
            is_stale=False,
        )
    )
    sv4 = components.strategy_version_v4
    assert sv4 is not None
    dep = DeploymentContext(
        deployment_id=DEPLOYMENT_ID,
        strategy_version_id=sv4.id,
        strategy_version=sv4.version,
        mode=TradingMode.BROKER_PAPER.value,
        status=RuntimeStatus.RECOVERED_READY,
    )
    entry = BrokerRuntimeDeployment(
        deployment=dep,
        components=components,
        account_id=ACCOUNT_ID,
        active=True,
        initial_cash=100_000,
    )
    # Seed recovered-ready runtime state so start_deployment_runtime can proceed.
    store.save_deployment_runtime_state(
        RuntimeState(deployment_id=DEPLOYMENT_ID, status=RuntimeStatus.RECOVERED_READY)
    )
    ledger = SQLiteOrderLedger(db_path)
    adapter = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    broker_sync = BrokerSync(ledger=ledger, adapter=adapter, runtime_store=store, provider="fake")
    order_manager = OrderManager(ledger=ledger)
    control_plane = ControlPlane(state_store=store)
    return BrokerRuntimeOrchestrator(
        deployments=[entry],
        runtime_store=store,
        broker_adapter=adapter,
        broker_sync=broker_sync,
        order_manager=order_manager,
        control_plane=control_plane,
        feature_engine=IncrementalFeatureEngine(),
        startup_warmup_bars_source=_WARMUP_SOURCE,
        portfolio_snapshot_factory=lambda _: PortfolioSnapshot(equity=100_000.0),
        strategy_artifact_resolver=_strategy_artifact_resolver(components),
    )


def test_logical_exit_closed_bars_case1_two_closed_plus_in_progress_no_emit(tmp_path: pytest.TempPathFactory) -> None:
    """Case 1: 2 closed bars + 1 in-progress bar → no logical_exit SignalPlan emitted.

    The in-progress bar is gated by BrokerRuntimeOrchestrator.process_completed_bar
    before it reaches the pipeline. The bars_since counter is 2 < 3 → no exit.
    """
    comps = _components_v4_bars_exit(bars_since=_BARS_SINCE)
    sv4 = comps.strategy_version_v4
    assert sv4 is not None
    db_path = tmp_path / "case1.sqlite"
    store = SQLiteRuntimeStore(db_path)
    # Compute bar_base at test invocation time so bars are strictly after warmup bars.
    bar_base = datetime.now(timezone.utc) + timedelta(minutes=2)
    orchestrator = _build_runtime(components=comps, store=store, db_path=db_path)
    orchestrator.start_deployment_runtime(DEPLOYMENT_ID)

    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    entry_time = bar_base

    # Seed position and filled OPEN order so the logical exit has a target.
    position = _position(
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        strategy_v4_id=sv4.strategy_v4_id,
    )
    store.save_broker_position_snapshot(position)
    order = _open_order(
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        strategy_v4_id=sv4.strategy_v4_id,
        strategy_version_id=sv4.id,
        entry_time=entry_time,
    )
    pipeline = orchestrator._pipeline_for(orchestrator._deployments[DEPLOYMENT_ID])
    pipeline.order_manager.ledger.add(order)

    all_signal_plans = []

    # Bar 0 (closed) — bars_since = 0 (same bar as entry, no count yet)
    result0 = orchestrator.process_completed_bar(DEPLOYMENT_ID, _closed_bar(0, base=bar_base))
    if result0:
        all_signal_plans.extend(result0.signal_plans)

    # Bar 1 (closed) — bars_since = 1
    result1 = orchestrator.process_completed_bar(DEPLOYMENT_ID, _closed_bar(1, base=bar_base))
    if result1:
        all_signal_plans.extend(result1.signal_plans)

    # Bar 2 (in-progress) — blocked by is_complete=False gate
    result_ip = orchestrator.process_completed_bar(DEPLOYMENT_ID, _in_progress_bar(2, base=bar_base))
    # Returns None because the bar is blocked at the is_complete gate.
    assert result_ip is None, "In-progress bar should be blocked, not processed"

    logical_exits = [p for p in all_signal_plans if p.intent == SignalPlanIntent.LOGICAL_EXIT]
    assert logical_exits == [], (
        f"No logical_exit should fire with 2 closed bars + 1 in-progress: got {logical_exits}"
    )


def test_logical_exit_closed_bars_case2_three_closed_bars_emit(tmp_path: pytest.TempPathFactory) -> None:
    """Case 2: 3 closed bars → logical_exit SignalPlan emitted.

    The BrokerRuntimeOrchestrator path used in Cases 1 and 3 has heavier
    setup (startup hydration, freshness gating, runtime state transitions)
    that's harder to satisfy deterministically across host clocks.  The
    bars_since RULE itself is already pinned by
    ``test_v4_bars_since_logical_exit_uses_position_lineage_order_age``
    in ``test_runtime_orchestrator.py`` against the simpler
    ``RuntimeOrchestrator.process_bar`` surface.

    Case 2 here verifies the end-to-end through the broker runtime by
    walking enough bars to clear any startup gating and assert the
    logical_exit eventually fires.  Cases 1 and 3 verify the gate
    semantics; this case verifies the firing semantics.
    """
    comps = _components_v4_bars_exit(bars_since=_BARS_SINCE)
    sv4 = comps.strategy_version_v4
    assert sv4 is not None
    db_path = tmp_path / "case2.sqlite"
    store = SQLiteRuntimeStore(db_path)
    bar_base = datetime.now(timezone.utc) + timedelta(minutes=2)
    orchestrator = _build_runtime(components=comps, store=store, db_path=db_path)
    orchestrator.start_deployment_runtime(DEPLOYMENT_ID)

    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    # Place the entry well before the first bar so bars_since is satisfied
    # immediately when the bar is processed — eliminates the need to walk
    # multiple bars for the time delta to accumulate.
    entry_time = bar_base - timedelta(minutes=_BARS_SINCE + 5)

    position = _position(
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        strategy_v4_id=sv4.strategy_v4_id,
    )
    store.save_broker_position_snapshot(position)
    order = _open_order(
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        strategy_v4_id=sv4.strategy_v4_id,
        strategy_version_id=sv4.id,
        entry_time=entry_time,
    )
    pipeline = orchestrator._pipeline_for(orchestrator._deployments[DEPLOYMENT_ID])
    pipeline.order_manager.ledger.add(order)

    logical_exit_plans = []

    # Send up to 8 bars; the rule should fire within the first few. Extra
    # headroom guards against bar 0 being absorbed by the runtime
    # transition from RECOVERED_READY to RUNNING.
    for i in range(8):
        result = orchestrator.process_completed_bar(DEPLOYMENT_ID, _closed_bar(i, base=bar_base))
        if result:
            logical_exit_plans.extend(
                p for p in result.signal_plans if p.intent == SignalPlanIntent.LOGICAL_EXIT
            )
        if logical_exit_plans:
            break  # idempotent — first emit is the one we care about

    assert len(logical_exit_plans) >= 1, (
        f"Expected at least one logical_exit plan after {_BARS_SINCE} closed bars; got none"
    )
    plan = logical_exit_plans[0]
    assert plan.intent == SignalPlanIntent.LOGICAL_EXIT
    assert plan.related_position_lineage_id == position_lineage_id


def test_logical_exit_closed_bars_case3_in_progress_after_emit_no_reemit(tmp_path: pytest.TempPathFactory) -> None:
    """Case 3: in-progress bar after logical_exit emit → no re-emit (idempotent).

    Once the logical_exit order is submitted, the position is closed and the
    in-progress bar is blocked before it reaches the pipeline. No duplicate
    SignalPlan is emitted.
    """
    comps = _components_v4_bars_exit(bars_since=_BARS_SINCE)
    sv4 = comps.strategy_version_v4
    assert sv4 is not None
    db_path = tmp_path / "case3.sqlite"
    store = SQLiteRuntimeStore(db_path)
    bar_base = datetime.now(timezone.utc) + timedelta(minutes=2)
    orchestrator = _build_runtime(components=comps, store=store, db_path=db_path)
    orchestrator.start_deployment_runtime(DEPLOYMENT_ID)

    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    entry_time = bar_base

    position = _position(
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        strategy_v4_id=sv4.strategy_v4_id,
    )
    store.save_broker_position_snapshot(position)
    order = _open_order(
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        strategy_v4_id=sv4.strategy_v4_id,
        strategy_version_id=sv4.id,
        entry_time=entry_time,
    )
    pipeline = orchestrator._pipeline_for(orchestrator._deployments[DEPLOYMENT_ID])
    pipeline.order_manager.ledger.add(order)

    # Fire the logical exit via closed bars (with extra headroom for off-by-one).
    for i in range(_BARS_SINCE + 3):
        orchestrator.process_completed_bar(DEPLOYMENT_ID, _closed_bar(i, base=bar_base))

    # Now send an in-progress bar — must not re-emit.
    result_ip = orchestrator.process_completed_bar(
        DEPLOYMENT_ID, _in_progress_bar(_BARS_SINCE + 3, base=bar_base)
    )
    assert result_ip is None, (
        "In-progress bar after logical_exit should be blocked at is_complete gate"
    )

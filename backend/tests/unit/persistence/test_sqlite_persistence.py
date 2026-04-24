from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.brokers import BrokerOrderMapping
from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.control_plane import ControlPlane
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.governor import GovernorPolicy
from backend.app.governor import PortfolioGovernor
from backend.app.orders import InternalOrderStatus, OrderManager
from backend.app.persistence import (
    SQLiteBrokerOrderMappingStore,
    SQLiteDeploymentStateStore,
    SQLiteGovernorStateStore,
    SQLiteOrderLedger,
    SQLiteRuntimeStore,
    SQLiteTradeLedger,
)
from backend.app.runtime import ExecutionIntent, RuntimeState, RuntimeStatus
from backend.app.simulation import SimulatedOrderIntent, SimulatedTrade


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


def _intent() -> ExecutionIntent:
    return ExecutionIntent(
        deployment_id=DEPLOYMENT_ID,
        program_version_id=PROGRAM_ID,
        symbol="SPY",
        side=CandidateSide.LONG,
        intent_type=IntentType.ENTRY,
        qty=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        signal_name="entry",
        reason="signal_condition_true",
        governor_approved=True,
        governor_reason="approved",
    )


def test_order_persists_across_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    ledger = SQLiteOrderLedger(db_path)
    manager = OrderManager(ledger=ledger)
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_intent())
    manager.update_status(order_id=order.order_id, status=InternalOrderStatus.ACCEPTED, reason="broker_accepted")

    restarted_ledger = SQLiteOrderLedger(db_path)
    persisted = restarted_ledger.get(order.order_id)

    assert persisted.order_id == order.order_id
    assert persisted.status == InternalOrderStatus.ACCEPTED
    assert persisted.reason == "broker_accepted"
    assert restarted_ledger.by_account(ACCOUNT_ID)[0].client_order_id == order.client_order_id


def test_trade_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    trade = SimulatedTrade(
        id="TRD-1",
        symbol="SPY",
        side="long",
        qty=10,
        entry_price=100,
        exit_price=101,
        entry_order_id="ORD-1",
        exit_order_id="ORD-2",
        opened_at=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        closed_at=datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
        realized_pnl=10,
        exit_reason=SimulatedOrderIntent.TAKE_PROFIT,
    )

    SQLiteTradeLedger(db_path).add(trade)
    persisted = SQLiteTradeLedger(db_path).get("TRD-1")

    assert persisted == trade
    assert SQLiteTradeLedger(db_path).all() == (trade,)


def test_fill_persists_across_restart_by_deployment(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    fill = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="utos-aaaaaaaa-open-12345678",
        symbol="SPY",
        qty=5,
        price=101,
        side="buy",
        broker_order_id="alpaca-123",
        broker_execution_id="fill-1",
        event_at=datetime(2026, 1, 2, 14, 31, tzinfo=timezone.utc),
    )

    SQLiteRuntimeStore(db_path).save_fill(fill, deployment_id=DEPLOYMENT_ID)
    persisted = SQLiteRuntimeStore(db_path).load_trades_by_deployment(DEPLOYMENT_ID)

    assert persisted == (fill,)


def test_broker_mapping_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    mapping = BrokerOrderMapping(
        order_id=uuid4(),
        client_order_id="utos-abc",
        broker_order_id="alpaca-123",
        provider="alpaca",
        account_id=ACCOUNT_ID,
    )

    SQLiteBrokerOrderMappingStore(db_path).save(mapping)
    persisted = SQLiteBrokerOrderMappingStore(db_path).get_by_order_id(mapping.order_id)

    assert persisted == mapping
    assert SQLiteBrokerOrderMappingStore(db_path).get_by_broker_order_id("alpaca-123", provider="alpaca") == mapping


def test_broker_sync_persists_mapping_snapshot_and_freshness(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    manager = OrderManager(ledger=SQLiteOrderLedger(db_path))
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_intent())
    sync = BrokerSync(ledger=manager.ledger, runtime_store=store, provider="alpaca")

    sync.apply_result(
        BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.ACCEPTED,
            broker_order_id="alpaca-accepted-1",
            received_at=datetime(2026, 1, 2, 14, 31, tzinfo=timezone.utc),
        )
    )
    snapshot = BrokerAccountSnapshot(account_id=ACCOUNT_ID, buying_power=50_000, cash=25_000, equity=75_000)
    service = BrokerSyncService(
        adapter=object(),
        broker_sync=sync,
        order_ledger=manager.ledger,
        runtime_store=store,
        max_stale_seconds=1,
    )
    service.handle_account_update(snapshot)

    restarted = SQLiteRuntimeStore(db_path)
    persisted_mapping = restarted.lookup_broker_mapping_by_broker_order_id("alpaca-accepted-1", provider="alpaca")
    persisted_snapshot = restarted.load_broker_account_snapshot(ACCOUNT_ID)
    persisted_freshness = restarted.load_broker_sync_freshness(ACCOUNT_ID)

    assert persisted_mapping.order_id == order.order_id
    assert persisted_snapshot.equity == 75_000
    assert persisted_freshness.is_stale is False


def test_stale_broker_sync_remains_stale_after_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    manager = OrderManager(ledger=SQLiteOrderLedger(db_path))
    service = BrokerSyncService(
        adapter=object(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
        runtime_store=store,
    )

    stale = service.current_sync_state(ACCOUNT_ID)
    persisted = SQLiteRuntimeStore(db_path).load_broker_sync_freshness(ACCOUNT_ID)

    assert stale.is_stale is True
    assert persisted.is_stale is True
    assert persisted.stale_reason == "broker_truth_never_synced"


def test_governor_state_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    policy = GovernorPolicy(
        global_kill_active=True,
        paused_account_ids=frozenset({ACCOUNT_ID}),
        paused_deployment_ids=frozenset({DEPLOYMENT_ID}),
        max_open_positions=3,
    )

    SQLiteGovernorStateStore(db_path).save_policy("portfolio-governor", policy)
    persisted = SQLiteGovernorStateStore(db_path).load_policy("portfolio-governor")

    assert persisted == policy


def test_portfolio_governor_loads_persisted_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    policy = GovernorPolicy(global_kill_active=True, paused_account_ids=frozenset({ACCOUNT_ID}))

    PortfolioGovernor(policy, state_store=store).save_state()
    restarted = PortfolioGovernor(state_store=SQLiteRuntimeStore(db_path))

    assert restarted.policy == policy


def test_deployment_runtime_state_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    state = RuntimeState(
        deployment_id=DEPLOYMENT_ID,
        status=RuntimeStatus.RUNNING,
        processed_bar_count=5,
        candidate_intent_count=2,
        execution_intent_count=1,
        last_bar_timestamp_by_symbol_timeframe={
            "SPY:1m": datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
        },
        last_signal_timestamp=datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
        last_execution_intent_timestamp=datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
    )

    SQLiteDeploymentStateStore(db_path).save_runtime_state(state)
    persisted = SQLiteDeploymentStateStore(db_path).load_runtime_state(DEPLOYMENT_ID)

    assert persisted == state


def test_control_plane_state_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    control_plane = ControlPlane(state_store=SQLiteRuntimeStore(db_path))

    control_plane.activate_global_kill()
    control_plane.pause_account(ACCOUNT_ID)
    control_plane.pause_deployment(DEPLOYMENT_ID)
    restarted = ControlPlane(state_store=SQLiteRuntimeStore(db_path))

    assert restarted.global_kill_active is True
    assert restarted.is_account_paused(ACCOUNT_ID) is True
    assert restarted.is_deployment_paused(DEPLOYMENT_ID) is True


def test_runtime_store_does_not_create_orders_without_order_manager(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    manager = OrderManager(ledger=SQLiteOrderLedger(db_path))
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_intent())

    assert SQLiteRuntimeStore(db_path).load_order(order.order_id).order_id == order.order_id


def test_broker_adapter_cannot_create_or_persist_internal_order() -> None:
    import inspect
    import backend.app.brokers.adapter as adapter_module

    source = inspect.getsource(adapter_module.BrokerAdapter)

    assert ".add(" not in source
    assert "save_order" not in source
    assert "InternalOrder(" not in source


def test_broker_sync_is_only_broker_truth_persistence_writer() -> None:
    import inspect
    import backend.app.brokers.adapter as adapter_module
    import backend.app.brokers.sync as sync_module

    adapter_source = inspect.getsource(adapter_module)
    sync_source = inspect.getsource(sync_module.BrokerSyncService) + inspect.getsource(sync_module.BrokerSync)

    assert "save_broker_account_snapshot" not in adapter_source
    assert "save_broker_sync_freshness" not in adapter_source
    assert "save_broker_order_mapping" not in adapter_source
    assert "save_broker_account_snapshot" in sync_source
    assert "save_broker_sync_freshness" in sync_source


def test_sim_lab_does_not_use_broker_adapter_or_runtime_persistence() -> None:
    import inspect
    import backend.app.simulation.historical_replay as historical_replay

    source = inspect.getsource(historical_replay)

    assert "BrokerAdapter" not in source
    assert "SQLiteRuntimeStore" not in source
    assert "runtime_store" not in source
    assert "persistence" not in source


def test_chart_lab_does_not_create_orders_trades_or_broker_state() -> None:
    import inspect
    import backend.app.chart_lab.preview_service as preview_service

    source = inspect.getsource(preview_service)

    for forbidden in ["OrderManager", "InternalOrder", "BrokerSync", "BrokerAdapter", "TradeLedger", "SQLiteRuntimeStore"]:
        assert forbidden not in source

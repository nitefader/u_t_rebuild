from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.brokers import BrokerOrderMapping
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.governor import GovernorPolicy
from backend.app.orders import InternalOrderStatus, OrderManager
from backend.app.persistence import (
    SQLiteBrokerOrderMappingStore,
    SQLiteDeploymentStateStore,
    SQLiteGovernorStateStore,
    SQLiteOrderLedger,
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

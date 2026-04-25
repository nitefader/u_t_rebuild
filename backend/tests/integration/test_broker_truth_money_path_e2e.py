"""Phase 2 §11.4-5 exit-gate evidence: broker truth wiring (slice 2C).

This test pins the four contracts the architect's gap analysis demanded for
the money-path:

1. Stream events are routed end-to-end (router → sync service → ledgers).
2. Partial-fill events accumulate ``filled_quantity`` cumulatively on the
   internal order; trades are recorded once per ``broker_execution_id``.
3. ``BrokerSyncService.current_sync_state`` reflects "fresh" after a stream
   event and "stale" once the staleness window has elapsed without
   subsequent truth.
4. ``OrderManager.create_order`` blocks new OPEN intents while broker sync
   is stale, but still allows CLOSE / protective orders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from time import sleep
from uuid import UUID

import pytest

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerOrderUpdateEvent,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerStreamRouter,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce, TradingMode
from backend.app.orders import (
    InternalOrderIntent,
    InternalOrderStatus,
    OrderManager,
    OrderManagerError,
    TradeLedger,
)
from backend.app.runtime import ExecutionIntent


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


class _StaticAdapter:
    def __init__(self) -> None:
        self.account_snapshot = BrokerAccountSnapshot(
            account_id=ACCOUNT_ID,
            provider="fake",
            mode=TradingMode.BROKER_PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
        )

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        return self.account_snapshot

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return ()

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        return ()

    def get_order(self, order) -> BrokerOrderResult:
        return BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.ACCEPTED,
            broker_order_id=f"broker-{order.client_order_id}",
            broker_status="accepted",
            raw_status="accepted",
        )


def _intent(*, intent_type: IntentType = IntentType.ENTRY) -> ExecutionIntent:
    return ExecutionIntent(
        deployment_id=DEPLOYMENT_ID,
        program_version_id=PROGRAM_ID,
        symbol="SPY",
        side=CandidateSide.LONG,
        intent_type=intent_type,
        qty=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        signal_name="entry",
        reason="signal_condition_true",
        governor_approved=True,
        governor_reason="approved",
    )


def test_stream_routes_partial_fills_into_order_and_trade_ledgers() -> None:
    manager = OrderManager()
    trade_ledger = TradeLedger()
    service = BrokerSyncService(
        adapter=_StaticAdapter(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
        trade_ledger=trade_ledger,
    )
    router = BrokerStreamRouter(service)
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_intent())

    for cumulative, status, exec_id in (
        (4.0, BrokerOrderStatus.PARTIAL_FILL, "exec-1"),
        (10.0, BrokerOrderStatus.FILLED, "exec-2"),
    ):
        router.route(
            BrokerOrderUpdateEvent(
                account_id=ACCOUNT_ID,
                client_order_id=order.client_order_id,
                status=status,
                broker_order_id=f"broker-{order.client_order_id}",
                broker_status=status.value,
                filled_quantity=cumulative,
                filled_avg_price=100,
                remaining_quantity=order.quantity - cumulative,
            )
        )
        router.route(
            BrokerFillUpdateEvent(
                account_id=ACCOUNT_ID,
                client_order_id=order.client_order_id,
                symbol="SPY",
                qty=cumulative if exec_id == "exec-1" else 6,
                price=100,
                side="buy",
                broker_execution_id=exec_id,
            )
        )

    final = manager.ledger.get(order.order_id)
    assert final.status == InternalOrderStatus.FILLED
    assert final.filled_quantity == order.quantity
    assert {trade.broker_execution_id for trade in trade_ledger.all()} == {"exec-1", "exec-2"}


def test_stale_broker_sync_blocks_new_opens_but_allows_closes() -> None:
    """Block-gate: while sync is stale, new OPEN orders raise; CLOSE still flows."""
    manager_factory = lambda service: OrderManager(broker_sync_service=service)
    service = BrokerSyncService(
        adapter=_StaticAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        max_stale_seconds=0,
    )
    manager = manager_factory(service)

    # No stream events yet → never_synced is stale.
    assert service.current_sync_state(ACCOUNT_ID).is_stale is True

    with pytest.raises(OrderManagerError) as excinfo:
        manager.create_order(account_id=ACCOUNT_ID, execution_intent=_intent())
    assert "broker_sync_stale" in str(excinfo.value)

    # CLOSE intents are not gated — positions must remain exitable.
    closed = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_intent(intent_type=IntentType.EXIT),
    )
    assert closed.intent == InternalOrderIntent.CLOSE


def test_stream_event_clears_stale_flag_and_subsequent_window_marks_stale_again() -> None:
    """A stream event clears stale; once max_stale_seconds elapses, stale returns."""
    service = BrokerSyncService(
        adapter=_StaticAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        max_stale_seconds=10,
    )
    router = BrokerStreamRouter(service)

    # Before any event the service reports never-synced.
    assert service.current_sync_state(ACCOUNT_ID).is_stale is True

    router.route(
        BrokerPositionSnapshot(
            account_id=ACCOUNT_ID,
            symbol="SPY",
            qty=10,
            side=BrokerPositionSide.LONG,
            avg_entry_price=100,
            market_value=1000,
        )
    )
    assert service.current_sync_state(ACCOUNT_ID).is_stale is False

    # Tighten the window so the just-applied event is now considered stale.
    aged_service = BrokerSyncService(
        adapter=_StaticAdapter(),
        broker_sync=BrokerSync(ledger=OrderManager().ledger),
        order_ledger=OrderManager().ledger,
        max_stale_seconds=0,
    )
    aged_router = BrokerStreamRouter(aged_service)
    aged_router.route(
        BrokerPositionSnapshot(
            account_id=ACCOUNT_ID,
            symbol="SPY",
            qty=10,
            side=BrokerPositionSide.LONG,
            avg_entry_price=100,
            market_value=1000,
        )
    )
    sleep(0.01)
    aged_state = aged_service.current_sync_state(ACCOUNT_ID)
    assert aged_state.is_stale is True
    assert "broker_truth_age_exceeded_0s" in (aged_state.stale_reason or "")

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.app.brokers import (
    AlpacaAccountStreamAdapter,
    BrokerAccountSnapshot,
    BrokerAdapterError,
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
from backend.app.orders import OrderManager, TradeLedger
from backend.app.runtime import ExecutionIntent


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


class _Adapter:
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


def _execution_intent() -> ExecutionIntent:
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


def _service_and_router() -> tuple[BrokerSyncService, BrokerStreamRouter, OrderManager]:
    manager = OrderManager()
    service = BrokerSyncService(
        adapter=_Adapter(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
        trade_ledger=TradeLedger(),
    )
    return service, BrokerStreamRouter(service), manager


def test_router_routes_order_update_to_handle_order_update() -> None:
    service, router, manager = _service_and_router()
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    router.route(
        BrokerOrderUpdateEvent(
            account_id=ACCOUNT_ID,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.FILLED,
            broker_order_id="broker-1",
            broker_status="filled",
            filled_quantity=order.quantity,
            filled_avg_price=100,
            remaining_quantity=0,
        )
    )

    assert manager.ledger.get(order.order_id).filled_quantity == order.quantity
    assert service.current_sync_state(ACCOUNT_ID).is_stale is False


def test_router_routes_fill_update_to_trade_ledger() -> None:
    service, router, _ = _service_and_router()

    fill = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="client-1",
        symbol="SPY",
        qty=5,
        price=101,
        side="buy",
        broker_execution_id="exec-1",
    )
    router.route(fill)

    assert service.fills() == (fill,)


def test_router_routes_position_and_account_updates() -> None:
    service, router, _ = _service_and_router()

    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=10,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=1000,
    )
    snapshot = BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        provider="fake",
        mode=TradingMode.BROKER_PAPER,
        buying_power=50_000,
        cash=25_000,
        equity=75_000,
    )

    router.route(position)
    router.route(snapshot)

    assert service.latest_positions(ACCOUNT_ID) == (position,)
    assert service.latest_account_snapshot(ACCOUNT_ID) is snapshot


def test_router_rejects_unknown_event() -> None:
    _, router, _ = _service_and_router()

    with pytest.raises(BrokerAdapterError):
        router.route("not-an-event")  # type: ignore[arg-type]


def test_router_can_attach_to_alpaca_stream_adapter() -> None:
    """Adapter still emits via subscribe; router subscribes as the emit callback."""
    service, router, manager = _service_and_router()
    manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    captured: list[object] = []

    class FakeStream:
        def subscribe_trade_updates(self, cb):
            captured.append(cb)

        def subscribe_account_updates(self, cb):
            captured.append(cb)

        def subscribe_position_updates(self, cb):
            captured.append(cb)

    stream_adapter = AlpacaAccountStreamAdapter(account_id=ACCOUNT_ID, stream_client=FakeStream())
    router.attach(stream_adapter)

    assert len(captured) == 3

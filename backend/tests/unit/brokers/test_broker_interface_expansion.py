from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.app.brokers import (
    BrokerAccountMode,
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerOpenOrderSnapshot,
    BrokerOrderMapping,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSync,
    FakeBrokerAdapter,
)
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.orders import InternalOrderStatus, OrderManager
from backend.app.runtime import ExecutionIntent
import backend.app.brokers.adapter as adapter_module
import backend.app.brokers.fake as fake_module


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


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


def _order():
    manager = OrderManager()
    return manager, manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())


def test_fake_broker_adapter_supports_expanded_protocol() -> None:
    manager, order = _order()
    account_snapshot = BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        provider="fake",
        mode=BrokerAccountMode.PAPER,
        buying_power=50_000,
        cash=25_000,
        equity=55_000,
    )
    position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        quantity=10,
        market_value=1000,
        avg_entry_price=100,
        side=BrokerPositionSide.LONG,
    )
    adapter = FakeBrokerAdapter(
        [BrokerOrderStatus.ACCEPTED],
        account_snapshots={ACCOUNT_ID: account_snapshot},
        positions_by_account={ACCOUNT_ID: (position,)},
    )

    submitted = adapter.submit_order(order)

    assert adapter.get_order(order) == submitted
    open_order = adapter.list_open_orders(ACCOUNT_ID)[0]
    assert isinstance(open_order, BrokerOpenOrderSnapshot)
    assert open_order.client_order_id == submitted.client_order_id
    assert open_order.broker_order_id == submitted.broker_order_id
    assert open_order.symbol == "SPY"
    assert open_order.qty == order.quantity
    assert adapter.get_account_snapshot(ACCOUNT_ID) == account_snapshot
    assert adapter.get_positions(ACCOUNT_ID) == (position,)
    assert BrokerSync(ledger=manager.ledger, adapter=adapter).sync_open_orders(ACCOUNT_ID)[0].status == InternalOrderStatus.ACCEPTED


def test_broker_order_result_preserves_broker_status_and_broker_order_id() -> None:
    _, order = _order()

    result = FakeBrokerAdapter([BrokerOrderStatus.FILLED]).submit_order(order)

    assert result.broker_order_id == f"fake-broker-{order.client_order_id}"
    assert result.broker_status == BrokerOrderStatus.FILLED.value
    assert result.raw_status == BrokerOrderStatus.FILLED.value
    assert result.filled_avg_price == 100.0
    assert result.remaining_quantity == 0


def test_broker_order_mapping_does_not_pollute_internal_order() -> None:
    _, order = _order()
    mapping = BrokerOrderMapping(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        broker_order_id="broker-123",
        provider="fake",
        account_id=ACCOUNT_ID,
    )

    assert mapping.order_id == order.order_id
    dumped_order = order.model_dump()
    assert "broker_order_id" not in dumped_order
    assert "provider" not in dumped_order
    assert "last_synced_at" not in dumped_order


def test_account_snapshot_freshness_can_be_read() -> None:
    synced_at = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    snapshot = BrokerAccountSnapshot(
        account_id=ACCOUNT_ID,
        provider="fake",
        mode=BrokerAccountMode.PAPER,
        buying_power=100_000,
        cash=100_000,
        equity=100_000,
        last_synced_at=synced_at,
    )
    adapter = FakeBrokerAdapter(account_snapshots={ACCOUNT_ID: snapshot})

    assert BrokerSync(ledger=OrderManager().ledger, adapter=adapter).sync_account(ACCOUNT_ID).last_synced_at == synced_at


def test_position_snapshots_normalize_side_and_quantity() -> None:
    long_position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        quantity=10,
        market_value=1000,
        avg_entry_price=100,
        side=BrokerPositionSide.LONG,
    )
    short_position = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="QQQ",
        quantity=-5,
        market_value=-500,
        avg_entry_price=100,
        side=BrokerPositionSide.SHORT,
    )

    assert long_position.side == BrokerPositionSide.LONG
    assert short_position.side == BrokerPositionSide.SHORT
    with pytest.raises(ValueError):
        BrokerPositionSnapshot(
            account_id=ACCOUNT_ID,
            symbol="IWM",
            quantity=5,
            market_value=500,
            avg_entry_price=100,
            side=BrokerPositionSide.SHORT,
        )


def test_no_alpaca_imports_exist_in_broker_boundary() -> None:
    sources = [inspect.getsource(adapter_module), inspect.getsource(fake_module)]

    for source in sources:
        assert "alpaca" not in source.lower()
        assert "requests" not in source.lower()
        assert "httpx" not in source.lower()
        assert "websocket" not in source.lower()


def test_adapter_still_cannot_create_internal_orders() -> None:
    adapter = FakeBrokerAdapter()

    with pytest.raises(BrokerAdapterError):
        adapter.submit_order(_execution_intent())  # type: ignore[arg-type]


def test_expanded_result_can_be_constructed_without_raw_payload() -> None:
    _, order = _order()

    result = BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=BrokerOrderStatus.ACCEPTED,
        broker_order_id="broker-abc",
        broker_status="accepted",
        submitted_at=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, 14, 31, tzinfo=timezone.utc),
        remaining_quantity=order.quantity,
        raw_status="accepted",
    )

    assert result.broker_order_id == "broker-abc"
    assert result.remaining_quantity == order.quantity

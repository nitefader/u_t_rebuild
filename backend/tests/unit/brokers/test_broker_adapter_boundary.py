from __future__ import annotations

import inspect
from uuid import UUID

import pytest

from backend.app.brokers import BrokerAdapterError, BrokerOrderResult, BrokerOrderStatus, BrokerSync, FakeBrokerAdapter
from backend.app.orders import InternalOrderStatus, OrderManager, OrderManagerError
from backend.tests.fixtures.modern_order import DEFAULT_STRATEGY_ID, make_signal_plan_order
import backend.app.brokers.fake as fake_module


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _order_manager_and_order():
    manager = OrderManager()
    order = make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)
    return manager, order


def test_broker_adapter_cannot_create_orders_directly() -> None:
    adapter = FakeBrokerAdapter()

    with pytest.raises(BrokerAdapterError):
        adapter.submit_order(object())  # type: ignore[arg-type]


def test_accepted_result_updates_ledger() -> None:
    manager, order = _order_manager_and_order()
    result = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED]).submit_order(order)

    updated = BrokerSync(ledger=manager.ledger).apply_result(result)

    assert updated.status == InternalOrderStatus.ACCEPTED
    assert updated.filled_quantity == 0
    assert manager.ledger.get(order.order_id).status == InternalOrderStatus.ACCEPTED


def test_rejected_result_updates_ledger_with_reason() -> None:
    manager, order = _order_manager_and_order()
    result = FakeBrokerAdapter([BrokerOrderStatus.REJECTED]).submit_order(order)

    updated = BrokerSync(ledger=manager.ledger).apply_result(result)

    assert updated.status == InternalOrderStatus.REJECTED
    assert updated.reason == "fake_broker_rejected"
    assert updated.filled_quantity == 0


def test_partial_fill_updates_filled_quantity() -> None:
    manager, order = _order_manager_and_order()
    result = FakeBrokerAdapter([BrokerOrderStatus.PARTIAL_FILL]).submit_order(order)

    updated = BrokerSync(ledger=manager.ledger).apply_result(result)

    assert updated.status == InternalOrderStatus.PARTIALLY_FILLED
    assert updated.filled_quantity == 5


def test_filled_result_closes_order_lifecycle() -> None:
    manager, order = _order_manager_and_order()
    result = FakeBrokerAdapter([BrokerOrderStatus.FILLED]).submit_order(order)

    updated = BrokerSync(ledger=manager.ledger).apply_result(result)

    assert updated.status == InternalOrderStatus.FILLED
    assert updated.filled_quantity == order.quantity


def test_cancel_result_updates_ledger_cancel_state() -> None:
    manager, order = _order_manager_and_order()
    adapter = FakeBrokerAdapter([BrokerOrderStatus.ACCEPTED])
    adapter.submit_order(order)
    result = adapter.cancel_order(order)

    updated = BrokerSync(ledger=manager.ledger).apply_result(result)

    assert updated.status == InternalOrderStatus.CANCELED
    assert updated.canceled_at is not None
    assert updated.filled_quantity == 0
    assert adapter.canceled_broker_order_ids == [f"fake-broker-{order.client_order_id}"]


def test_attribution_remains_intact() -> None:
    manager, order = _order_manager_and_order()
    result = FakeBrokerAdapter([BrokerOrderStatus.FILLED]).submit_order(order)

    updated = BrokerSync(ledger=manager.ledger).apply_result(result)

    assert updated.account_id == ACCOUNT_ID
    assert updated.deployment_id == DEPLOYMENT_ID
    assert updated.strategy_id == DEFAULT_STRATEGY_ID
    assert updated.signal_plan_id == order.signal_plan_id
    assert updated.client_order_id == order.client_order_id
    assert manager.ledger.by_account(ACCOUNT_ID) == (updated,)
    assert manager.ledger.by_deployment(DEPLOYMENT_ID) == (updated,)


def test_broker_sync_rejects_mismatched_client_order_id() -> None:
    manager, order = _order_manager_and_order()
    result = BrokerOrderResult(
        order_id=order.order_id,
        client_order_id="utos-wrong",
        status=BrokerOrderStatus.ACCEPTED,
    )

    with pytest.raises(OrderManagerError):
        BrokerSync(ledger=manager.ledger).apply_result(result)


def test_no_real_broker_calls() -> None:
    source = inspect.getsource(fake_module)

    for forbidden in ["alpaca", "requests", "httpx", "websocket"]:
        assert forbidden not in source.lower()


def test_fake_adapter_lifecycle_methods_do_not_create_internal_orders() -> None:
    source = inspect.getsource(fake_module)

    assert "InternalOrder(" not in source

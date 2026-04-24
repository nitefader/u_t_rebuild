from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.app.brokers import BrokerAdapterError, BrokerOrderResult, BrokerOrderStatus, BrokerSync, FakeBrokerAdapter
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.orders import InternalOrderStatus, OrderManager, OrderManagerError
from backend.app.runtime import ExecutionIntent
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


def _order_manager_and_order():
    manager = OrderManager()
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())
    return manager, order


def test_broker_adapter_cannot_create_orders_directly() -> None:
    adapter = FakeBrokerAdapter()

    with pytest.raises(BrokerAdapterError):
        adapter.submit_order(_execution_intent())  # type: ignore[arg-type]


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


def test_attribution_remains_intact() -> None:
    manager, order = _order_manager_and_order()
    result = FakeBrokerAdapter([BrokerOrderStatus.FILLED]).submit_order(order)

    updated = BrokerSync(ledger=manager.ledger).apply_result(result)

    assert updated.account_id == ACCOUNT_ID
    assert updated.deployment_id == DEPLOYMENT_ID
    assert updated.program_id == PROGRAM_ID
    assert updated.client_order_id == order.client_order_id
    assert manager.ledger.by_account(ACCOUNT_ID) == (updated,)
    assert manager.ledger.by_deployment(DEPLOYMENT_ID) == (updated,)
    assert manager.ledger.by_program(PROGRAM_ID) == (updated,)


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

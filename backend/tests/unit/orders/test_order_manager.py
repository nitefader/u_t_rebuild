from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.orders import InternalOrderIntent, InternalOrderStatus, OrderLedger, OrderManager, OrderManagerError
from backend.app.runtime import ExecutionIntent
import backend.app.orders.manager as order_manager_module


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


def _execution_intent(
    *,
    deployment_id: UUID = DEPLOYMENT_ID,
    program_id: UUID = PROGRAM_ID,
    symbol: str = "spy",
    qty: float = 10,
    intent_type: IntentType = IntentType.ENTRY,
) -> ExecutionIntent:
    return ExecutionIntent(
        deployment_id=deployment_id,
        program_version_id=program_id,
        symbol=symbol,
        side=CandidateSide.LONG,
        intent_type=intent_type,
        qty=qty,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        signal_name="entry",
        reason="signal_condition_true",
        features_used={"5m.close[0]": 100.0},
        governor_approved=True,
        governor_reason="approved",
    )


def test_creates_internal_order_before_broker_submission() -> None:
    manager = OrderManager()

    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    assert order.order_id is not None
    assert order.status == InternalOrderStatus.CREATED
    assert order.intent == InternalOrderIntent.OPEN
    assert manager.ledger.get(order.order_id) == order


def test_client_order_id_format_is_correct() -> None:
    manager = OrderManager()

    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    assert order.client_order_id == "utos-11111111-aaaaaaaa-99999999-open-000001"
    assert re.fullmatch(r"utos-[0-9a-f]{8}-[0-9a-f]{8}-[0-9a-f]{8}-(open|close|tp|sl|scale)-\d{6}", order.client_order_id)


def test_rejects_invalid_intent() -> None:
    manager = OrderManager()

    with pytest.raises(OrderManagerError):
        manager.create_order(
            account_id=ACCOUNT_ID,
            execution_intent=_execution_intent(),
            order_intent="mystery",
        )


def test_preserves_attribution() -> None:
    manager = OrderManager()

    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent(symbol="qqq"))

    assert order.account_id == ACCOUNT_ID
    assert order.deployment_id == DEPLOYMENT_ID
    assert order.program_id == PROGRAM_ID
    assert order.symbol == "QQQ"
    assert order.quantity == 10
    assert order.order_type == OrderType.MARKET
    assert order.side == CandidateSide.LONG


def test_updates_order_status() -> None:
    manager = OrderManager()
    order = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent())

    updated = manager.update_status(order_id=order.order_id, status=InternalOrderStatus.PENDING_SUBMISSION)

    assert updated.status == InternalOrderStatus.PENDING_SUBMISSION
    assert manager.ledger.get(order.order_id).status == InternalOrderStatus.PENDING_SUBMISSION
    assert updated.updated_at >= order.updated_at


def test_supports_lookup_by_deployment_account_program() -> None:
    ledger = OrderLedger()
    manager = OrderManager(ledger=ledger)
    other_account_id = uuid4()
    other_deployment_id = uuid4()
    other_program_id = uuid4()
    first = manager.create_order(account_id=ACCOUNT_ID, execution_intent=_execution_intent(symbol="SPY"))
    second = manager.create_order(
        account_id=other_account_id,
        execution_intent=_execution_intent(
            deployment_id=other_deployment_id,
            program_id=other_program_id,
            symbol="QQQ",
        ),
    )

    assert ledger.by_account(ACCOUNT_ID) == (first,)
    assert ledger.by_deployment(DEPLOYMENT_ID) == (first,)
    assert ledger.by_program(PROGRAM_ID) == (first,)
    assert ledger.by_account(other_account_id) == (second,)
    assert ledger.by_deployment(other_deployment_id) == (second,)
    assert ledger.by_program(other_program_id) == (second,)


def test_creates_close_tp_sl_and_scale_intents() -> None:
    manager = OrderManager()
    close_order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(intent_type=IntentType.EXIT),
    )
    tp_order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.TAKE_PROFIT,
    )
    sl_order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.STOP_LOSS,
    )
    scale_order = manager.create_order(
        account_id=ACCOUNT_ID,
        execution_intent=_execution_intent(),
        order_intent=InternalOrderIntent.SCALE,
    )

    assert close_order.intent == InternalOrderIntent.CLOSE
    assert tp_order.intent == InternalOrderIntent.TAKE_PROFIT
    assert sl_order.intent == InternalOrderIntent.STOP_LOSS
    assert scale_order.intent == InternalOrderIntent.SCALE
    assert tp_order.client_order_id.endswith("-tp-000001")
    assert sl_order.client_order_id.endswith("-sl-000001")
    assert scale_order.client_order_id.endswith("-scale-000001")


def test_no_external_calls() -> None:
    source = inspect.getsource(order_manager_module)

    for forbidden in ["alpaca", "requests", "httpx", "websocket", "submit_order"]:
        assert forbidden not in source.lower()

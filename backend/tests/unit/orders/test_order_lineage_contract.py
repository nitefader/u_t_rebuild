from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.domain import CandidateSide, OrderType, TimeInForce
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderOrigin


def _base_order() -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "order_id": uuid4(),
        "client_order_id": "test-order",
        "account_id": uuid4(),
        "symbol": "SPY",
        "side": CandidateSide.LONG,
        "quantity": 1,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
        "intent": InternalOrderIntent.OPEN,
        "status": InternalOrderStatus.CREATED,
        "created_at": now,
        "updated_at": now,
    }


def test_signal_plan_order_requires_full_lineage() -> None:
    payload = {
        **_base_order(),
        "origin": OrderOrigin.SIGNAL_PLAN,
        "deployment_id": uuid4(),
        "strategy_id": uuid4(),
        "signal_plan_id": uuid4(),
    }

    with pytest.raises(ValidationError, match="signal plan orders require lineage fields"):
        InternalOrder(**payload)


def test_signal_plan_order_preserves_lineage() -> None:
    signal_plan_id = uuid4()
    payload = _base_order()
    payload["intent"] = InternalOrderIntent.TARGET
    order = InternalOrder(
        **payload,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        signal_plan_id=signal_plan_id,
        opening_signal_plan_id=signal_plan_id,
        current_signal_plan_id=signal_plan_id,
        position_lineage_id=uuid4(),
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        leg_label="T1",
        lifecycle_intent=InternalOrderIntent.TARGET.value,
    )

    assert order.signal_plan_id == signal_plan_id
    assert order.opening_signal_plan_id == signal_plan_id
    assert order.current_signal_plan_id == signal_plan_id
    assert order.leg_label == "T1"


def test_manual_operator_order_cannot_carry_signal_plan_lineage() -> None:
    payload = {
        **_base_order(),
        "origin": OrderOrigin.MANUAL_OPERATOR,
        "signal_plan_id": uuid4(),
    }

    with pytest.raises(ValidationError, match="manual operator orders cannot carry signal plan lineage"):
        InternalOrder(**payload)

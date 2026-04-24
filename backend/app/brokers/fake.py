from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from backend.app.orders import InternalOrder

from .models import BrokerAdapterError, BrokerOrderResult, BrokerOrderStatus


class FakeBrokerAdapter:
    """Deterministic broker boundary test double."""

    def __init__(self, scripted_results: Iterable[BrokerOrderStatus | BrokerOrderResult] | None = None) -> None:
        self._scripted_results: deque[BrokerOrderStatus | BrokerOrderResult] = deque(scripted_results or [])
        self.submitted_orders: list[InternalOrder] = []

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        if not isinstance(order, InternalOrder):
            raise BrokerAdapterError("broker adapter requires an already-created InternalOrder")
        self.submitted_orders.append(order)
        scripted = self._scripted_results.popleft() if self._scripted_results else BrokerOrderStatus.ACCEPTED
        if isinstance(scripted, BrokerOrderResult):
            if scripted.order_id != order.order_id or scripted.client_order_id != order.client_order_id:
                raise BrokerAdapterError("scripted broker result does not match submitted internal order")
            return scripted
        return self._result_for_status(order, scripted)

    def _result_for_status(self, order: InternalOrder, status: BrokerOrderStatus) -> BrokerOrderResult:
        if status == BrokerOrderStatus.ACCEPTED:
            filled_quantity = 0
            reason = None
        elif status == BrokerOrderStatus.REJECTED:
            filled_quantity = 0
            reason = "fake_broker_rejected"
        elif status == BrokerOrderStatus.PARTIAL_FILL:
            filled_quantity = order.quantity / 2
            reason = None
        elif status == BrokerOrderStatus.FILLED:
            filled_quantity = order.quantity
            reason = None
        else:
            raise BrokerAdapterError(f"unsupported fake broker status: {status}")
        return BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=status,
            filled_quantity=filled_quantity,
            reason=reason,
            broker_reference=f"fake-{order.client_order_id}",
        )

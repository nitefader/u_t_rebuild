from __future__ import annotations

from backend.app.orders import InternalOrder, InternalOrderStatus, OrderLedger, OrderManagerError

from .models import BrokerOrderResult, BrokerOrderStatus


class BrokerSync:
    """Apply broker boundary results to the internal OrderLedger."""

    def __init__(self, *, ledger: OrderLedger) -> None:
        self._ledger = ledger

    def apply_result(self, result: BrokerOrderResult) -> InternalOrder:
        order = self._ledger.get(result.order_id)
        if order.client_order_id != result.client_order_id:
            raise OrderManagerError("broker result client_order_id does not match internal order")
        status = self._map_status(result.status)
        filled_quantity = result.filled_quantity
        if result.status == BrokerOrderStatus.FILLED:
            filled_quantity = order.quantity
        if filled_quantity > order.quantity:
            raise OrderManagerError("broker result filled_quantity exceeds internal order quantity")
        updated = order.model_copy(
            update={
                "status": status,
                "filled_quantity": filled_quantity,
                "updated_at": result.received_at,
                "reason": result.reason if result.reason is not None else order.reason,
            }
        )
        return self._ledger.replace(updated)

    def _map_status(self, status: BrokerOrderStatus) -> InternalOrderStatus:
        if status == BrokerOrderStatus.ACCEPTED:
            return InternalOrderStatus.ACCEPTED
        if status == BrokerOrderStatus.REJECTED:
            return InternalOrderStatus.REJECTED
        if status == BrokerOrderStatus.PARTIAL_FILL:
            return InternalOrderStatus.PARTIALLY_FILLED
        if status == BrokerOrderStatus.FILLED:
            return InternalOrderStatus.FILLED
        raise OrderManagerError(f"unsupported broker status: {status}")

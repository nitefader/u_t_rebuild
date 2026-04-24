from __future__ import annotations

from uuid import UUID

from backend.app.orders import InternalOrder, InternalOrderStatus, OrderLedger, OrderManagerError

from .adapter import BrokerAdapter
from .models import BrokerAccountSnapshot, BrokerOrderResult, BrokerOrderStatus, BrokerPositionSnapshot


class BrokerSync:
    """Apply broker boundary results to the internal OrderLedger."""

    def __init__(self, *, ledger: OrderLedger, adapter: BrokerAdapter | None = None) -> None:
        self._ledger = ledger
        self._adapter = adapter

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

    def sync_open_orders(self, account_id: UUID) -> tuple[InternalOrder, ...]:
        adapter = self._require_adapter()
        updates: list[InternalOrder] = []
        for result in adapter.list_open_orders(account_id):
            updates.append(self.apply_result(result))
        return tuple(updates)

    def sync_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return self._require_adapter().get_positions(account_id)

    def sync_account(self, account_id: UUID) -> BrokerAccountSnapshot:
        return self._require_adapter().get_account_snapshot(account_id)

    def _map_status(self, status: BrokerOrderStatus) -> InternalOrderStatus:
        if status == BrokerOrderStatus.ACCEPTED:
            return InternalOrderStatus.ACCEPTED
        if status == BrokerOrderStatus.REJECTED:
            return InternalOrderStatus.REJECTED
        if status == BrokerOrderStatus.PARTIAL_FILL:
            return InternalOrderStatus.PARTIALLY_FILLED
        if status == BrokerOrderStatus.FILLED:
            return InternalOrderStatus.FILLED
        if status == BrokerOrderStatus.CANCELED:
            return InternalOrderStatus.CANCELED
        if status in {
            BrokerOrderStatus.EXPIRED,
            BrokerOrderStatus.PENDING_CANCEL,
            BrokerOrderStatus.REPLACED,
            BrokerOrderStatus.SUSPENDED,
            BrokerOrderStatus.DONE_FOR_DAY,
        }:
            return InternalOrderStatus.SUBMITTED
        raise OrderManagerError(f"unsupported broker status: {status}")

    def _require_adapter(self) -> BrokerAdapter:
        if self._adapter is None:
            raise OrderManagerError("broker sync read operation requires a broker adapter")
        return self._adapter

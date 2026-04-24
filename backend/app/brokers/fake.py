from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from uuid import UUID

from backend.app.orders import InternalOrder

from .models import (
    BrokerAccountMode,
    BrokerAccountSnapshot,
    BrokerAdapterError,
    BrokerOpenOrderSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSnapshot,
)


class FakeBrokerAdapter:
    """Deterministic broker boundary test double."""

    def __init__(
        self,
        scripted_results: Iterable[BrokerOrderStatus | BrokerOrderResult] | None = None,
        *,
        account_snapshots: dict[UUID, BrokerAccountSnapshot] | None = None,
        positions_by_account: dict[UUID, tuple[BrokerPositionSnapshot, ...]] | None = None,
        open_orders_by_account: dict[UUID, tuple[BrokerOrderResult, ...]] | None = None,
    ) -> None:
        self._scripted_results: deque[BrokerOrderStatus | BrokerOrderResult] = deque(scripted_results or [])
        self._account_snapshots = account_snapshots or {}
        self._positions_by_account = positions_by_account or {}
        self._open_orders_by_account = open_orders_by_account or {}
        self._results_by_order_id: dict[UUID, BrokerOrderResult] = {}
        self.submitted_orders: list[InternalOrder] = []
        self.canceled_client_order_ids: list[str] = []
        self.canceled_broker_order_ids: list[str] = []
        self.replaced_broker_order_ids: list[str] = []

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        if not isinstance(order, InternalOrder):
            raise BrokerAdapterError("broker adapter requires an already-created InternalOrder")
        self.submitted_orders.append(order)
        scripted = self._scripted_results.popleft() if self._scripted_results else BrokerOrderStatus.ACCEPTED
        if isinstance(scripted, BrokerOrderResult):
            if scripted.order_id != order.order_id or scripted.client_order_id != order.client_order_id:
                raise BrokerAdapterError("scripted broker result does not match submitted internal order")
            self._results_by_order_id[order.order_id] = scripted
            return scripted
        result = self._result_for_status(order, scripted)
        self._results_by_order_id[order.order_id] = result
        return result

    def get_order(self, order: InternalOrder) -> BrokerOrderResult:
        if not isinstance(order, InternalOrder):
            raise BrokerAdapterError("broker adapter requires an already-created InternalOrder")
        try:
            return self._results_by_order_id[order.order_id]
        except KeyError as exc:
            raise BrokerAdapterError(f"fake broker has no order result for {order.order_id}") from exc

    def cancel_order(self, order: InternalOrder) -> BrokerOrderResult:
        if not isinstance(order, InternalOrder):
            raise BrokerAdapterError("broker adapter requires an already-created InternalOrder")
        current = self.get_order(order)
        if not current.broker_order_id:
            raise BrokerAdapterError("cancel requires broker_order_id")
        self.canceled_broker_order_ids.append(current.broker_order_id)
        self.canceled_client_order_ids.append(order.client_order_id)
        result = current.model_copy(
            update={
                "status": BrokerOrderStatus.CANCELED,
                "broker_status": BrokerOrderStatus.CANCELED.value,
                "remaining_quantity": max(order.quantity - current.filled_quantity, 0),
                "canceled_at": current.received_at,
                "raw_status": BrokerOrderStatus.CANCELED.value,
            }
        )
        self._results_by_order_id[order.order_id] = result
        return result

    def cancel_orders(self, account_id: UUID, scope: str) -> tuple[BrokerOrderResult, ...]:
        _ = scope
        results: list[BrokerOrderResult] = []
        open_order_ids = {
            snapshot.client_order_id
            for snapshot in self.list_open_orders(account_id)
        }
        for order in self.submitted_orders:
            if order.account_id == account_id and order.client_order_id in open_order_ids:
                results.append(self.cancel_order(order))
        return tuple(results)

    def replace_order(self, order: InternalOrder, new_params: Mapping[str, object]) -> BrokerOrderResult:
        if not isinstance(order, InternalOrder):
            raise BrokerAdapterError("broker adapter requires an already-created InternalOrder")
        _ = dict(new_params)
        current = self.get_order(order)
        if not current.broker_order_id:
            raise BrokerAdapterError("replace requires broker_order_id")
        self.replaced_broker_order_ids.append(current.broker_order_id)
        result = current.model_copy(
            update={
                "status": BrokerOrderStatus.ACCEPTED,
                "broker_status": BrokerOrderStatus.ACCEPTED.value,
                "raw_status": BrokerOrderStatus.ACCEPTED.value,
            }
        )
        self._results_by_order_id[order.order_id] = result
        return result

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        if account_id in self._open_orders_by_account:
            return tuple(self._snapshot_from_result(result, account_id=account_id) for result in self._open_orders_by_account[account_id])
        open_statuses = {BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.PARTIAL_FILL}
        return tuple(
            self._snapshot_from_result(result, account_id=account_id)
            for order in self.submitted_orders
            if order.account_id == account_id
            for result in [self._results_by_order_id[order.order_id]]
            if result.status in open_statuses
        )

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        return self._account_snapshots.get(
            account_id,
            BrokerAccountSnapshot(
                account_id=account_id,
                provider="fake",
                mode=BrokerAccountMode.PAPER,
                buying_power=100_000,
                cash=100_000,
                equity=100_000,
                daytrading_buying_power=100_000,
                account_status="ACTIVE",
                shorting_enabled=False,
            ),
        )

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return self._positions_by_account.get(account_id, ())

    def cancel_client_order_id(self, client_order_id: str) -> None:
        self.canceled_client_order_ids.append(client_order_id)

    def _snapshot_from_result(self, result: BrokerOrderResult, *, account_id: UUID) -> BrokerOpenOrderSnapshot:
        matching_order = next(
            (order for order in self.submitted_orders if order.order_id == result.order_id),
            None,
        )
        return BrokerOpenOrderSnapshot(
            account_id=account_id,
            broker_order_id=result.broker_order_id or result.client_order_id,
            client_order_id=result.client_order_id,
            symbol=matching_order.symbol if matching_order is not None else "UNKNOWN",
            side=matching_order.side.value if matching_order is not None else "unknown",
            qty=matching_order.quantity if matching_order is not None else max(result.remaining_quantity or 0, 1),
            filled_qty=result.filled_quantity,
            status=result.status,
            order_type=matching_order.order_type.value if matching_order is not None else "unknown",
            limit_price=matching_order.limit_price if matching_order is not None else None,
            stop_price=matching_order.stop_price if matching_order is not None else None,
            timestamp=result.updated_at or result.received_at,
        )

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
            broker_order_id=f"fake-broker-{order.client_order_id}",
            broker_status=status.value,
            filled_quantity=filled_quantity,
            filled_avg_price=100.0 if filled_quantity else None,
            remaining_quantity=order.quantity - filled_quantity,
            reason=reason,
            raw_status=status.value,
            broker_reference=f"fake-{order.client_order_id}",
        )

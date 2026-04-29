from __future__ import annotations

from uuid import UUID

from backend.app.domain._base import utc_now

from .models import InternalOrder, InternalOrderStatus, OrderManagerError


class OrderLedger:
    """In-memory internal order state store.

    This is intentionally not a broker adapter and not persistence. It is the
    first internal source of truth that broker integration will write through.
    """

    def __init__(self) -> None:
        self._orders_by_id: dict[UUID, InternalOrder] = {}
        self._order_ids_by_account: dict[UUID, list[UUID]] = {}
        self._order_ids_by_deployment: dict[UUID, list[UUID]] = {}
        self._order_ids_by_program: dict[UUID, list[UUID]] = {}

    def add(self, order: InternalOrder) -> InternalOrder:
        if order.order_id in self._orders_by_id:
            raise OrderManagerError(f"internal order already exists: {order.order_id}")
        self._orders_by_id[order.order_id] = order
        self._order_ids_by_account.setdefault(order.account_id, []).append(order.order_id)
        if order.deployment_id is not None:
            self._order_ids_by_deployment.setdefault(order.deployment_id, []).append(order.order_id)
        if order.program_id is not None:
            self._order_ids_by_program.setdefault(order.program_id, []).append(order.order_id)
        return order

    def get(self, order_id: UUID) -> InternalOrder:
        try:
            return self._orders_by_id[order_id]
        except KeyError as exc:
            raise OrderManagerError(f"unknown internal order: {order_id}") from exc

    def update_status(
        self,
        *,
        order_id: UUID,
        status: InternalOrderStatus,
        reason: str | None = None,
    ) -> InternalOrder:
        order = self.get(order_id)
        updated = order.model_copy(
            update={
                "status": status,
                "updated_at": utc_now(),
                "reason": reason if reason is not None else order.reason,
            }
        )
        self._orders_by_id[order_id] = updated
        return updated

    def replace(self, order: InternalOrder) -> InternalOrder:
        self.get(order.order_id)
        self._orders_by_id[order.order_id] = order
        return order

    def by_account(self, account_id: UUID) -> tuple[InternalOrder, ...]:
        return self._orders_for(self._order_ids_by_account.get(account_id, []))

    def by_deployment(self, deployment_id: UUID) -> tuple[InternalOrder, ...]:
        return self._orders_for(self._order_ids_by_deployment.get(deployment_id, []))

    def by_program(self, program_id: UUID) -> tuple[InternalOrder, ...]:
        return self._orders_for(self._order_ids_by_program.get(program_id, []))

    def by_client_order_id(self, client_order_id: str) -> InternalOrder | None:
        for order in self._orders_by_id.values():
            if order.client_order_id == client_order_id:
                return order
        return None

    def all(self) -> tuple[InternalOrder, ...]:
        return tuple(self._orders_by_id.values())

    def _orders_for(self, order_ids: list[UUID]) -> tuple[InternalOrder, ...]:
        return tuple(self._orders_by_id[order_id] for order_id in order_ids)

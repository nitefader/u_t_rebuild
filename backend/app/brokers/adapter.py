from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable
from uuid import UUID

from backend.app.orders import InternalOrder

from .models import BrokerAccountSnapshot, BrokerOpenOrderSnapshot, BrokerOrderResult, BrokerPositionSnapshot


@runtime_checkable
class BrokerAdapter(Protocol):
    """Boundary for broker implementations.

    Adapters receive internal orders that already exist in the OrderLedger.
    They do not create internal orders, assign attribution, or own lifecycle
    state.
    """

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        """Submit an already-created internal order to a broker boundary."""

    def get_order(self, order: InternalOrder) -> BrokerOrderResult:
        """Fetch broker truth for an already-created internal order."""

    def cancel_order(self, order: InternalOrder) -> BrokerOrderResult:
        """Cancel an existing broker order by broker_order_id."""

    def cancel_orders(self, account_id: UUID, scope: str) -> tuple[BrokerOrderResult, ...]:
        """Cancel broker orders in the already selected broker-side scope."""

    def replace_order(self, order: InternalOrder, new_params: Mapping[str, object]) -> BrokerOrderResult:
        """Replace an existing broker order by broker_order_id."""

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOpenOrderSnapshot, ...]:
        """Fetch open broker orders for an account."""

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        """Fetch external broker account truth."""

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        """Fetch external broker position truth."""

from __future__ import annotations

from typing import Protocol

from backend.app.orders import InternalOrder

from .models import BrokerOrderResult


class BrokerAdapter(Protocol):
    """Boundary for broker implementations.

    Adapters receive internal orders that already exist in the OrderLedger.
    They do not create internal orders, assign attribution, or own lifecycle
    state.
    """

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        """Submit an already-created internal order to a broker boundary."""

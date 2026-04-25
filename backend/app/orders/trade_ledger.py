"""Canonical in-memory trade ledger for broker-sourced fills (Phase 2 §11.4).

Until this module landed, the ``trade_ledger`` slot on ``BrokerSyncService``
was duck-typed: callers either provided a snapshot recorder, the SQLite
persistence adapter, or a simulation ledger. ``TradeLedger`` is the canonical
shape — one ``Trade`` record per ``BrokerFillUpdateEvent`` — that the live
broker sync service writes through. Persistence and simulation ledgers keep
their own representations; the in-memory ledger here is the runtime source
of truth referenced by reconciliation tests and operator views.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers.models import BrokerFillUpdateEvent


class Trade(BaseModel):
    """One broker fill, normalized for internal use.

    A ``Trade`` is an immutable record of an execution at the broker. Multiple
    partial fills for one internal order produce multiple ``Trade`` records
    keyed by ``broker_execution_id`` when the broker provides one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    trade_id: str
    account_id: UUID
    symbol: str
    qty: float = Field(gt=0)
    price: float = Field(ge=0)
    side: str
    client_order_id: str
    broker_order_id: str | None = None
    broker_execution_id: str | None = None
    executed_at: datetime
    order_id: UUID | None = None


class TradeLedger:
    """In-memory ledger of broker-sourced fills.

    The ledger is append-only — fills, like broker history, are not retracted.
    Use ``record_fill`` from inside ``BrokerSyncService.handle_fill_update``
    when a ``BrokerFillUpdateEvent`` arrives over the stream.
    """

    def __init__(self) -> None:
        self._trades: list[Trade] = []
        self._trades_by_execution_id: dict[str, Trade] = {}

    def record_fill(
        self,
        event: BrokerFillUpdateEvent,
        *,
        order_id: UUID | None = None,
    ) -> Trade:
        if event.broker_execution_id is not None:
            existing = self._trades_by_execution_id.get(event.broker_execution_id)
            if existing is not None:
                return existing
        trade = Trade(
            trade_id=f"TRD-{len(self._trades) + 1:06d}",
            account_id=event.account_id,
            symbol=event.symbol.upper(),
            qty=event.qty,
            price=event.price,
            side=event.side,
            client_order_id=event.client_order_id,
            broker_order_id=event.broker_order_id,
            broker_execution_id=event.broker_execution_id,
            executed_at=event.event_at,
            order_id=order_id,
        )
        self._trades.append(trade)
        if trade.broker_execution_id is not None:
            self._trades_by_execution_id[trade.broker_execution_id] = trade
        return trade

    def all(self) -> tuple[Trade, ...]:
        return tuple(self._trades)

    def by_account(self, account_id: UUID) -> tuple[Trade, ...]:
        return tuple(trade for trade in self._trades if trade.account_id == account_id)

    def by_symbol(self, symbol: str) -> tuple[Trade, ...]:
        normalized = symbol.upper()
        return tuple(trade for trade in self._trades if trade.symbol == normalized)

    def by_client_order_id(self, client_order_id: str) -> tuple[Trade, ...]:
        return tuple(trade for trade in self._trades if trade.client_order_id == client_order_id)

    def by_order_id(self, order_id: UUID) -> tuple[Trade, ...]:
        return tuple(trade for trade in self._trades if trade.order_id == order_id)

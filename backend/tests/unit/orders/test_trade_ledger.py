from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.brokers import BrokerFillUpdateEvent
from backend.app.orders import Trade, TradeLedger


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_ACCOUNT_ID = UUID("99999999-8888-7777-6666-555555555555")


def _fill(
    *,
    client_order_id: str = "client-1",
    symbol: str = "SPY",
    qty: float = 5,
    price: float = 100,
    broker_execution_id: str | None = "exec-1",
    side: str = "buy",
    account_id: UUID = ACCOUNT_ID,
    event_at: datetime | None = None,
) -> BrokerFillUpdateEvent:
    return BrokerFillUpdateEvent(
        account_id=account_id,
        client_order_id=client_order_id,
        symbol=symbol,
        qty=qty,
        price=price,
        side=side,
        broker_order_id=f"broker-{client_order_id}",
        broker_execution_id=broker_execution_id,
        event_at=event_at or datetime(2026, 4, 23, 14, 30, tzinfo=timezone.utc),
    )


def test_record_fill_appends_a_trade() -> None:
    ledger = TradeLedger()
    fill = _fill()

    trade = ledger.record_fill(fill)

    assert isinstance(trade, Trade)
    assert trade.trade_id == "TRD-000001"
    assert trade.account_id == ACCOUNT_ID
    assert trade.symbol == "SPY"
    assert trade.qty == 5
    assert trade.price == 100
    assert trade.broker_execution_id == "exec-1"
    assert trade.executed_at == fill.event_at


def test_record_fill_is_idempotent_by_broker_execution_id() -> None:
    """Re-delivered stream events must not double-record the trade."""
    ledger = TradeLedger()
    fill = _fill()

    first = ledger.record_fill(fill)
    second = ledger.record_fill(fill)

    assert first is second
    assert ledger.all() == (first,)


def test_record_fill_records_each_event_when_no_execution_id() -> None:
    ledger = TradeLedger()

    a = ledger.record_fill(_fill(broker_execution_id=None, qty=2))
    b = ledger.record_fill(_fill(broker_execution_id=None, qty=3))

    assert a.trade_id == "TRD-000001"
    assert b.trade_id == "TRD-000002"
    assert len(ledger.all()) == 2


def test_record_fill_attaches_internal_order_id() -> None:
    ledger = TradeLedger()
    order_id = uuid4()

    trade = ledger.record_fill(_fill(), order_id=order_id)

    assert trade.order_id == order_id
    assert ledger.by_order_id(order_id) == (trade,)


def test_lookup_by_account_symbol_and_client_order_id() -> None:
    ledger = TradeLedger()
    spy_buy = ledger.record_fill(_fill(client_order_id="client-spy", symbol="spy", broker_execution_id="exec-1"))
    qqq_buy = ledger.record_fill(
        _fill(client_order_id="client-qqq", symbol="QQQ", broker_execution_id="exec-2")
    )
    other_account = ledger.record_fill(
        _fill(account_id=OTHER_ACCOUNT_ID, symbol="IWM", broker_execution_id="exec-3")
    )

    assert ledger.by_account(ACCOUNT_ID) == (spy_buy, qqq_buy)
    assert ledger.by_account(OTHER_ACCOUNT_ID) == (other_account,)
    assert ledger.by_symbol("spy") == (spy_buy,)
    assert ledger.by_symbol("IWM") == (other_account,)
    assert ledger.by_client_order_id("client-qqq") == (qqq_buy,)


def test_trade_is_immutable() -> None:
    ledger = TradeLedger()
    trade = ledger.record_fill(_fill())

    try:
        trade.qty = 999  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("Trade should be frozen")

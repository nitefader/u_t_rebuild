from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import AlpacaBrokerAdapter, AlpacaBrokerError, BrokerOrderStatus, BrokerPositionSide
from backend.app.domain import CandidateSide, OrderType, TimeInForce
from backend.app.domain._base import utc_now
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus
from backend.app.runtime import ExecutionIntent
import backend.app.brokers.alpaca as alpaca_module


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


class FakeOrderRequest:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class FakeAlpacaClient:
    def __init__(self, *, submit_response: dict | None = None, existing_order: dict | None = None) -> None:
        self.submit_response = submit_response or _alpaca_order(status="new")
        self.existing_order = existing_order
        self.submit_order_calls = 0
        self.get_order_calls = 0
        self.submitted_order_data = None

    def submit_order(self, *, order_data):
        self.submit_order_calls += 1
        self.submitted_order_data = order_data
        return self.submit_response

    def get_order_by_client_id(self, client_order_id: str):
        self.get_order_calls += 1
        if self.existing_order is None:
            raise RuntimeError("order not found")
        payload = dict(self.existing_order)
        payload["client_order_id"] = client_order_id
        return payload

    def get_orders(self):
        return [
            _alpaca_order(status="new"),
            _alpaca_order(status="partially_filled", filled_qty="4", broker_id="alpaca-open-2"),
            _alpaca_order(status="filled", broker_id="alpaca-filled"),
        ]

    def get_account(self):
        return {
            "buying_power": "50000",
            "daytrading_buying_power": "45000",
            "cash": "25000",
            "equity": "55000",
            "trading_blocked": False,
            "account_blocked": False,
            "pattern_day_trader": False,
            "shorting_enabled": True,
            "status": "ACTIVE",
        }

    def get_all_positions(self):
        return [
            {"symbol": "spy", "qty": "10", "market_value": "1000", "avg_entry_price": "100", "unrealized_pl": "12.50"},
            {"symbol": "qqq", "qty": "-2", "market_value": "-800", "avg_entry_price": "400", "unrealized_pl": "-5"},
        ]


def _alpaca_order(
    *,
    status: str,
    filled_qty: str = "0",
    avg_price: str | None = None,
    broker_id: str = "alpaca-order-1",
) -> dict:
    return {
        "id": broker_id,
        "client_order_id": "utos-11111111-aaaaaaaa-99999999-open-000001",
        "symbol": "SPY",
        "side": "buy",
        "type": "market",
        "qty": "10",
        "status": status,
        "filled_qty": filled_qty,
        "filled_avg_price": avg_price,
        "submitted_at": "2026-01-02T14:30:00Z",
        "updated_at": "2026-01-02T14:31:00Z",
        "filled_at": "2026-01-02T14:31:00Z" if status == "filled" else None,
        "rejected_reason": "invalid order" if status == "rejected" else None,
    }


def _order() -> InternalOrder:
    now = utc_now()
    return InternalOrder(
        order_id=uuid4(),
        client_order_id="utos-11111111-aaaaaaaa-99999999-open-000001",
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        program_id=PROGRAM_ID,
        symbol="SPY",
        side=CandidateSide.LONG,
        quantity=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


def _adapter(client: FakeAlpacaClient) -> AlpacaBrokerAdapter:
    from backend.app.domain import TradingMode
    return AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER, trading_client=client)


def test_submit_market_order_success(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeOrderRequest)
    client = FakeAlpacaClient(submit_response=_alpaca_order(status="new"))

    result = _adapter(client).submit_order(_order())

    assert result.status == BrokerOrderStatus.ACCEPTED
    assert result.broker_order_id == "alpaca-order-1"
    assert client.submit_order_calls == 1
    assert client.submitted_order_data.kwargs["client_order_id"] == "utos-11111111-aaaaaaaa-99999999-open-000001"
    assert client.submitted_order_data.kwargs["symbol"] == "SPY"
    assert client.submitted_order_data.kwargs["qty"] == 10


def test_partial_fill_mapping() -> None:
    result = _adapter(FakeAlpacaClient()).order_response_to_result(
        order=_order(),
        response=_alpaca_order(status="partially_filled", filled_qty="4", avg_price="100.25"),
    )

    assert result.status == BrokerOrderStatus.PARTIAL_FILL
    assert result.filled_quantity == 4
    assert result.remaining_quantity == 6
    assert result.filled_avg_price == 100.25


def test_full_fill_mapping() -> None:
    result = _adapter(FakeAlpacaClient()).order_response_to_result(
        order=_order(),
        response=_alpaca_order(status="filled", filled_qty="10", avg_price="100.50"),
    )

    assert result.status == BrokerOrderStatus.FILLED
    assert result.filled_quantity == 10
    assert result.remaining_quantity == 0


def test_rejected_order_mapping() -> None:
    result = _adapter(FakeAlpacaClient()).order_response_to_result(
        order=_order(),
        response=_alpaca_order(status="rejected"),
    )

    assert result.status == BrokerOrderStatus.REJECTED
    assert result.reason == "invalid order"


def test_idempotent_submission_fetches_existing_order(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeOrderRequest)
    client = FakeAlpacaClient(existing_order=_alpaca_order(status="accepted", broker_id="alpaca-existing"))

    result = _adapter(client).submit_order(_order())

    assert result.broker_order_id == "alpaca-existing"
    assert result.status == BrokerOrderStatus.ACCEPTED
    assert client.get_order_calls == 1
    assert client.submit_order_calls == 0


def test_account_snapshot_mapping() -> None:
    snapshot = _adapter(FakeAlpacaClient()).get_account_snapshot(ACCOUNT_ID)

    assert snapshot.account_id == ACCOUNT_ID
    assert snapshot.provider == "alpaca"
    assert snapshot.buying_power == 50_000
    assert snapshot.equity == 55_000
    assert snapshot.shorting_enabled is True


def test_positions_snapshot_mapping() -> None:
    positions = _adapter(FakeAlpacaClient()).get_positions(ACCOUNT_ID)

    assert positions[0].symbol == "SPY"
    assert positions[0].side == BrokerPositionSide.LONG
    assert positions[1].symbol == "QQQ"
    assert positions[1].side == BrokerPositionSide.SHORT


def test_open_orders_mapping() -> None:
    open_orders = _adapter(FakeAlpacaClient()).list_open_orders(ACCOUNT_ID)

    assert [order.status for order in open_orders] == [BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.PARTIAL_FILL]
    assert open_orders[0].client_order_id == "utos-11111111-aaaaaaaa-99999999-open-000001"


def test_unknown_status_fails_closed() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        _adapter(FakeAlpacaClient()).order_response_to_result(order=_order(), response=_alpaca_order(status="mystery"))

    assert exc_info.value.details.code == "unknown_order_status"
    assert exc_info.value.details.retryable is False


def test_adapter_never_creates_internal_order() -> None:
    source = inspect.getsource(alpaca_module.AlpacaBrokerAdapter)
    assert "InternalOrder(" not in source

    intent = ExecutionIntent(
        deployment_id=DEPLOYMENT_ID,
        program_version_id=PROGRAM_ID,
        symbol="SPY",
        side=CandidateSide.LONG,
        intent_type="entry",
        qty=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        signal_name="entry",
        reason="signal_condition_true",
        governor_approved=True,
    )
    with pytest.raises(AlpacaBrokerError):
        _adapter(FakeAlpacaClient()).submit_order(intent)  # type: ignore[arg-type]

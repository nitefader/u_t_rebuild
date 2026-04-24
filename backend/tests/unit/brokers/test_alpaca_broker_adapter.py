from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import (
    AlpacaBrokerAdapter,
    AlpacaBrokerError,
    BrokerAdapter,
    BrokerOpenOrderSnapshot,
    BrokerOrderStatus,
    BrokerPositionSide,
)
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.domain._base import utc_now
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus
from backend.app.runtime import ExecutionIntent
import backend.app.brokers.alpaca as alpaca_module

try:
    from alpaca.trading.enums import OrderStatus
except ImportError:  # pragma: no cover - local fallback when alpaca-py is unavailable.
    class OrderStatus(Enum):
        PENDING_NEW = "pending_new"


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


def _order(*, order_type: OrderType = OrderType.MARKET, limit_price: float | None = None) -> InternalOrder:
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
        order_type=order_type,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


class FakeTradingClient:
    def __init__(self, response: dict | None = None, *, existing_order: dict | None = None) -> None:
        self.response = response or {
            "id": "alpaca-order-1",
            "client_order_id": "utos-11111111-aaaaaaaa-99999999-open-000001",
            "status": "new",
            "filled_qty": "0",
            "qty": "10",
        }
        self.existing_order = existing_order
        self.submitted_order_data = None
        self.get_order_calls = 0
        self.submit_order_calls = 0

    def submit_order(self, *, order_data):
        self.submit_order_calls += 1
        self.submitted_order_data = order_data
        return self.response

    def get_order_by_client_id(self, client_order_id: str):
        self.get_order_calls += 1
        if self.existing_order is None:
            raise RuntimeError("order not found")
        payload = dict(self.existing_order)
        payload["client_order_id"] = client_order_id
        return payload

    def get_orders(self):
        return [self.response]

    def get_account(self):
        return {"buying_power": "50000", "cash": "25000", "equity": "55000"}

    def get_all_positions(self):
        return [{"symbol": "SPY", "qty": "10", "market_value": "1000", "avg_entry_price": "100"}]


class FakeOrderRequest:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def _adapter(response: dict | None = None) -> AlpacaBrokerAdapter:
    return AlpacaBrokerAdapter(trading_client=FakeTradingClient(response=response), load_env=False)


def test_adapter_implements_broker_adapter_protocol() -> None:
    assert isinstance(_adapter(), BrokerAdapter)


def test_market_order_translation_correct() -> None:
    request = _adapter().translate_order_request(_order(order_type=OrderType.MARKET))

    assert request == {
        "symbol": "SPY",
        "qty": 10.0,
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
        "client_order_id": "utos-11111111-aaaaaaaa-99999999-open-000001",
    }


def test_limit_order_translation_rejected_for_v1_safe_path() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        _adapter().translate_order_request(_order(order_type=OrderType.LIMIT, limit_price=101.25))

    assert exc_info.value.details.code == "submit_supports_market_only"


def test_invalid_unsupported_order_type_rejected() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        _adapter().translate_order_request(_order(order_type=OrderType.STOP))

    assert exc_info.value.details.code == "submit_supports_market_only"


def test_status_normalization_works() -> None:
    adapter = _adapter()

    assert adapter.normalize_status("pending_new") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status(OrderStatus.PENDING_NEW) == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("OrderStatus.PENDING_NEW") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("new") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("accepted") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("partially_filled") == BrokerOrderStatus.PARTIAL_FILL
    assert adapter.normalize_status("filled") == BrokerOrderStatus.FILLED
    assert adapter.normalize_status("rejected") == BrokerOrderStatus.REJECTED
    assert adapter.normalize_status("canceled") == BrokerOrderStatus.CANCELED
    assert adapter.normalize_status("expired") == BrokerOrderStatus.EXPIRED
    assert adapter.normalize_status("pending_cancel") == BrokerOrderStatus.PENDING_CANCEL
    assert adapter.normalize_status("pending_replace") == BrokerOrderStatus.REPLACED
    assert adapter.normalize_status("done_for_day") == BrokerOrderStatus.ACCEPTED


def test_unknown_status_returns_controlled_failure() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        _adapter().normalize_status("mystery_status")

    assert exc_info.value.details.code == "unknown_order_status"


def test_order_response_normalization_works() -> None:
    order = _order()
    response = {
        "id": "alpaca-order-1",
        "client_order_id": order.client_order_id,
        "status": "filled",
        "filled_qty": "10",
        "filled_avg_price": "100.50",
        "submitted_at": "2026-01-02T14:30:00Z",
        "updated_at": "2026-01-02T14:31:00Z",
        "filled_at": "2026-01-02T14:31:00Z",
    }

    result = _adapter().order_response_to_result(order=order, response=response)

    assert result.status == BrokerOrderStatus.FILLED
    assert result.broker_order_id == "alpaca-order-1"
    assert result.broker_status == "filled"
    assert result.filled_quantity == 10
    assert result.filled_avg_price == 100.50
    assert result.remaining_quantity == 0


def test_account_snapshot_normalization_works() -> None:
    snapshot = _adapter().account_response_to_snapshot(
        account_id=ACCOUNT_ID,
        response={
            "buying_power": "50000",
            "cash": "25000",
            "equity": "55000",
            "trading_blocked": False,
            "account_blocked": False,
            "pattern_day_trader": True,
            "shorting_enabled": True,
        },
    )

    assert snapshot.account_id == ACCOUNT_ID
    assert snapshot.provider == "alpaca"
    assert snapshot.mode == TradingMode.BROKER_PAPER
    assert snapshot.buying_power == 50_000
    assert snapshot.pattern_day_trader is True
    assert snapshot.shorting_enabled is True


def test_position_snapshot_normalization_works() -> None:
    long_snapshot = _adapter().position_response_to_snapshot(
        account_id=ACCOUNT_ID,
        response={"symbol": "spy", "qty": "10", "market_value": "1000", "avg_entry_price": "100"},
    )
    short_snapshot = _adapter().position_response_to_snapshot(
        account_id=ACCOUNT_ID,
        response={"symbol": "qqq", "qty": "-5", "market_value": "-500", "avg_entry_price": "100"},
    )

    assert long_snapshot.symbol == "SPY"
    assert long_snapshot.side == BrokerPositionSide.LONG
    assert long_snapshot.quantity == 10
    assert short_snapshot.symbol == "QQQ"
    assert short_snapshot.side == BrokerPositionSide.SHORT
    assert short_snapshot.quantity == -5


def test_open_order_snapshot_normalization_works() -> None:
    snapshot = _adapter().open_order_response_to_snapshot(
        account_id=ACCOUNT_ID,
        response={
            "id": "alpaca-order-1",
            "client_order_id": "client-1",
            "symbol": "spy",
            "side": "buy",
            "qty": "10",
            "filled_qty": "2",
            "status": "partially_filled",
            "type": "limit",
            "limit_price": "101.25",
            "stop_price": None,
            "updated_at": "2026-01-02T14:31:00Z",
        },
    )

    assert isinstance(snapshot, BrokerOpenOrderSnapshot)
    assert snapshot.account_id == ACCOUNT_ID
    assert snapshot.broker_order_id == "alpaca-order-1"
    assert snapshot.client_order_id == "client-1"
    assert snapshot.symbol == "SPY"
    assert snapshot.status == BrokerOrderStatus.PARTIAL_FILL
    assert snapshot.qty == 10
    assert snapshot.filled_qty == 2
    assert snapshot.order_type == "limit"
    assert snapshot.limit_price == 101.25


def test_adapter_cannot_create_internal_orders() -> None:
    adapter = _adapter()
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

    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.submit_order(intent)  # type: ignore[arg-type]

    assert exc_info.value.details.code == "invalid_order_boundary"


def test_mocked_submission_uses_trading_client(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeOrderRequest)
    fake_client = FakeTradingClient()
    adapter = AlpacaBrokerAdapter(trading_client=fake_client, load_env=False)

    result = adapter.submit_order(_order())

    assert result.status == BrokerOrderStatus.ACCEPTED
    assert fake_client.get_order_calls == 1
    assert fake_client.submit_order_calls == 1
    assert isinstance(fake_client.submitted_order_data, FakeOrderRequest)
    assert fake_client.submitted_order_data.kwargs["client_order_id"] == "utos-11111111-aaaaaaaa-99999999-open-000001"


def test_adapter_instantiates_with_env(monkeypatch) -> None:
    class FakeTradingClientClass:
        def __init__(self, api_key, secret_key, **kwargs) -> None:
            self.api_key = api_key
            self.secret_key = secret_key
            self.kwargs = kwargs

    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    monkeypatch.setenv("ALPACA_BASE_URL", "https://malicious.invalid")
    monkeypatch.setattr(alpaca_module, "TradingClient", FakeTradingClientClass)

    adapter = AlpacaBrokerAdapter(load_env=False)

    assert adapter._client.api_key == "key"
    assert adapter._client.secret_key == "secret"
    assert adapter._client.kwargs["paper"] is True
    assert "url_override" not in adapter._client.kwargs
    assert adapter.base_url == "https://paper-api.alpaca.markets"


def test_adapter_rejects_external_base_url_override() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        AlpacaBrokerAdapter(trading_client=FakeTradingClient(), load_env=False, base_url="https://example.invalid")

    assert exc_info.value.details.code == "custom_base_url_rejected"


def test_no_alpaca_sdk_or_network_imports_exist() -> None:
    source = inspect.getsource(alpaca_module)

    assert "alpaca_trade_api" not in source
    assert "httpx" not in source
    assert "websocket" not in source.lower()
    assert re.search(r"^\s*import\s+requests\b", source, flags=re.MULTILINE) is None
    assert re.search(r"^\s*from\s+requests\b", source, flags=re.MULTILINE) is None

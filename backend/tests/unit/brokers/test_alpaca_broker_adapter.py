from __future__ import annotations

import inspect
import re
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
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderOrigin
import backend.app.brokers.alpaca as alpaca_module

try:
    from alpaca.trading.enums import OrderStatus
except ImportError:  # pragma: no cover - local fallback when alpaca-py is unavailable.
    class OrderStatus(Enum):
        PENDING_NEW = "pending_new"


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
STRATEGY_ID = UUID("22222222-3333-4444-5555-666666666666")
STRATEGY_VERSION_ID = UUID("33333333-4444-5555-6666-777777777777")
SIGNAL_PLAN_ID = UUID("44444444-5555-6666-7777-888888888888")
CLIENT_ORDER_ID = "sigplan-11111111-44444444-open-0000010000"


def _order(
    *,
    order_type: OrderType = OrderType.MARKET,
    limit_price: float | None = None,
    stop_price: float | None = None,
    side: CandidateSide = CandidateSide.LONG,
    intent: InternalOrderIntent = InternalOrderIntent.OPEN,
) -> InternalOrder:
    now = utc_now()
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=CLIENT_ORDER_ID,
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=STRATEGY_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        signal_plan_id=SIGNAL_PLAN_ID,
        opening_signal_plan_id=SIGNAL_PLAN_ID,
        current_signal_plan_id=SIGNAL_PLAN_ID,
        position_lineage_id=SIGNAL_PLAN_ID,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        symbol="SPY",
        side=side,
        quantity=10,
        order_type=order_type,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price,
        stop_price=stop_price,
        intent=intent,
        status=InternalOrderStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


class FakeTradingClient:
    def __init__(self, response: dict | None = None, *, existing_order: dict | None = None) -> None:
        self.response = response or {
            "id": "alpaca-order-1",
            "client_order_id": CLIENT_ORDER_ID,
            "status": "new",
            "filled_qty": "0",
            "qty": "10",
        }
        self.existing_order = existing_order
        self.submitted_order_data = None
        self.get_order_calls = 0
        self.submit_order_calls = 0
        self.get_orders_filter = None

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

    def get_orders(self, filter=None):  # noqa: A002
        self.get_orders_filter = filter
        return [self.response]

    def get_account(self):
        return {"buying_power": "50000", "cash": "25000", "equity": "55000"}

    def get_all_positions(self):
        return [{"symbol": "SPY", "qty": "10", "market_value": "1000", "avg_entry_price": "100"}]


class FakeOrderRequest:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


def _adapter(response: dict | None = None, *, mode: TradingMode = TradingMode.BROKER_PAPER) -> AlpacaBrokerAdapter:
    return AlpacaBrokerAdapter(
        mode=mode,
        trading_client=FakeTradingClient(response=response),
    )


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
        "client_order_id": CLIENT_ORDER_ID,
    }


def test_long_position_exit_translates_to_alpaca_sell_order() -> None:
    request = _adapter().translate_order_request(
        _order(side=CandidateSide.SHORT, intent=InternalOrderIntent.LOGICAL_EXIT)
    )

    assert request["side"] == "sell"


def test_short_position_exit_translates_to_alpaca_buy_order() -> None:
    request = _adapter().translate_order_request(
        _order(side=CandidateSide.LONG, intent=InternalOrderIntent.LOGICAL_EXIT)
    )

    assert request["side"] == "buy"


def test_limit_order_translation_correct() -> None:
    request = _adapter().translate_order_request(_order(order_type=OrderType.LIMIT, limit_price=101.25))

    assert request["type"] == "limit"
    assert request["limit_price"] == 101.25


def test_stop_order_translation_correct() -> None:
    request = _adapter().translate_order_request(_order(order_type=OrderType.STOP, stop_price=99.50))

    assert request["type"] == "stop"
    assert request["stop_price"] == 99.50


def test_stop_limit_order_translation_correct() -> None:
    request = _adapter().translate_order_request(
        _order(order_type=OrderType.STOP_LIMIT, limit_price=99.25, stop_price=99.50)
    )

    assert request["type"] == "stop_limit"
    assert request["limit_price"] == 99.25
    assert request["stop_price"] == 99.50


def test_limit_order_without_limit_price_rejected() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        _adapter().translate_order_request(_order(order_type=OrderType.LIMIT))

    assert exc_info.value.details.code == "limit_price_required"


def test_stop_order_without_stop_price_rejected() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        _adapter().translate_order_request(_order(order_type=OrderType.STOP))

    assert exc_info.value.details.code == "stop_price_required"


def test_status_normalization_works() -> None:
    adapter = _adapter()

    assert adapter.normalize_status("pending_new") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status(OrderStatus.PENDING_NEW) == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("OrderStatus.PENDING_NEW") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("new") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("accepted") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("held") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("stopped") == BrokerOrderStatus.ACCEPTED
    assert adapter.normalize_status("partial_fill") == BrokerOrderStatus.PARTIAL_FILL
    assert adapter.normalize_status("partially_filled") == BrokerOrderStatus.PARTIAL_FILL
    assert adapter.normalize_status("filled") == BrokerOrderStatus.FILLED
    assert adapter.normalize_status("rejected") == BrokerOrderStatus.REJECTED
    assert adapter.normalize_status("canceled") == BrokerOrderStatus.CANCELED
    assert adapter.normalize_status("expired") == BrokerOrderStatus.EXPIRED
    assert adapter.normalize_status("pending_cancel") == BrokerOrderStatus.PENDING_CANCEL
    assert adapter.normalize_status("pending_replace") == BrokerOrderStatus.REPLACED
    assert adapter.normalize_status("done_for_day") == BrokerOrderStatus.DONE_FOR_DAY
    assert adapter.normalize_status("calculated") == BrokerOrderStatus.DONE_FOR_DAY


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
            "daytrading_buying_power": "45000",
            "regt_buying_power": "40000",
            "non_marginable_buying_power": "12000",
            "multiplier": "2",
            "portfolio_value": "56000",
            "long_market_value": "1000",
            "short_market_value": "0",
            "initial_margin": "500",
            "maintenance_margin": "250",
            "last_maintenance_margin": "200",
            "last_equity": "54000",
            "sma": "100",
            "daytrade_count": 1,
            "trade_suspended_by_user": False,
            "transfers_blocked": True,
            "crypto_status": "ACTIVE",
            "currency": "USD",
            "accrued_fees": "1.25",
            "pending_transfer_in": "10",
            "pending_transfer_out": "5",
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
    assert snapshot.daytrading_buying_power == 45_000
    assert snapshot.regt_buying_power == 40_000
    assert snapshot.non_marginable_buying_power == 12_000
    assert snapshot.multiplier == 2
    assert snapshot.portfolio_value == 56_000
    assert snapshot.long_market_value == 1_000
    assert snapshot.short_market_value == 0
    assert snapshot.initial_margin == 500
    assert snapshot.maintenance_margin == 250
    assert snapshot.last_maintenance_margin == 200
    assert snapshot.last_equity == 54_000
    assert snapshot.sma == 100
    assert snapshot.daytrade_count == 1
    assert snapshot.transfers_blocked is True
    assert snapshot.crypto_status == "ACTIVE"
    assert snapshot.currency == "USD"
    assert snapshot.accrued_fees == 1.25
    assert snapshot.pending_transfer_in == 10
    assert snapshot.pending_transfer_out == 5
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

    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.submit_order(object())  # type: ignore[arg-type]

    assert exc_info.value.details.code == "invalid_order_boundary"


def test_mocked_submission_uses_trading_client(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeOrderRequest)
    fake_client = FakeTradingClient()
    adapter = AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER, trading_client=fake_client)

    result = adapter.submit_order(_order())

    assert result.status == BrokerOrderStatus.ACCEPTED
    assert fake_client.get_order_calls == 1
    assert fake_client.submit_order_calls == 1
    assert isinstance(fake_client.submitted_order_data, FakeOrderRequest)
    assert fake_client.submitted_order_data.kwargs["client_order_id"] == CLIENT_ORDER_ID


def test_mocked_limit_submission_uses_limit_order_request(monkeypatch) -> None:
    monkeypatch.setattr(alpaca_module, "LimitOrderRequest", FakeOrderRequest)
    fake_client = FakeTradingClient()
    adapter = AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER, trading_client=fake_client)

    result = adapter.submit_order(_order(order_type=OrderType.LIMIT, limit_price=101.25))

    assert result.status == BrokerOrderStatus.ACCEPTED
    assert fake_client.submit_order_calls == 1
    assert isinstance(fake_client.submitted_order_data, FakeOrderRequest)
    assert fake_client.submitted_order_data.kwargs["limit_price"] == 101.25


def test_adapter_builds_trading_client_with_explicit_credentials(monkeypatch) -> None:
    """Adapter takes credentials explicitly, never reads env."""

    class FakeTradingClientClass:
        def __init__(self, api_key, secret_key, **kwargs) -> None:
            self.api_key = api_key
            self.secret_key = secret_key
            self.kwargs = kwargs

    monkeypatch.setattr(alpaca_module, "TradingClient", FakeTradingClientClass)
    # M10 live-mode init guard: enable env + per-Account flag for the
    # BROKER_LIVE construction.
    monkeypatch.setenv("TRADING_LIVE_ENABLED", "true")
    paper = AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER, api_key="K", secret_key="S")
    live = AlpacaBrokerAdapter(
        mode=TradingMode.BROKER_LIVE, api_key="K", secret_key="S", allow_live=True
    )

    assert paper._client.api_key == "K"
    assert paper._client.secret_key == "S"
    assert paper._client.kwargs["paper"] is True
    assert paper.base_url == "https://paper-api.alpaca.markets"
    assert live._client.kwargs["paper"] is False
    assert live.base_url == "https://api.alpaca.markets"


def test_adapter_rejects_broker_live_without_env_gate(monkeypatch) -> None:
    """M10: BROKER_LIVE without TRADING_LIVE_ENABLED env raises."""
    monkeypatch.delenv("TRADING_LIVE_ENABLED", raising=False)
    with pytest.raises(AlpacaBrokerError) as excinfo:
        AlpacaBrokerAdapter(
            mode=TradingMode.BROKER_LIVE,
            api_key="K",
            secret_key="S",
            allow_live=True,
        )
    assert excinfo.value.details.code == "live_mode_env_disabled"


def test_adapter_rejects_broker_live_without_per_account_flag(monkeypatch) -> None:
    """M10: BROKER_LIVE with env enabled but allow_live=False raises."""
    monkeypatch.setenv("TRADING_LIVE_ENABLED", "true")
    with pytest.raises(AlpacaBrokerError) as excinfo:
        AlpacaBrokerAdapter(
            mode=TradingMode.BROKER_LIVE,
            api_key="K",
            secret_key="S",
            allow_live=False,
        )
    assert excinfo.value.details.code == "live_mode_account_disabled"


def test_adapter_paper_unaffected_by_live_gates(monkeypatch) -> None:
    """M10: BROKER_PAPER bypasses live-mode gates entirely."""
    monkeypatch.delenv("TRADING_LIVE_ENABLED", raising=False)

    class FakeTradingClientClass:
        def __init__(self, api_key, secret_key, **kwargs) -> None:
            self.api_key = api_key
            self.secret_key = secret_key
            self.kwargs = kwargs

    monkeypatch.setattr(alpaca_module, "TradingClient", FakeTradingClientClass)
    paper = AlpacaBrokerAdapter(
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        secret_key="S",
        allow_live=False,  # explicitly false; paper doesn't care
    )
    assert paper.mode == TradingMode.BROKER_PAPER


def test_adapter_requires_explicit_credentials() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER)
    assert exc_info.value.details.code == "missing_credentials"


def test_adapter_rejects_external_base_url_override() -> None:
    with pytest.raises(AlpacaBrokerError) as exc_info:
        AlpacaBrokerAdapter(
            mode=TradingMode.BROKER_PAPER,
            trading_client=FakeTradingClient(),
            base_url="https://example.invalid",
        )

    assert exc_info.value.details.code == "custom_base_url_rejected"


def test_no_alpaca_sdk_or_network_imports_exist() -> None:
    source = inspect.getsource(alpaca_module)

    assert "alpaca_trade_api" not in source
    assert "httpx" not in source
    assert "websocket" not in source.lower()
    assert re.search(r"^\s*import\s+requests\b", source, flags=re.MULTILINE) is None
    assert re.search(r"^\s*from\s+requests\b", source, flags=re.MULTILINE) is None

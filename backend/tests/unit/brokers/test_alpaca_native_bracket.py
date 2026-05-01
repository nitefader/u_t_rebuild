"""T-4 (Bracket Program) — Alpaca native bracket support tests.

Acceptance from STRATEGY_TO_BROKER_BRACKET_PROGRAM.md §5:

    3. Long native Alpaca bracket
    4. Short native Alpaca bracket if supported, otherwise explicit unsupported result.

Plus pre-flight gate tests for Alpaca's constraint matrix verified
2026-04-29 against ``docs.alpaca.markets`` + alpaca-py SDK:
- TIF must be DAY or GTC
- Extended hours not supported
- Fractional shares not supported
- Bracket child prices required

Per operator: "fail clearly if Alpaca rejects the structure."
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.brokers import AlpacaBrokerAdapter, AlpacaBrokerError
from backend.app.brokers.alpaca import AlpacaBrokerCapabilities
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.domain._base import utc_now
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderOrigin

try:
    from alpaca.trading.enums import OrderClass as AlpacaOrderClass
    from alpaca.trading.requests import (
        MarketOrderRequest,
        StopLossRequest,
        TakeProfitRequest,
    )
except ImportError:  # pragma: no cover
    AlpacaOrderClass = None  # type: ignore[assignment]
    MarketOrderRequest = None  # type: ignore[assignment]
    StopLossRequest = None  # type: ignore[assignment]
    TakeProfitRequest = None  # type: ignore[assignment]


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
STRATEGY_ID = UUID("22222222-3333-4444-5555-666666666666")
STRATEGY_VERSION_ID = UUID("33333333-4444-5555-6666-777777777777")
SIGNAL_PLAN_ID = UUID("44444444-5555-6666-7777-888888888888")


def _bracket_order(
    *,
    side: CandidateSide = CandidateSide.LONG,
    quantity: float = 10,
    take_profit: float | None = 110.0,
    stop_loss: float | None = 95.0,
    time_in_force: TimeInForce = TimeInForce.DAY,
    extended_hours: bool = False,
    order_class: str | None = "bracket",
) -> InternalOrder:
    now = utc_now()
    return InternalOrder(
        order_id=uuid4(),
        client_order_id="sigplan-11111111-44444444-open-0000010000",
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
        quantity=quantity,
        order_type=OrderType.MARKET,
        time_in_force=time_in_force,
        order_class=order_class,
        bracket_take_profit_limit_price=take_profit,
        bracket_stop_loss_stop_price=stop_loss,
        extended_hours=extended_hours,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.CREATED,
        created_at=now,
        updated_at=now,
    )


class _FakeTradingClient:
    def submit_order(self, *, order_data):
        self.last = order_data
        return {"id": "alpaca-1", "client_order_id": order_data.client_order_id, "status": "new", "filled_qty": "0"}


def _adapter() -> AlpacaBrokerAdapter:
    return AlpacaBrokerAdapter(mode=TradingMode.BROKER_PAPER, trading_client=_FakeTradingClient())


def test_capabilities_advertise_supports_brackets_true() -> None:
    """T-4 flips supports_brackets from false to true."""

    assert AlpacaBrokerCapabilities().supports_brackets is True


@pytest.mark.skipif(AlpacaOrderClass is None, reason="alpaca-py SDK not installed")
def test_long_native_bracket_request_attaches_take_profit_and_stop_loss() -> None:
    """Acceptance #3: long native bracket with both child legs."""

    adapter = _adapter()
    order = _bracket_order(side=CandidateSide.LONG, take_profit=110.0, stop_loss=95.0)

    request = adapter.to_alpaca_order_request(order)

    assert isinstance(request, MarketOrderRequest)
    # OrderClass.BRACKET attached
    assert request.order_class == AlpacaOrderClass.BRACKET
    # take_profit + stop_loss legs
    assert request.take_profit is not None
    assert request.take_profit.limit_price == 110.0
    assert request.stop_loss is not None
    assert request.stop_loss.stop_price == 95.0
    # Entry side: BUY for long
    assert str(request.side).lower().endswith("buy")


@pytest.mark.skipif(AlpacaOrderClass is None, reason="alpaca-py SDK not installed")
def test_short_native_bracket_request_attaches_inverse_legs() -> None:
    """Acceptance #4: short native bracket — Alpaca does support this for ETB."""

    adapter = _adapter()
    # Short: take_profit BELOW fill, stop_loss ABOVE fill.
    order = _bracket_order(side=CandidateSide.SHORT, take_profit=90.0, stop_loss=105.0)

    request = adapter.to_alpaca_order_request(order)

    assert request.order_class == AlpacaOrderClass.BRACKET
    assert request.take_profit.limit_price == 90.0
    assert request.stop_loss.stop_price == 105.0
    assert str(request.side).lower().endswith("sell")


def test_native_bracket_without_child_prices_fails_explicitly() -> None:
    """Per operator: fail clearly if Alpaca rejects the structure."""

    adapter = _adapter()
    order = _bracket_order(take_profit=None, stop_loss=None)

    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)

    assert exc_info.value.details.code == "native_bracket_missing_child_prices"


def test_native_bracket_without_take_profit_fails_explicitly() -> None:
    adapter = _adapter()
    order = _bracket_order(take_profit=None, stop_loss=95.0)
    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)
    assert exc_info.value.details.code == "native_bracket_missing_child_prices"


def test_native_bracket_without_stop_loss_fails_explicitly() -> None:
    adapter = _adapter()
    order = _bracket_order(take_profit=110.0, stop_loss=None)
    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)
    assert exc_info.value.details.code == "native_bracket_missing_child_prices"


def test_native_bracket_with_unsupported_tif_ioc_fails_explicitly() -> None:
    adapter = _adapter()
    order = _bracket_order(time_in_force=TimeInForce.IOC)
    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)
    assert exc_info.value.details.code == "native_bracket_unsupported_tif"
    assert "ioc" in exc_info.value.details.message.lower()


def test_native_bracket_with_extended_hours_fails_explicitly() -> None:
    adapter = _adapter()
    order = _bracket_order(extended_hours=True)
    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)
    assert exc_info.value.details.code == "native_bracket_unsupported_extended_hours"


def test_native_bracket_with_fractional_quantity_fails_explicitly() -> None:
    adapter = _adapter()
    order = _bracket_order(quantity=2.5)
    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)
    assert exc_info.value.details.code == "native_bracket_unsupported_fractional"


def test_native_bracket_with_gtc_tif_passes_preflight() -> None:
    adapter = _adapter()
    order = _bracket_order(time_in_force=TimeInForce.GTC)
    # Should not raise
    request = adapter.to_alpaca_order_request(order)
    assert request is not None


def test_simple_order_class_does_not_attach_bracket_fields() -> None:
    """Backwards-compat: existing simple-order path unchanged."""

    adapter = _adapter()
    order = _bracket_order(order_class=None, take_profit=None, stop_loss=None)

    request = adapter.to_alpaca_order_request(order)

    # Simple market order — no order_class kwarg
    if hasattr(request, "order_class"):
        assert request.order_class is None
    if hasattr(request, "take_profit"):
        assert request.take_profit is None
    if hasattr(request, "stop_loss"):
        assert request.stop_loss is None


def test_internal_order_accepts_bracket_child_prices() -> None:
    """Schema-level check: InternalOrder accepts the new bracket fields."""

    order = _bracket_order()
    assert order.bracket_take_profit_limit_price == 110.0
    assert order.bracket_stop_loss_stop_price == 95.0
    assert order.order_class == "bracket"


@pytest.mark.skipif(AlpacaOrderClass is None, reason="alpaca-py SDK not installed")
def test_native_oco_request_uses_limit_primary_with_attached_stop_loss() -> None:
    adapter = _adapter()
    order = _bracket_order(
        order_class="oco",
        take_profit=None,
        stop_loss=95.0,
    ).model_copy(update={"order_type": OrderType.LIMIT, "limit_price": 110.0})

    request = adapter.to_alpaca_order_request(order)

    assert request.order_class == AlpacaOrderClass.OCO
    assert request.limit_price == pytest.approx(110.0)
    assert request.take_profit is not None
    assert request.take_profit.limit_price == pytest.approx(110.0)
    assert request.stop_loss is not None
    assert request.stop_loss.stop_price == pytest.approx(95.0)


@pytest.mark.skipif(AlpacaOrderClass is None, reason="alpaca-py SDK not installed")
def test_native_oco_request_quantizes_fractional_penny_prices() -> None:
    adapter = _adapter()
    order = _bracket_order(
        order_class="oco",
        take_profit=None,
        stop_loss=65.47461329431461,
    ).model_copy(update={"order_type": OrderType.LIMIT, "limit_price": 65.8282734113708})

    request = adapter.to_alpaca_order_request(order)

    assert request.limit_price == pytest.approx(65.83)
    assert request.take_profit is not None
    assert request.take_profit.limit_price == pytest.approx(65.83)
    assert request.stop_loss is not None
    assert request.stop_loss.stop_price == pytest.approx(65.47)


def test_native_oco_without_limit_or_stop_fails_explicitly() -> None:
    adapter = _adapter()
    order = _bracket_order(order_class="oco", take_profit=None, stop_loss=None).model_copy(
        update={"order_type": OrderType.LIMIT}
    )

    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)

    assert exc_info.value.details.code == "native_oco_missing_prices"


def test_native_oco_without_limit_price_fails_explicitly() -> None:
    adapter = _adapter()
    order = _bracket_order(order_class="oco", take_profit=None, stop_loss=95.0).model_copy(
        update={"order_type": OrderType.LIMIT}
    )

    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)

    assert exc_info.value.details.code == "native_oco_missing_prices"


def test_native_oco_without_stop_loss_fails_explicitly() -> None:
    adapter = _adapter()
    order = _bracket_order(order_class="oco", take_profit=None, stop_loss=None).model_copy(
        update={"order_type": OrderType.LIMIT, "limit_price": 110.0}
    )

    with pytest.raises(AlpacaBrokerError) as exc_info:
        adapter.to_alpaca_order_request(order)

    assert exc_info.value.details.code == "native_oco_missing_prices"

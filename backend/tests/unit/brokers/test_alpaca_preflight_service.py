from __future__ import annotations

from uuid import uuid4

from backend.app.brokers import (
    AlpacaBrokerPreflightService,
    BrokerAssetClass,
    BrokerOrderClass,
    BrokerOrderPreflightRequest,
    BrokerViolationCode,
    MarketRulePreflightRequest,
    MarketRulePreflightService,
    MarketRuleViolationCode,
    MarketSessionState,
)
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode


def _order_request(**overrides: object) -> BrokerOrderPreflightRequest:
    data: dict[str, object] = {
        "account_id": uuid4(),
        "provider": "alpaca",
        "broker_mode": TradingMode.BROKER_PAPER,
        "asset_class": BrokerAssetClass.EQUITY,
        "symbol": "SPY",
        "side": CandidateSide.LONG,
        "quantity": 1,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
    }
    data.update(overrides)
    return BrokerOrderPreflightRequest(**data)


def _market_request(**overrides: object) -> MarketRulePreflightRequest:
    data: dict[str, object] = {
        "account_id": uuid4(),
        "provider": "alpaca",
        "broker_mode": TradingMode.BROKER_PAPER,
        "symbol": "SPY",
        "asset_class": BrokerAssetClass.EQUITY,
        "side": CandidateSide.LONG,
        "quantity": 1,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
        "market_session": MarketSessionState.REGULAR,
        "asset_tradable": True,
        "asset_fractionable": True,
        "shortable": True,
        "easy_to_borrow": True,
        "halted": False,
        "buying_power": 10_000,
    }
    data.update(overrides)
    return MarketRulePreflightRequest(**data)


def test_allows_regular_equity_market_day_order() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(_order_request())

    assert result.allowed is True
    assert result.normalized_request["provider"] == "alpaca"


def test_rejects_extended_hours_market_order_with_operator_advisory() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(extended_hours=True, order_type=OrderType.MARKET)
    )

    assert result.allowed is False
    # M3/P1-1: EH non-limit orders now use the specific EH order-type violation code.
    assert result.violations[0].code == BrokerViolationCode.EXTENDED_HOURS_ORDER_TYPE_UNSUPPORTED
    assert result.violations[0].field == "order_type"
    assert result.operator_advisory is not None
    assert "limit DAY" in result.operator_advisory.operator_action


def test_allows_extended_hours_equity_limit_day_order() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(extended_hours=True, order_type=OrderType.LIMIT, limit_price=500)
    )

    assert result.allowed is True


def test_rejects_fractional_equity_gtc_order() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            asset_class=BrokerAssetClass.FRACTIONAL_EQUITY,
            time_in_force=TimeInForce.GTC,
            notional=100,
            quantity=None,
        )
    )

    assert result.allowed is False
    assert result.violations[0].code == BrokerViolationCode.UNSUPPORTED_TIME_IN_FORCE
    assert result.violations[0].field == "time_in_force"


def test_rejects_crypto_day_and_stop_order() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            asset_class=BrokerAssetClass.CRYPTO,
            symbol="BTC/USD",
            order_type=OrderType.STOP,
            time_in_force=TimeInForce.DAY,
            stop_price=55_000,
        )
    )

    assert result.allowed is False
    assert {violation.code for violation in result.violations} == {
        BrokerViolationCode.UNSUPPORTED_TIME_IN_FORCE,
        BrokerViolationCode.UNSUPPORTED_ORDER_TYPE,
    }


def test_rejects_option_stop_order_and_non_day_tif() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            asset_class=BrokerAssetClass.OPTION,
            symbol="SPY260117C00500000",
            order_type=OrderType.STOP,
            time_in_force=TimeInForce.GTC,
            stop_price=2.5,
        )
    )

    assert result.allowed is False
    assert {violation.field for violation in result.violations} == {"time_in_force", "order_type"}


def test_allows_valid_broker_native_bracket_simple_shape() -> None:
    # M4 (P0-4): The blanket UNSUPPORTED_ORDER_CLASS block is removed for BRACKET.
    # A BRACKET order with 1 target + 1 stop and no runner passes preflight now.
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.BRACKET,
            native_multileg_requested=True,
            target_leg_count=1,
            stop_leg_count=1,
        )
    )

    assert result.allowed is True


def test_rejects_broker_native_multitarget_bracket_with_specific_advisory() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.BRACKET,
            native_multileg_requested=True,
            target_leg_count=4,
            stop_leg_count=1,
        )
    )

    assert result.allowed is False
    assert result.violations[0].code == BrokerViolationCode.BROKER_NATIVE_MULTI_LEG_UNSUPPORTED
    assert result.violations[0].field == "target_leg_count"
    assert "multiple take-profit targets" in result.violations[0].message
    assert result.normalized_request["target_leg_count"] == 4


def test_rejects_runner_as_broker_native_multileg_concept() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.OCO,
            native_multileg_requested=True,
            target_leg_count=1,
            stop_leg_count=1,
            runner_leg_count=1,
        )
    )

    assert result.allowed is False
    assert any(violation.field == "runner_leg_count" for violation in result.violations)


def test_market_rules_reject_closed_equity_session() -> None:
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(market_session=MarketSessionState.CLOSED)
    )

    assert result.allowed is False
    assert result.violations[0].code == MarketRuleViolationCode.MARKET_CLOSED


def test_market_rules_allow_crypto_when_session_closed() -> None:
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(
            asset_class=BrokerAssetClass.CRYPTO,
            symbol="BTC/USD",
            market_session=MarketSessionState.CLOSED,
        )
    )

    assert result.allowed is True


def test_market_rules_reject_unshortable_symbol_with_advisory() -> None:
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(side=CandidateSide.SHORT, shortable=False, easy_to_borrow=False)
    )

    assert result.allowed is False
    assert {violation.code for violation in result.violations} == {
        MarketRuleViolationCode.SHORT_NOT_ALLOWED,
        MarketRuleViolationCode.NOT_EASY_TO_BORROW,
    }
    assert result.operator_advisory is not None
    assert "short" in result.operator_advisory.operator_action.lower()


def test_market_rules_do_not_treat_long_exit_sell_as_new_short() -> None:
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(
            side=CandidateSide.SHORT,
            is_position_management=True,
            shortable=False,
            easy_to_borrow=False,
        )
    )

    assert result.allowed is True


def test_market_rules_reject_notional_above_buying_power() -> None:
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(quantity=None, notional=2_500, buying_power=2_000)
    )

    assert result.allowed is False
    assert result.violations[0].code == MarketRuleViolationCode.BUYING_POWER_INSUFFICIENT

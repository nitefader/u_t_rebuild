from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.brokers import (
    BrokerAssetClass,
    BrokerCapabilityMatrix,
    BrokerCapabilityViolation,
    BrokerErrorFamily,
    BrokerErrorSeverity,
    BrokerOperation,
    BrokerOperatorAdvisory,
    BrokerOrderClass,
    BrokerOrderPreflightRequest,
    BrokerOrderPreflightResult,
    BrokerViolationCode,
    MarketRulePreflightRequest,
    MarketRulePreflightResult,
    MarketRuleViolation,
    MarketRuleViolationCode,
    MarketSessionState,
)
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode


def test_capability_matrix_requires_reason_when_unsupported() -> None:
    with pytest.raises(ValidationError):
        BrokerCapabilityMatrix(
            provider="alpaca",
            asset_class=BrokerAssetClass.EQUITY,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            supported=False,
        )


def test_broker_preflight_rejects_quantity_and_notional_together() -> None:
    with pytest.raises(ValidationError):
        BrokerOrderPreflightRequest(
            account_id=uuid4(),
            provider="alpaca",
            broker_mode=TradingMode.BROKER_PAPER,
            asset_class=BrokerAssetClass.FRACTIONAL_EQUITY,
            symbol="SPY",
            side=CandidateSide.LONG,
            quantity=1,
            notional=100,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )


def test_rejected_broker_preflight_requires_structured_violation() -> None:
    result = BrokerOrderPreflightResult(
        allowed=False,
        violations=(
            BrokerCapabilityViolation(
                code=BrokerViolationCode.EXTENDED_HOURS_UNSUPPORTED,
                message="extended-hours orders require a supported limit/day shape",
                field="extended_hours",
            ),
        ),
        operator_advisory=BrokerOperatorAdvisory(
            family=BrokerErrorFamily.VALIDATION,
            severity=BrokerErrorSeverity.ERROR,
            retryable=False,
            source="preflight",
            message="extended-hours market order rejected before broker submit",
            operator_action="Use a supported limit DAY order or disable extended hours.",
        ),
    )

    assert not result.allowed
    assert result.violations[0].code == BrokerViolationCode.EXTENDED_HOURS_UNSUPPORTED


def test_allowed_broker_preflight_cannot_carry_violations() -> None:
    with pytest.raises(ValidationError):
        BrokerOrderPreflightResult(
            allowed=True,
            violations=(BrokerCapabilityViolation(code=BrokerViolationCode.UNSUPPORTED_ORDER_TYPE, message="bad"),),
        )


def test_market_rule_preflight_has_session_and_asset_state() -> None:
    request = MarketRulePreflightRequest(
        account_id=uuid4(),
        provider="alpaca",
        broker_mode=TradingMode.BROKER_PAPER,
        symbol="SPY",
        asset_class=BrokerAssetClass.EQUITY,
        side=CandidateSide.LONG,
        quantity=1,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.DAY,
        order_class=BrokerOrderClass.SIMPLE,
        extended_hours=True,
        market_session=MarketSessionState.PRE_MARKET,
        asset_tradable=True,
        asset_fractionable=True,
        shortable=True,
        easy_to_borrow=True,
        halted=False,
        buying_power=1000,
    )

    assert request.market_session == MarketSessionState.PRE_MARKET


def test_rejected_market_rule_preflight_requires_structured_violation() -> None:
    result = MarketRulePreflightResult(
        allowed=False,
        session_state=MarketSessionState.CLOSED,
        violations=(
            MarketRuleViolation(
                code=MarketRuleViolationCode.MARKET_CLOSED,
                message="market is closed and order is not eligible for this session",
            ),
        ),
    )

    assert result.violations[0].code == MarketRuleViolationCode.MARKET_CLOSED

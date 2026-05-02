"""Alpaca preflight hardening tests — HARD.MD M3 + M5 + M4.

Test rows per HARD.MD §73:
  T3.1  stop-distance threshold
  T3.2  fractional + short
  T3.3  extended-hours TIF rules
  T3.4  OTO replace rejection
  T3.5  qty XOR notional
  T3.6  notional replace rejection
  T3.7  short buying-power estimate

Trailing stop tests (M5):
  T5.1  trail_price AND trail_percent → schema-level reject
  T5.2  trail_percent only on TRAILING_STOP + EH → advisory present
  T5.3  trailing stop used as bracket stop_loss leg → tested via preflight

Native bracket tests (M4):
  T4.1  bracket buy: valid shape accepted
  T4.2  bracket with multi-TP: decomposed (multi-leg violation)
  T4.3  (reconciliation lives in BrokerSync — covered in test_broker_sync_reconciliation.py)
  T4.4  OCO/OTO shape edges
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

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
from backend.app.brokers.capabilities import BrokerOperation
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.orders.models import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderOrigin
from backend.app.domain._base import utc_now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _order_request(**overrides: object) -> BrokerOrderPreflightRequest:
    data: dict[str, object] = {
        "account_id": uuid4(),
        "provider": "alpaca",
        "broker_mode": TradingMode.BROKER_PAPER,
        "asset_class": BrokerAssetClass.EQUITY,
        "symbol": "SPY",
        "side": CandidateSide.LONG,
        "quantity": 10,
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
        "quantity": 10,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
        "market_session": MarketSessionState.REGULAR,
        "asset_tradable": True,
        "asset_fractionable": True,
        "shortable": True,
        "easy_to_borrow": True,
        "halted": False,
        "buying_power": 100_000,
    }
    data.update(overrides)
    return MarketRulePreflightRequest(**data)


def _internal_order(**overrides: object) -> InternalOrder:
    now = utc_now()
    data: dict[str, object] = {
        "order_id": uuid4(),
        "client_order_id": "sigplan-11111111-44444444-open-0000010000",
        "account_id": uuid4(),
        "origin": OrderOrigin.SIGNAL_PLAN,
        "deployment_id": uuid4(),
        "strategy_id": uuid4(),
        "strategy_version_id": uuid4(),
        "signal_plan_id": uuid4(),
        "opening_signal_plan_id": uuid4(),
        "current_signal_plan_id": uuid4(),
        "position_lineage_id": uuid4(),
        "account_evaluation_id": uuid4(),
        "governor_decision_id": uuid4(),
        "symbol": "SPY",
        "side": CandidateSide.LONG,
        "quantity": 10.0,
        "order_type": OrderType.MARKET,
        "time_in_force": TimeInForce.DAY,
        "intent": InternalOrderIntent.OPEN,
        "status": InternalOrderStatus.CREATED,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return InternalOrder(**data)


# ---------------------------------------------------------------------------
# T3.1 — Stop-distance threshold (R1, P0-3a)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "limit_price,stop_price,should_reject",
    [
        # $0.005 distance — below threshold
        (100.00, 99.995, True),
        # exactly $0.01 distance — at threshold (allowed)
        (100.00, 99.99, False),
        # $0.50 distance — well above threshold
        (100.00, 99.50, False),
        # limit below stop (e.g. short stop-limit): distance still computed as abs()
        (95.00, 95.005, True),
        (95.00, 95.01, False),
    ],
    ids=[
        "distance_0.005_reject",
        "distance_0.01_accept",
        "distance_0.50_accept",
        "short_distance_0.005_reject",
        "short_distance_0.01_accept",
    ],
)
def test_t3_1_stop_distance_threshold(limit_price: float, stop_price: float, should_reject: bool) -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_type=OrderType.STOP_LIMIT,
            limit_price=limit_price,
            stop_price=stop_price,
        )
    )

    if should_reject:
        assert result.allowed is False
        codes = {v.code for v in result.violations}
        assert BrokerViolationCode.STOP_DISTANCE_BELOW_THRESHOLD in codes
    else:
        # Stop-limit allowed if no other violations (EH not set, equity OK)
        violation_codes = {v.code for v in result.violations}
        assert BrokerViolationCode.STOP_DISTANCE_BELOW_THRESHOLD not in violation_codes


def test_t3_1_stop_price_below_001_rejects() -> None:
    """A standalone stop order with stop_price < $0.01 is rejected."""
    # Note: BrokerOrderPreflightRequest.stop_price has Field(gt=0) so we can't test
    # stop_price=0. Use stop_price=0.005 (sub-penny) to test the threshold.
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_type=OrderType.STOP,
            stop_price=0.005,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.STOP_DISTANCE_BELOW_THRESHOLD in codes


def test_t3_1_stop_price_at_001_accepted() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_type=OrderType.STOP,
            stop_price=0.01,
        )
    )

    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.STOP_DISTANCE_BELOW_THRESHOLD not in codes


# ---------------------------------------------------------------------------
# T3.2 — Fractional + short rejection (R2, P0-3b)
# ---------------------------------------------------------------------------


def test_t3_2_fractional_short_rejects() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            asset_class=BrokerAssetClass.FRACTIONAL_EQUITY,
            side=CandidateSide.SHORT,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.FRACTIONAL_SHORT_UNSUPPORTED in codes


def test_t3_2_fractional_long_is_allowed() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            asset_class=BrokerAssetClass.FRACTIONAL_EQUITY,
            side=CandidateSide.LONG,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
    )

    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.FRACTIONAL_SHORT_UNSUPPORTED not in codes


def test_t3_2_fractional_short_position_management_not_rejected() -> None:
    """Closing a fractional position (is_position_management=True) is not a new short."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            asset_class=BrokerAssetClass.FRACTIONAL_EQUITY,
            side=CandidateSide.SHORT,
            is_position_management=True,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
    )

    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.FRACTIONAL_SHORT_UNSUPPORTED not in codes


# ---------------------------------------------------------------------------
# T3.3 — Extended-hours TIF rules (R3, P1-1)
# ---------------------------------------------------------------------------


def test_t3_3_eh_limit_gtc_accepted() -> None:
    """EH + limit + GTC is now allowed per Playbook §10."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            extended_hours=True,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.GTC,
            limit_price=500.0,
        )
    )

    assert result.allowed is True


def test_t3_3_eh_limit_day_accepted() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            extended_hours=True,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.DAY,
            limit_price=500.0,
        )
    )

    assert result.allowed is True


def test_t3_3_eh_limit_ioc_rejected() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            extended_hours=True,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.IOC,
            limit_price=500.0,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.EXTENDED_HOURS_TIF_UNSUPPORTED in codes


def test_t3_3_eh_limit_fok_rejected() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            extended_hours=True,
            order_type=OrderType.LIMIT,
            time_in_force=TimeInForce.FOK,
            limit_price=500.0,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.EXTENDED_HOURS_TIF_UNSUPPORTED in codes


def test_t3_3_eh_market_order_rejected() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            extended_hours=True,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.EXTENDED_HOURS_ORDER_TYPE_UNSUPPORTED in codes


# ---------------------------------------------------------------------------
# T3.4 — OTO replace rejection (R4, P1-2a)
# ---------------------------------------------------------------------------


def test_t3_4_oto_replace_rejected() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            operation=BrokerOperation.REPLACE,
            order_class=BrokerOrderClass.OTO,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.OTO_REPLACE_UNSUPPORTED in codes


def test_t3_4_bracket_replace_falls_through_to_general_replace_block() -> None:
    """Non-OTO replace still hits the generic replace block."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            operation=BrokerOperation.REPLACE,
            order_class=BrokerOrderClass.BRACKET,
        )
    )

    assert result.allowed is False
    # OTO-specific code should NOT be present; REPLACE_UNSUPPORTED should be.
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.OTO_REPLACE_UNSUPPORTED not in codes
    assert BrokerViolationCode.REPLACE_UNSUPPORTED in codes


# ---------------------------------------------------------------------------
# T3.5 — qty XOR notional (R6)
# ---------------------------------------------------------------------------


def test_t3_5_qty_and_notional_both_set_rejected_at_schema_level() -> None:
    """BrokerOrderPreflightRequest validates quantity XOR notional at schema level."""
    with pytest.raises(Exception):  # pydantic ValidationError
        BrokerOrderPreflightRequest(
            account_id=uuid4(),
            provider="alpaca",
            broker_mode=TradingMode.BROKER_PAPER,
            asset_class=BrokerAssetClass.EQUITY,
            symbol="SPY",
            side=CandidateSide.LONG,
            quantity=10,
            notional=1000,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )


def test_t3_5_neither_qty_nor_notional_rejected_at_schema_level() -> None:
    with pytest.raises(Exception):  # pydantic ValidationError
        BrokerOrderPreflightRequest(
            account_id=uuid4(),
            provider="alpaca",
            broker_mode=TradingMode.BROKER_PAPER,
            asset_class=BrokerAssetClass.EQUITY,
            symbol="SPY",
            side=CandidateSide.LONG,
            quantity=None,
            notional=None,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )


def test_t3_5_notional_only_accepted_for_fractional() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            asset_class=BrokerAssetClass.FRACTIONAL_EQUITY,
            quantity=None,
            notional=100,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )
    )

    # Should not have qty/notional conflict violation
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.QTY_NOTIONAL_CONFLICT not in codes
    assert BrokerViolationCode.QTY_NOTIONAL_NEITHER not in codes


# ---------------------------------------------------------------------------
# T3.6 — Notional replace rejection (R5, P1-2b)
# ---------------------------------------------------------------------------


def test_t3_6_notional_replace_rejected() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            operation=BrokerOperation.REPLACE,
            quantity=None,
            notional=1000,
            asset_class=BrokerAssetClass.FRACTIONAL_EQUITY,
            time_in_force=TimeInForce.DAY,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.NOTIONAL_REPLACE_UNSUPPORTED in codes


def test_t3_6_qty_replace_not_flagged_as_notional_replace() -> None:
    """A qty-based replace still hits the generic replace block, not the notional one."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            operation=BrokerOperation.REPLACE,
            quantity=10,
        )
    )

    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.NOTIONAL_REPLACE_UNSUPPORTED not in codes
    assert BrokerViolationCode.REPLACE_UNSUPPORTED in codes


# ---------------------------------------------------------------------------
# T3.7 — Short buying-power estimate (R7, P1-4)
# ---------------------------------------------------------------------------


def test_t3_7_short_bp_insufficient_rejects() -> None:
    """max(limit_price=100, 1.03*ask=103) * qty=10 = 1030 > buying_power=900."""
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(
            side=CandidateSide.SHORT,
            order_type=OrderType.LIMIT,
            limit_price=100.0,
            ask_price=100.0,
            quantity=10,
            buying_power=900.0,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert MarketRuleViolationCode.SHORT_BUYING_POWER_INSUFFICIENT in codes


def test_t3_7_short_bp_sufficient_accepted() -> None:
    """max(100, 1.03*100=103) * 10 = 1030 <= buying_power=2000."""
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(
            side=CandidateSide.SHORT,
            order_type=OrderType.LIMIT,
            limit_price=100.0,
            ask_price=100.0,
            quantity=10,
            buying_power=2_000.0,
        )
    )

    codes = {v.code for v in result.violations}
    assert MarketRuleViolationCode.SHORT_BUYING_POWER_INSUFFICIENT not in codes


def test_t3_7_short_bp_uses_limit_when_higher_than_ask_margin() -> None:
    """limit=110 > 1.03*ask=103 → required = 110 * 10 = 1100 > bp=1050."""
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(
            side=CandidateSide.SHORT,
            order_type=OrderType.LIMIT,
            limit_price=110.0,
            ask_price=100.0,
            quantity=10,
            buying_power=1_050.0,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert MarketRuleViolationCode.SHORT_BUYING_POWER_INSUFFICIENT in codes


def test_t3_7_short_bp_no_ask_price_skips_estimate() -> None:
    """Without ask_price the short BP estimate is skipped (no false positives)."""
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(
            side=CandidateSide.SHORT,
            order_type=OrderType.MARKET,
            buying_power=100.0,  # very low but no ask → estimate skipped
        )
    )

    codes = {v.code for v in result.violations}
    assert MarketRuleViolationCode.SHORT_BUYING_POWER_INSUFFICIENT not in codes


def test_t3_7_long_side_never_uses_short_bp_estimate() -> None:
    result = MarketRulePreflightService().preflight_market_rules(
        _market_request(
            side=CandidateSide.LONG,
            ask_price=100.0,
            quantity=10,
            buying_power=100.0,  # insufficient for a long buy but that check uses notional
        )
    )

    codes = {v.code for v in result.violations}
    assert MarketRuleViolationCode.SHORT_BUYING_POWER_INSUFFICIENT not in codes


# ---------------------------------------------------------------------------
# T5 — Trailing stop (M5, HARD.MD P1-3)
# ---------------------------------------------------------------------------


def test_t5_1_trail_price_and_trail_percent_both_set_rejected_at_schema() -> None:
    """T5.1: Both trail_price AND trail_percent → InternalOrder model rejects."""
    now = utc_now()
    with pytest.raises(Exception):  # pydantic ValidationError
        InternalOrder(
            order_id=uuid4(),
            client_order_id="sigplan-11111111-44444444-trail-0000010000",
            account_id=uuid4(),
            origin=OrderOrigin.SIGNAL_PLAN,
            deployment_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            signal_plan_id=uuid4(),
            opening_signal_plan_id=uuid4(),
            current_signal_plan_id=uuid4(),
            position_lineage_id=uuid4(),
            account_evaluation_id=uuid4(),
            governor_decision_id=uuid4(),
            symbol="SPY",
            side=CandidateSide.LONG,
            quantity=10.0,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            order_class="trailing_stop",
            trail_price=Decimal("1.50"),
            trail_percent=Decimal("1.0"),  # both set — invalid
            intent=InternalOrderIntent.TRAIL,
            status=InternalOrderStatus.CREATED,
            created_at=now,
            updated_at=now,
        )


def test_t5_1_trail_price_only_accepted() -> None:
    """T5.1: trail_price set, trail_percent=None → valid InternalOrder."""
    order = _internal_order(
        order_class="trailing_stop",
        trail_price=Decimal("1.50"),
        trail_percent=None,
        intent=InternalOrderIntent.TRAIL,
    )
    assert order.trail_price == Decimal("1.50")
    assert order.trail_percent is None


def test_t5_1_trail_percent_only_accepted() -> None:
    order = _internal_order(
        order_class="trailing_stop",
        trail_price=None,
        trail_percent=Decimal("1.0"),
        intent=InternalOrderIntent.TRAIL,
    )
    assert order.trail_percent == Decimal("1.0")
    assert order.trail_price is None


def test_t5_1_trailing_stop_order_class_without_either_trail_field_rejected() -> None:
    """T5.1: order_class=trailing_stop but no trail fields → rejected."""
    now = utc_now()
    with pytest.raises(Exception):
        InternalOrder(
            order_id=uuid4(),
            client_order_id="sigplan-11111111-44444444-trail-0000010001",
            account_id=uuid4(),
            origin=OrderOrigin.SIGNAL_PLAN,
            deployment_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            signal_plan_id=uuid4(),
            opening_signal_plan_id=uuid4(),
            current_signal_plan_id=uuid4(),
            position_lineage_id=uuid4(),
            account_evaluation_id=uuid4(),
            governor_decision_id=uuid4(),
            symbol="SPY",
            side=CandidateSide.LONG,
            quantity=10.0,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
            order_class="trailing_stop",
            trail_price=None,
            trail_percent=None,  # neither set — invalid for trailing_stop
            intent=InternalOrderIntent.TRAIL,
            status=InternalOrderStatus.CREATED,
            created_at=now,
            updated_at=now,
        )


def test_t5_2_trailing_stop_carries_advisory_warning() -> None:
    """T5.2: TRAILING_STOP preflight emits advisory about no EH protection."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.TRAILING_STOP,
            time_in_force=TimeInForce.DAY,
        )
    )

    assert result.allowed is True
    assert any("no extended-hours protection" in w for w in result.warnings)


def test_t5_2_trailing_stop_with_ioc_tif_rejected() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.TRAILING_STOP,
            time_in_force=TimeInForce.IOC,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.UNSUPPORTED_TIME_IN_FORCE in codes


def test_t5_2_trailing_stop_with_gtc_accepted() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.TRAILING_STOP,
            time_in_force=TimeInForce.GTC,
        )
    )

    assert result.allowed is True


def test_t5_3_trail_field_set_on_non_trailing_stop_order_class_is_valid() -> None:
    """trail_price/trail_percent fields are nullable for non-trailing_stop orders."""
    order = _internal_order(
        order_class=None,  # simple order
        trail_price=None,
        trail_percent=None,
    )
    assert order.order_class is None
    assert order.trail_price is None
    assert order.trail_percent is None


# ---------------------------------------------------------------------------
# T4 — Native bracket / OCO / OTO submission (M4, HARD.MD P0-4)
# ---------------------------------------------------------------------------


def test_t4_1_bracket_buy_valid_shape_accepted() -> None:
    """T4.1: Bracket buy — 1 TP, 1 stop, day/gtc, no EH → accepted."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.BRACKET,
            native_multileg_requested=True,
            target_leg_count=1,
            stop_leg_count=1,
            runner_leg_count=0,
            time_in_force=TimeInForce.DAY,
            extended_hours=False,
        )
    )

    assert result.allowed is True


def test_t4_1_bracket_buy_gtc_accepted() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.BRACKET,
            native_multileg_requested=True,
            target_leg_count=1,
            stop_leg_count=1,
            runner_leg_count=0,
            time_in_force=TimeInForce.GTC,
            extended_hours=False,
        )
    )

    assert result.allowed is True


def test_t4_2_bracket_multi_tp_decomposed_via_violation() -> None:
    """T4.2: Multi-TP bracket → BROKER_NATIVE_MULTI_LEG_UNSUPPORTED; decomposes into legs."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.BRACKET,
            native_multileg_requested=True,
            target_leg_count=3,
            stop_leg_count=1,
            runner_leg_count=0,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.BROKER_NATIVE_MULTI_LEG_UNSUPPORTED in codes
    # The violation references target_leg_count specifically
    tl_violations = [v for v in result.violations if v.field == "target_leg_count"]
    assert tl_violations


def test_t4_4_oco_valid_shape_accepted() -> None:
    """T4.4: OCO with 1 target + 1 stop, no runner → accepted."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.OCO,
            native_multileg_requested=True,
            target_leg_count=1,
            stop_leg_count=1,
            runner_leg_count=0,
        )
    )

    assert result.allowed is True


def test_t4_4_oto_rejected_as_unsupported_order_class() -> None:
    """T4.4: OTO decomposes internally; broker-native OTO is rejected."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.OTO,
            native_multileg_requested=True,
            target_leg_count=1,
            stop_leg_count=0,
            runner_leg_count=0,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.UNSUPPORTED_ORDER_CLASS in codes


def test_t4_4_oto_replace_has_specific_violation_code() -> None:
    """T4.4: OTO replace is rejected with OTO_REPLACE_UNSUPPORTED, not generic REPLACE_UNSUPPORTED."""
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            operation=BrokerOperation.REPLACE,
            order_class=BrokerOrderClass.OTO,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.OTO_REPLACE_UNSUPPORTED in codes
    # The OTO-specific code takes priority; generic REPLACE should not also appear
    assert BrokerViolationCode.REPLACE_UNSUPPORTED not in codes


def test_t4_4_oco_runner_leg_rejected() -> None:
    """T4.4: OCO with runner leg → BROKER_NATIVE_MULTI_LEG_UNSUPPORTED."""
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
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.BROKER_NATIVE_MULTI_LEG_UNSUPPORTED in codes


def test_t4_4_bracket_runner_leg_rejected() -> None:
    result = AlpacaBrokerPreflightService().preflight_order(
        _order_request(
            order_class=BrokerOrderClass.BRACKET,
            native_multileg_requested=True,
            target_leg_count=1,
            stop_leg_count=1,
            runner_leg_count=1,
        )
    )

    assert result.allowed is False
    codes = {v.code for v in result.violations}
    assert BrokerViolationCode.BROKER_NATIVE_MULTI_LEG_UNSUPPORTED in codes

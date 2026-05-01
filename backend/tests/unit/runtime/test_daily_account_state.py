from __future__ import annotations

from datetime import datetime, timezone
import logging
import sys
from uuid import uuid4

import pytest

from backend.app.brokers.models import BrokerFillUpdateEvent
from backend.app.runtime.daily_account_state import (
    DailyAccountState,
    DailyAccountStateAggregator,
    _et_market_day,
    _fill_cash_flow,
)
import backend.app.runtime.daily_account_state as daily_account_state_module

ACCOUNT_ID = uuid4()

_T_NY_MORNING = datetime(2026, 4, 30, 14, 30, tzinfo=timezone.utc)  # 10:30 ET
_T_NY_NEXT_DAY = datetime(2026, 5, 1, 14, 30, tzinfo=timezone.utc)   # 10:30 ET next day


def _fill(
    *,
    side: str = "buy",
    qty: float = 10.0,
    price: float = 100.0,
    event_at: datetime = _T_NY_MORNING,
    account_id=ACCOUNT_ID,
    symbol: str = "SPY",
) -> BrokerFillUpdateEvent:
    return BrokerFillUpdateEvent(
        account_id=account_id,
        client_order_id="ord-1",
        symbol=symbol,
        qty=qty,
        price=price,
        side=side,
        event_at=event_at,
    )


# ── _et_market_day ──────────────────────────────────────────────────────────

def test_et_market_day_returns_iso_date() -> None:
    day = _et_market_day(_T_NY_MORNING)
    assert day == "2026-04-30"


def test_et_market_day_rollover_near_midnight_et() -> None:
    # EDT = UTC-4; 2026-04-30 03:59 UTC = 2026-04-29 23:59 EDT
    before_midnight_et = datetime(2026, 4, 30, 3, 59, tzinfo=timezone.utc)
    assert _et_market_day(before_midnight_et) == "2026-04-29"

    # 2026-04-30 04:00 UTC = 2026-04-30 00:00 EDT
    after_midnight_et = datetime(2026, 4, 30, 4, 0, tzinfo=timezone.utc)
    assert _et_market_day(after_midnight_et) == "2026-04-30"


# ── _fill_cash_flow (kept for diagnostic callers) ───────────────────────────

def test_fill_cash_flow_buy_is_negative() -> None:
    assert _fill_cash_flow(_fill(side="buy", qty=10, price=100)) == -1000.0


def test_fill_cash_flow_sell_is_positive() -> None:
    assert _fill_cash_flow(_fill(side="sell", qty=10, price=100)) == 1000.0


# ── DailyAccountStateAggregator: opening fills do NOT realize PnL ──────────


class TestOpeningFillsDoNotRegisterLoss:
    """P0-1 fix: opening a long must not look like a loss to Governor."""

    def test_open_long_does_not_register_loss(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=10_000)

        assert state.realized_pnl == 0.0
        assert state.total_loss_today == 0.0
        assert state.last_loss_at is None
        assert state.drawdown_pct == 0.0

    def test_open_short_does_not_register_loss(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="sell_short", qty=10, price=100), equity=10_000)

        assert state.realized_pnl == 0.0
        assert state.total_loss_today == 0.0
        assert state.last_loss_at is None

    def test_adding_to_long_does_not_realize(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=10_000)
        s2 = agg.apply_fill(s1, _fill(side="buy", qty=10, price=120), equity=10_000)

        assert s2.realized_pnl == 0.0
        assert s2.total_loss_today == 0.0
        # 20 shares; weighted avg cost = (10*100 + 10*120)/20 = 110
        lot = s2.lots["SPY"]
        assert lot.qty == pytest.approx(20.0)
        assert lot.avg_cost == pytest.approx(110.0)


# ── Round-trip realized PnL ─────────────────────────────────────────────────


class TestRoundTripRealizedPnL:
    def test_long_close_at_higher_price_is_gain(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=10, price=110), equity=None)

        assert s2.realized_pnl == pytest.approx(100.0)
        assert s2.total_loss_today == 0.0
        assert s2.last_loss_at is None
        assert "SPY" not in s2.lots

    def test_long_close_at_lower_price_is_loss(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=10_000)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=10, price=90, event_at=_T_NY_MORNING), equity=10_000)

        assert s2.realized_pnl == pytest.approx(-100.0)
        assert s2.total_loss_today == pytest.approx(100.0)
        assert s2.last_loss_at == _T_NY_MORNING

    def test_partial_close_realizes_proportional_pnl(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=4, price=110), equity=None)

        # 4 shares closed @ +10 each = +40
        assert s2.realized_pnl == pytest.approx(40.0)
        # Remaining lot: 6 shares @ 100 (avg unchanged on partial close)
        lot = s2.lots["SPY"]
        assert lot.qty == pytest.approx(6.0)
        assert lot.avg_cost == pytest.approx(100.0)

    def test_short_close_at_lower_price_is_gain(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="sell_short", qty=10, price=100), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="buy", qty=10, price=90), equity=None)

        # short: gain = closing_qty * (avg_cost - cover_price) = 10 * (100 - 90) = 100
        assert s2.realized_pnl == pytest.approx(100.0)

    def test_flip_long_to_short_realizes_long_pnl_then_opens_short(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=None)
        # Sell 15 — closes 10 long @ 110 (+100) and opens 5 short @ 110.
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=15, price=110), equity=None)

        assert s2.realized_pnl == pytest.approx(100.0)
        lot = s2.lots["SPY"]
        assert lot.qty == pytest.approx(-5.0)
        assert lot.avg_cost == pytest.approx(110.0)


# ── Market-day rollover ─────────────────────────────────────────────────────


class TestMarketDayRollover:
    def test_new_market_day_resets_state_and_lots(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=None)
        s2 = agg.apply_fill(
            s1, _fill(side="buy", qty=5, price=200, event_at=_T_NY_NEXT_DAY), equity=None
        )

        assert s2.market_day == "2026-05-01"
        assert s2.realized_pnl == 0.0
        assert s2.total_loss_today == 0.0
        # Lot dict is fresh — yesterday's lot does not carry over to the new day's risk gate.
        assert "SPY" in s2.lots and s2.lots["SPY"].qty == pytest.approx(5.0)
        assert s2.lots["SPY"].avg_cost == pytest.approx(200.0)


# ── Drawdown ───────────────────────────────────────────────────────────────


class TestDrawdown:
    def test_drawdown_zero_when_only_open_position(self) -> None:
        # Crucial: opening a position does NOT register drawdown.
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=10_000)

        assert state.drawdown_pct == 0.0

    def test_drawdown_computed_from_realized_loss(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=10_000)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=10, price=90), equity=10_000)

        # realized -100 on equity 10_000 → 1.0%
        assert s2.drawdown_pct == pytest.approx(1.0)

    def test_drawdown_zero_when_equity_is_none(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=10, price=90), equity=None)

        assert s2.drawdown_pct == 0.0


# ── Cooldown / last_loss_at ─────────────────────────────────────────────────


class TestCooldown:
    def test_last_loss_at_only_set_on_realized_loss(self) -> None:
        agg = DailyAccountStateAggregator()
        # Opening buy + closing sell at gain — no loss.
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=10, price=110), equity=None)

        assert s2.last_loss_at is None

    def test_last_loss_at_set_on_realized_loss(self) -> None:
        agg = DailyAccountStateAggregator()
        t1 = datetime(2026, 4, 30, 14, 30, tzinfo=timezone.utc)
        t2 = datetime(2026, 4, 30, 15, 0, tzinfo=timezone.utc)
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100, event_at=t1), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=10, price=90, event_at=t2), equity=None)

        assert s2.last_loss_at == t2

    def test_last_loss_at_not_cleared_by_subsequent_gain(self) -> None:
        agg = DailyAccountStateAggregator()
        t1 = datetime(2026, 4, 30, 14, 30, tzinfo=timezone.utc)
        t2 = datetime(2026, 4, 30, 15, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 4, 30, 15, 30, tzinfo=timezone.utc)

        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100, event_at=t1), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=10, price=90, event_at=t2), equity=None)
        # New round-trip ending in gain
        s3 = agg.apply_fill(s2, _fill(side="buy", qty=10, price=100, event_at=t3), equity=None)
        s4 = agg.apply_fill(
            s3,
            _fill(side="sell", qty=10, price=110, event_at=datetime(2026, 4, 30, 16, 0, tzinfo=timezone.utc)),
            equity=None,
        )

        assert s4.last_loss_at == t2


def test_et_market_day_logs_warning_when_zoneinfo_unavailable(monkeypatch, caplog) -> None:
    monkeypatch.setattr(daily_account_state_module, "_TZ_FALLBACK_WARNED", False)
    # Import succeeds, but missing ZoneInfo attribute forces fallback path.
    monkeypatch.setitem(sys.modules, "zoneinfo", object())

    with caplog.at_level(logging.WARNING, logger="backend.app.runtime.daily_account_state"):
        day = _et_market_day(_T_NY_MORNING)

    assert day == "2026-04-30"
    assert any(
        getattr(record, "event", None) == "daily_account_state_timezone_fallback"
        for record in caplog.records
    )

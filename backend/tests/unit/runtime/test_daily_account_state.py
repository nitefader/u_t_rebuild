from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from backend.app.brokers.models import BrokerFillUpdateEvent
from backend.app.runtime.daily_account_state import (
    DailyAccountState,
    DailyAccountStateAggregator,
    _et_market_day,
    _fill_cash_flow,
)

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
) -> BrokerFillUpdateEvent:
    return BrokerFillUpdateEvent(
        account_id=account_id,
        client_order_id="ord-1",
        symbol="SPY",
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


# ── _fill_cash_flow ──────────────────────────────────────────────────────────

def test_fill_cash_flow_buy_is_negative() -> None:
    assert _fill_cash_flow(_fill(side="buy", qty=10, price=100)) == -1000.0


def test_fill_cash_flow_sell_is_positive() -> None:
    assert _fill_cash_flow(_fill(side="sell", qty=10, price=100)) == 1000.0


def test_fill_cash_flow_sell_short_is_positive() -> None:
    assert _fill_cash_flow(_fill(side="sell_short", qty=5, price=200)) == 1000.0


def test_fill_cash_flow_short_alias_is_positive() -> None:
    assert _fill_cash_flow(_fill(side="short", qty=5, price=200)) == 1000.0


# ── DailyAccountStateAggregator ──────────────────────────────────────────────

class TestAggregatorFreshState:
    def test_none_current_creates_fresh_state(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=None)

        assert state.account_id == ACCOUNT_ID
        assert state.market_day == "2026-04-30"
        assert state.realized_pnl == -1000.0
        assert state.total_loss_today == 1000.0
        assert state.last_loss_at is not None

    def test_new_market_day_resets_state(self) -> None:
        agg = DailyAccountStateAggregator()
        prev = agg.apply_fill(None, _fill(side="sell", qty=10, price=100, event_at=_T_NY_MORNING), equity=None)

        assert prev.realized_pnl == 1000.0

        state = agg.apply_fill(prev, _fill(side="buy", qty=5, price=200, event_at=_T_NY_NEXT_DAY), equity=None)

        assert state.market_day == "2026-05-01"
        assert state.realized_pnl == -1000.0  # fresh day, only this fill


class TestAggregatorAccumulation:
    def test_multiple_buys_accumulate_loss(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=10_000)
        s2 = agg.apply_fill(s1, _fill(side="buy", qty=5, price=100), equity=10_000)

        assert s2.realized_pnl == pytest.approx(-1500.0)
        assert s2.total_loss_today == pytest.approx(1500.0)

    def test_sell_then_buy_nets_pnl(self) -> None:
        agg = DailyAccountStateAggregator()
        s1 = agg.apply_fill(None, _fill(side="sell", qty=10, price=100), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="buy", qty=10, price=80), equity=None)

        # sold 10@100 = +1000; bought 10@80 = -800; net = +200
        assert s2.realized_pnl == pytest.approx(200.0)
        assert s2.total_loss_today == pytest.approx(800.0)
        assert s2.last_loss_at is not None

    def test_gain_fill_does_not_update_last_loss_at(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="sell", qty=10, price=100), equity=None)

        assert state.last_loss_at is None
        assert state.total_loss_today == 0.0


class TestAggregatorDrawdown:
    def test_drawdown_zero_when_pnl_positive(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="sell", qty=10, price=100), equity=10_000)

        assert state.drawdown_pct == 0.0

    def test_drawdown_computed_from_equity(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=10_000)

        # realized_pnl = -1000, equity = 10_000 → drawdown = 10%
        assert state.drawdown_pct == pytest.approx(10.0)

    def test_drawdown_capped_at_100(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="buy", qty=100, price=100), equity=500)

        # loss = 10_000 on equity 500 → would be 2000%, capped at 100%
        assert state.drawdown_pct == pytest.approx(100.0)

    def test_drawdown_zero_when_equity_is_none(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=None)

        assert state.drawdown_pct == 0.0

    def test_drawdown_zero_when_equity_is_zero(self) -> None:
        agg = DailyAccountStateAggregator()
        state = agg.apply_fill(None, _fill(side="buy", qty=10, price=100), equity=0)

        assert state.drawdown_pct == 0.0


class TestAggregatorCooldown:
    def test_last_loss_at_set_on_buy(self) -> None:
        agg = DailyAccountStateAggregator()
        fill = _fill(side="buy", event_at=_T_NY_MORNING)
        state = agg.apply_fill(None, fill, equity=None)

        assert state.last_loss_at == _T_NY_MORNING

    def test_last_loss_at_updated_on_each_loss(self) -> None:
        agg = DailyAccountStateAggregator()
        t1 = datetime(2026, 4, 30, 14, 30, tzinfo=timezone.utc)
        t2 = datetime(2026, 4, 30, 15, 0, tzinfo=timezone.utc)

        s1 = agg.apply_fill(None, _fill(side="buy", event_at=t1), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="buy", event_at=t2), equity=None)

        assert s2.last_loss_at == t2

    def test_last_loss_at_not_cleared_by_gain(self) -> None:
        agg = DailyAccountStateAggregator()
        t1 = datetime(2026, 4, 30, 14, 30, tzinfo=timezone.utc)
        t2 = datetime(2026, 4, 30, 15, 0, tzinfo=timezone.utc)

        s1 = agg.apply_fill(None, _fill(side="buy", event_at=t1), equity=None)
        s2 = agg.apply_fill(s1, _fill(side="sell", qty=20, price=100, event_at=t2), equity=None)

        # sell is a gain; last_loss_at should still point to the buy time
        assert s2.last_loss_at == t1

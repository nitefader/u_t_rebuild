from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers.models import BrokerFillUpdateEvent
from backend.app.domain._base import utc_now

_LOG = logging.getLogger(__name__)
_TZ_FALLBACK_WARNED = False


def _et_market_day(dt: datetime) -> str:
    """Return the ET calendar date of *dt* as an ISO string ``YYYY-MM-DD``."""
    try:
        import zoneinfo
        et = zoneinfo.ZoneInfo("America/New_York")
        return dt.astimezone(et).date().isoformat()
    except Exception:
        global _TZ_FALLBACK_WARNED
        if not _TZ_FALLBACK_WARNED:
            _TZ_FALLBACK_WARNED = True
            _LOG.warning(
                "daily_account_state: zoneinfo America/New_York unavailable, falling back to fixed UTC-5 offset",
                exc_info=True,
                extra={"event": "daily_account_state_timezone_fallback"},
            )
        # Fallback: fixed UTC-5 offset (no DST). Acceptable for a risk gate.
        from datetime import timedelta
        offset = timedelta(hours=-5)
        et_dt = dt.astimezone(timezone(offset))
        return et_dt.date().isoformat()


_BUY_SIDES = {"buy", "buy_to_cover", "cover"}
_SELL_SIDES = {"sell", "sell_short", "short"}


def _signed_fill_qty(fill: BrokerFillUpdateEvent) -> float:
    """Return signed qty: positive for buys, negative for sells/shorts."""
    side = (fill.side or "").lower()
    if side in _BUY_SIDES:
        return float(fill.qty)
    if side in _SELL_SIDES:
        return -float(fill.qty)
    # Unknown side — treat as flat (no position change). Safer than guessing.
    return 0.0


def _fill_cash_flow(fill: BrokerFillUpdateEvent) -> float:
    """Net cash-flow contribution of a single fill.

    Retained for callers (and tests) that reason about gross cash movement.
    NOT used by ``DailyAccountStateAggregator`` for realized PnL — that uses
    round-trip closing-fill semantics via ``_PositionLot``.
    """
    side = (fill.side or "").lower()
    if side in _SELL_SIDES:
        return fill.qty * fill.price
    return -(fill.qty * fill.price)


class _PositionLot(BaseModel):
    """Average-cost lot for one (account, symbol).

    ``qty`` is signed: positive = long, negative = short, zero = flat.
    ``avg_cost`` is meaningful only when ``qty != 0``.
    """

    model_config = ConfigDict(frozen=False, extra="forbid")

    qty: float = 0.0
    avg_cost: float = 0.0


def _apply_fill_to_lot(lot: _PositionLot, signed_qty: float, price: float) -> float:
    """Apply *signed_qty* @ *price* to *lot* and return realized PnL.

    Average-cost semantics: opening/adding updates avg_cost; closing/reducing
    realizes PnL against the existing avg_cost. Flips close the existing
    position fully then open the residual at the fill price.
    """
    if signed_qty == 0.0:
        return 0.0

    current = lot.qty
    if current == 0.0:
        # Opening fresh position.
        lot.qty = signed_qty
        lot.avg_cost = price
        return 0.0

    same_direction = (current > 0 and signed_qty > 0) or (current < 0 and signed_qty < 0)
    if same_direction:
        # Adding to position — weighted-average new cost, no realized PnL.
        new_qty = current + signed_qty
        lot.avg_cost = (abs(current) * lot.avg_cost + abs(signed_qty) * price) / abs(new_qty)
        lot.qty = new_qty
        return 0.0

    # Opposite direction: closing or flipping.
    closing_qty = min(abs(current), abs(signed_qty))
    # Long close: realized = closing_qty * (sell_price - avg_cost)
    # Short close: realized = closing_qty * (avg_cost - cover_price)
    if current > 0:
        realized = closing_qty * (price - lot.avg_cost)
    else:
        realized = closing_qty * (lot.avg_cost - price)

    new_qty = current + signed_qty
    if new_qty == 0.0:
        lot.qty = 0.0
        lot.avg_cost = 0.0
    elif (new_qty > 0) == (current > 0):
        # Partial close — same direction remains, avg_cost unchanged.
        lot.qty = new_qty
    else:
        # Flip — residual opens at fill price.
        lot.qty = new_qty
        lot.avg_cost = price

    return realized


class DailyAccountState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    market_day: str
    realized_pnl: float = 0.0
    drawdown_pct: float = Field(default=0.0, ge=0)
    last_loss_at: datetime | None = None
    total_loss_today: float = Field(default=0.0, ge=0)
    # Per-symbol open-position lots carried within the market day.
    # Average-cost semantics. Reset on market-day rollover.
    lots: dict[str, _PositionLot] = Field(default_factory=dict)
    updated_at: datetime = Field(default_factory=utc_now)


class DailyAccountStateAggregator:
    """Stateless helper: applies a single BrokerFillUpdateEvent to the current
    DailyAccountState and returns an updated immutable state.

    Realized PnL uses average-cost round-trip semantics — opening a long does
    NOT register as a loss; only closing/reducing fills realize PnL against
    the prevailing avg_cost. This is the gate Governor T-7 reads for
    daily-loss / drawdown / cooldown enforcement.
    """

    def apply_fill(
        self,
        current: DailyAccountState | None,
        fill: BrokerFillUpdateEvent,
        *,
        equity: float | None,
    ) -> DailyAccountState:
        new_market_day = _et_market_day(fill.event_at)

        if current is None or current.market_day != new_market_day:
            current = DailyAccountState(
                account_id=fill.account_id,
                market_day=new_market_day,
            )

        # Copy lots so we can mutate locally; the returned state is frozen.
        lots: dict[str, _PositionLot] = {
            sym: _PositionLot(qty=l.qty, avg_cost=l.avg_cost)
            for sym, l in current.lots.items()
        }
        symbol = fill.symbol.upper()
        lot = lots.get(symbol) or _PositionLot()
        lots[symbol] = lot

        signed_qty = _signed_fill_qty(fill)
        realized = _apply_fill_to_lot(lot, signed_qty, float(fill.price))

        # Drop fully-closed lots to keep the dict bounded.
        if lot.qty == 0.0:
            lots.pop(symbol, None)

        new_realized_pnl = current.realized_pnl + realized

        new_last_loss_at = current.last_loss_at
        new_total_loss_today = current.total_loss_today
        if realized < 0:
            new_last_loss_at = fill.event_at
            new_total_loss_today = current.total_loss_today + abs(realized)

        new_drawdown_pct = 0.0
        if equity is not None and equity > 0 and new_realized_pnl < 0:
            new_drawdown_pct = min((-new_realized_pnl / equity) * 100, 100.0)

        return DailyAccountState(
            account_id=fill.account_id,
            market_day=new_market_day,
            realized_pnl=new_realized_pnl,
            drawdown_pct=new_drawdown_pct,
            last_loss_at=new_last_loss_at,
            total_loss_today=new_total_loss_today,
            lots=lots,
            updated_at=utc_now(),
        )

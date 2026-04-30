from __future__ import annotations

from datetime import datetime, timezone, date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers.models import BrokerFillUpdateEvent
from backend.app.domain._base import utc_now


_ET = timezone(datetime(2000, 1, 1, tzinfo=timezone.utc).utcoffset() or __import__("datetime").timedelta(hours=-5))


def _et_market_day(dt: datetime) -> str:
    """Return the ET calendar date of *dt* as an ISO string ``YYYY-MM-DD``."""
    try:
        import zoneinfo
        et = zoneinfo.ZoneInfo("America/New_York")
        return dt.astimezone(et).date().isoformat()
    except Exception:
        # Fallback: fixed UTC-5 offset (no DST). Acceptable for a risk gate.
        offset = __import__("datetime").timedelta(hours=-5)
        et_dt = dt.astimezone(timezone(offset))
        return et_dt.date().isoformat()


def _fill_cash_flow(fill: BrokerFillUpdateEvent) -> float:
    """Net cash-flow contribution of a single fill.

    Sells bring cash in (+), buys spend cash (-). Accumulated across a
    market day this gives realized P&L for a flat-by-EOD account.
    """
    side = (fill.side or "").lower()
    if side in {"sell", "sell_short", "short"}:
        return fill.qty * fill.price
    return -(fill.qty * fill.price)


class DailyAccountState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    market_day: str
    realized_pnl: float = 0.0
    drawdown_pct: float = Field(default=0.0, ge=0)
    last_loss_at: datetime | None = None
    total_loss_today: float = Field(default=0.0, ge=0)
    updated_at: datetime = Field(default_factory=utc_now)


class DailyAccountStateAggregator:
    """Stateless helper: applies a single BrokerFillUpdateEvent to the current
    DailyAccountState and returns an updated immutable state.

    Caller is responsible for persistence and for threading the updated state
    into GovernorRequests.
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

        cash_flow = _fill_cash_flow(fill)
        new_realized_pnl = current.realized_pnl + cash_flow

        new_last_loss_at = current.last_loss_at
        new_total_loss_today = current.total_loss_today
        if cash_flow < 0:
            new_last_loss_at = fill.event_at
            new_total_loss_today = current.total_loss_today + abs(cash_flow)

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
            updated_at=utc_now(),
        )

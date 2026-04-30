from __future__ import annotations

from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.governor import (
    BrokerSyncFreshness,
    GovernorPolicy,
    GovernorRequest,
    PortfolioGovernor,
    PortfolioSnapshot,
)
from backend.app.orders import InternalOrderIntent
from backend.app.runtime import RuntimeState
from backend.app.runtime.daily_account_state import DailyAccountState
from backend.tests.fixtures.legacy_intent import LegacyExecutionIntent as ExecutionIntent

ACCOUNT_ID = uuid4()
DEPLOYMENT_ID = uuid4()
PROGRAM_ID = uuid4()

_NOW = datetime(2026, 4, 30, 15, 0, tzinfo=timezone.utc)
_MARKET_DAY = "2026-04-30"


def _daily_state(
    *,
    realized_pnl: float = 0.0,
    drawdown_pct: float = 0.0,
    last_loss_at: datetime | None = None,
    total_loss_today: float = 0.0,
) -> DailyAccountState:
    return DailyAccountState(
        account_id=ACCOUNT_ID,
        market_day=_MARKET_DAY,
        realized_pnl=realized_pnl,
        drawdown_pct=drawdown_pct,
        last_loss_at=last_loss_at,
        total_loss_today=total_loss_today,
    )


def _request(
    *,
    policy: GovernorPolicy = GovernorPolicy(),
    daily_state: DailyAccountState | None = None,
    equity: float | None = 10_000.0,
) -> tuple[PortfolioGovernor, GovernorRequest]:
    governor = PortfolioGovernor(policy)
    request = GovernorRequest(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        program_id=PROGRAM_ID,
        symbol="SPY",
        runtime_state=RuntimeState(deployment_id=DEPLOYMENT_ID),
        broker_sync=BrokerSyncFreshness(),
        portfolio=PortfolioSnapshot(equity=equity),
        order_intent=InternalOrderIntent.OPEN,
        daily_state=daily_state,
    )
    return governor, request


# ── daily_loss_pct_exceeded ──────────────────────────────────────────────────

class TestDailyLossLimit:
    def test_rejects_when_loss_equals_limit(self) -> None:
        policy = GovernorPolicy(max_daily_loss_pct=5.0)
        # equity=10_000, realized_pnl=-500 → 5%
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(realized_pnl=-500.0),
            equity=10_000,
        )
        decision = governor.evaluate(req)

        assert decision.approved is False
        assert decision.rule_id == "daily_loss_pct_exceeded"
        assert decision.reason == "daily_loss_limit_exceeded"

    def test_rejects_when_loss_exceeds_limit(self) -> None:
        policy = GovernorPolicy(max_daily_loss_pct=5.0)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(realized_pnl=-600.0),
            equity=10_000,
        )
        decision = governor.evaluate(req)

        assert decision.approved is False
        assert decision.rule_id == "daily_loss_pct_exceeded"

    def test_approves_when_loss_below_limit(self) -> None:
        policy = GovernorPolicy(max_daily_loss_pct=5.0)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(realized_pnl=-400.0),
            equity=10_000,
        )
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_approves_when_pnl_positive(self) -> None:
        policy = GovernorPolicy(max_daily_loss_pct=5.0)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(realized_pnl=200.0),
            equity=10_000,
        )
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_skipped_when_no_daily_state(self) -> None:
        policy = GovernorPolicy(max_daily_loss_pct=5.0)
        governor, req = _request(policy=policy, daily_state=None)
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_skipped_when_policy_not_set(self) -> None:
        governor, req = _request(
            policy=GovernorPolicy(),
            daily_state=_daily_state(realized_pnl=-9999.0),
            equity=10_000,
        )
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_skipped_when_equity_is_none(self) -> None:
        policy = GovernorPolicy(max_daily_loss_pct=5.0)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(realized_pnl=-600.0),
            equity=None,
        )
        # equity=None triggers portfolio_equity_unavailable first (fail-closed),
        # but the daily_loss check itself never fires when equity is None
        decision = governor.evaluate(req)
        assert decision.rule_id != "daily_loss_pct_exceeded"


# ── drawdown_pct_exceeded ────────────────────────────────────────────────────

class TestDrawdownLimit:
    def test_rejects_when_drawdown_equals_limit(self) -> None:
        policy = GovernorPolicy(max_drawdown_pct=3.0)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(drawdown_pct=3.0),
        )
        decision = governor.evaluate(req)

        assert decision.approved is False
        assert decision.rule_id == "drawdown_pct_exceeded"
        assert decision.reason == "daily_drawdown_limit_exceeded"

    def test_rejects_when_drawdown_exceeds_limit(self) -> None:
        policy = GovernorPolicy(max_drawdown_pct=3.0)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(drawdown_pct=4.5),
        )
        decision = governor.evaluate(req)

        assert decision.approved is False
        assert decision.rule_id == "drawdown_pct_exceeded"

    def test_approves_when_drawdown_below_limit(self) -> None:
        policy = GovernorPolicy(max_drawdown_pct=3.0)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(drawdown_pct=2.9),
        )
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_skipped_when_no_daily_state(self) -> None:
        policy = GovernorPolicy(max_drawdown_pct=3.0)
        governor, req = _request(policy=policy, daily_state=None)
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_skipped_when_policy_not_set(self) -> None:
        governor, req = _request(
            policy=GovernorPolicy(),
            daily_state=_daily_state(drawdown_pct=99.9),
        )
        decision = governor.evaluate(req)

        assert decision.approved is True


# ── cooldown_after_loss_active ───────────────────────────────────────────────

class TestCooldownAfterLoss:
    def test_rejects_within_cooldown_window(self) -> None:
        policy = GovernorPolicy(cooldown_after_loss_minutes=15)
        # last_loss_at 5 minutes ago → 10 minutes remaining
        last_loss = _NOW - timedelta(minutes=5)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(last_loss_at=last_loss),
        )

        # We cannot mock utc_now() inside the governor, but we can test the
        # elapsed calculation by setting last_loss_at to a very recent time
        # (1 second ago). The governor uses utc_now() at call time; as long as
        # the test runs in well under 15 minutes this will always be in cooldown.
        recent_loss = datetime.now(timezone.utc) - timedelta(seconds=1)
        governor2, req2 = _request(
            policy=policy,
            daily_state=_daily_state(last_loss_at=recent_loss),
        )
        decision = governor2.evaluate(req2)

        assert decision.approved is False
        assert decision.rule_id == "cooldown_after_loss_active"
        assert decision.reason == "cooldown_after_loss_active"

    def test_approves_after_cooldown_expires(self) -> None:
        policy = GovernorPolicy(cooldown_after_loss_minutes=15)
        old_loss = datetime.now(timezone.utc) - timedelta(minutes=20)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(last_loss_at=old_loss),
        )
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_approves_when_no_loss_today(self) -> None:
        policy = GovernorPolicy(cooldown_after_loss_minutes=15)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(last_loss_at=None),
        )
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_skipped_when_no_daily_state(self) -> None:
        policy = GovernorPolicy(cooldown_after_loss_minutes=15)
        governor, req = _request(policy=policy, daily_state=None)
        decision = governor.evaluate(req)

        assert decision.approved is True

    def test_skipped_when_policy_not_set(self) -> None:
        recent_loss = datetime.now(timezone.utc) - timedelta(seconds=1)
        governor, req = _request(
            policy=GovernorPolicy(),
            daily_state=_daily_state(last_loss_at=recent_loss),
        )
        decision = governor.evaluate(req)

        assert decision.approved is True


# ── precedence: earlier rules fire first ────────────────────────────────────

class TestRulePrecedence:
    def test_daily_loss_checked_before_drawdown(self) -> None:
        # Both daily_loss and drawdown triggered; daily_loss is first
        policy = GovernorPolicy(max_daily_loss_pct=5.0, max_drawdown_pct=3.0)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(realized_pnl=-600.0, drawdown_pct=4.0),
            equity=10_000,
        )
        decision = governor.evaluate(req)

        assert decision.rule_id == "daily_loss_pct_exceeded"

    def test_drawdown_checked_before_cooldown(self) -> None:
        policy = GovernorPolicy(
            max_drawdown_pct=3.0,
            cooldown_after_loss_minutes=15,
        )
        recent_loss = datetime.now(timezone.utc) - timedelta(seconds=1)
        governor, req = _request(
            policy=policy,
            daily_state=_daily_state(drawdown_pct=4.0, last_loss_at=recent_loss),
        )
        decision = governor.evaluate(req)

        assert decision.rule_id == "drawdown_pct_exceeded"

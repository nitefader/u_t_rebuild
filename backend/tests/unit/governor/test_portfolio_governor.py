from __future__ import annotations

from uuid import UUID

import pytest

from backend.app.governor import (
    BrokerSyncFreshness,
    GovernorPolicy,
    GovernorRequest,
    PendingOpenSummary,
    PortfolioGovernor,
    PortfolioSnapshot,
    PositionSummary,
)
from backend.app.orders import InternalOrderIntent, OrderManager, OrderManagerError
from backend.app.runtime import RuntimeState


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_ACCOUNT_ID = UUID("22222222-3333-4444-5555-666666666666")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
OTHER_DEPLOYMENT_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")


def _request(
    *,
    account_id: UUID = ACCOUNT_ID,
    deployment_id: UUID = DEPLOYMENT_ID,
    broker_sync: BrokerSyncFreshness | None = None,
    portfolio: PortfolioSnapshot | None = None,
    order_intent: InternalOrderIntent | None = None,
    candidate_market_value: float = 0,
    candidate_open_risk: float = 0,
) -> GovernorRequest:
    # W2-A-1b: tests that don't intentionally exercise the equity=None
    # fail-closed path get a non-None default equity so the new
    # portfolio_equity_unavailable rule does not pre-empt the rule each test
    # is actually checking. Tests that specifically test percentage gates set
    # their own equity (10_000 etc.). Tests that exercise the new fail-closed
    # rule pass an explicit ``portfolio=PortfolioSnapshot()`` (equity=None).
    return GovernorRequest(
        account_id=account_id,
        deployment_id=deployment_id,
        symbol="SPY",
        runtime_state=RuntimeState(deployment_id=deployment_id),
        broker_sync=broker_sync or BrokerSyncFreshness(),
        portfolio=portfolio if portfolio is not None else PortfolioSnapshot(equity=100_000),
        order_intent=order_intent,
        candidate_market_value=candidate_market_value,
        candidate_open_risk=candidate_open_risk,
    )


def test_approved_normal_open() -> None:
    decision = PortfolioGovernor().evaluate(_request())

    assert decision.approved is True
    assert decision.reason == "approved"
    assert decision.rule_id == "allow"
    assert decision.projected_state is not None
    assert decision.projected_state["projected_open_positions"] == 1


def test_governor_reloads_persisted_policy_without_restart() -> None:
    class _StateStore:
        def __init__(self) -> None:
            self.policy = GovernorPolicy()

        def load_portfolio_governor_state(self, _governor_id: str) -> GovernorPolicy:
            return self.policy

        def save_portfolio_governor_state(self, _governor_id: str, policy: GovernorPolicy) -> None:
            self.policy = policy

    store = _StateStore()
    governor = PortfolioGovernor(state_store=store)

    # Baseline: no global kill, OPEN is allowed.
    allowed = governor.evaluate(_request())
    assert allowed.approved is True

    # Simulate operator pause/kill update persisted after runtime start.
    store.save_portfolio_governor_state(
        "portfolio-governor",
        GovernorPolicy(global_kill_active=True),
    )

    blocked = governor.evaluate(_request())
    assert blocked.approved is False
    assert blocked.rule_id == "global_kill_blocks_open"


def test_governor_accepts_canonical_request_without_execution_intent() -> None:
    decision = PortfolioGovernor().evaluate(
        GovernorRequest(
            account_id=ACCOUNT_ID,
            deployment_id=DEPLOYMENT_ID,
            symbol="spy",
            runtime_state=RuntimeState(deployment_id=DEPLOYMENT_ID),
            broker_sync=BrokerSyncFreshness(),
            portfolio=PortfolioSnapshot(equity=100_000),
            order_intent=InternalOrderIntent.OPEN,
        )
    )

    assert decision.approved is True
    assert decision.projected_state is not None
    assert decision.projected_state["deployment_id"] == str(DEPLOYMENT_ID)
    assert decision.projected_state["symbol"] == "SPY"


def test_global_kill_rejects_open() -> None:
    governor = PortfolioGovernor(GovernorPolicy(global_kill_active=True))

    decision = governor.evaluate(_request())

    assert decision.approved is False
    assert decision.reason == "global_kill_active"
    assert decision.rule_id == "global_kill_blocks_open"


def test_account_pause_rejects_only_that_account() -> None:
    governor = PortfolioGovernor(GovernorPolicy(paused_account_ids=frozenset({ACCOUNT_ID})))

    blocked = governor.evaluate(_request(account_id=ACCOUNT_ID))
    allowed = governor.evaluate(_request(account_id=OTHER_ACCOUNT_ID))

    assert blocked.approved is False
    assert blocked.reason == "account_pause_active"
    assert allowed.approved is True


def test_deployment_pause_rejects_only_that_deployment() -> None:
    governor = PortfolioGovernor(GovernorPolicy(paused_deployment_ids=frozenset({DEPLOYMENT_ID})))

    blocked = governor.evaluate(_request(deployment_id=DEPLOYMENT_ID))
    allowed = governor.evaluate(_request(deployment_id=OTHER_DEPLOYMENT_ID))

    assert blocked.approved is False
    assert blocked.reason == "deployment_pause_active"
    assert allowed.approved is True


def test_stale_broker_sync_rejects_open() -> None:
    decision = PortfolioGovernor().evaluate(_request(broker_sync=BrokerSyncFreshness(is_stale=True, reason="timeout")))

    assert decision.approved is False
    assert decision.reason == "broker_sync_stale"
    assert decision.rule_id == "stale_broker_sync_blocks_open"


def test_protective_close_tp_sl_allowed_during_pause() -> None:
    governor = PortfolioGovernor(
        GovernorPolicy(
            global_kill_active=True,
            paused_account_ids=frozenset({ACCOUNT_ID}),
            paused_deployment_ids=frozenset({DEPLOYMENT_ID}),
        )
    )

    close_decision = governor.evaluate(_request(order_intent=InternalOrderIntent.CLOSE))
    tp_decision = governor.evaluate(_request(order_intent=InternalOrderIntent.TAKE_PROFIT))
    sl_decision = governor.evaluate(_request(order_intent=InternalOrderIntent.STOP_LOSS))

    assert close_decision.approved is True
    assert tp_decision.approved is True
    assert sl_decision.approved is True
    assert close_decision.reason == "protective_exit_allowed"


@pytest.mark.parametrize(
    "order_intent",
    [
        InternalOrderIntent.CLOSE,
        InternalOrderIntent.REDUCE,
        InternalOrderIntent.TARGET,
        InternalOrderIntent.STOP,
        InternalOrderIntent.TRAIL,
        InternalOrderIntent.BREAKEVEN,
        InternalOrderIntent.RUNNER,
        InternalOrderIntent.LOGICAL_EXIT,
        InternalOrderIntent.TAKE_PROFIT,
        InternalOrderIntent.STOP_LOSS,
        InternalOrderIntent.SCALE,
    ],
)
def test_all_position_management_intents_allowed_during_pause(order_intent: InternalOrderIntent) -> None:
    governor = PortfolioGovernor(
        GovernorPolicy(
            global_kill_active=True,
            paused_account_ids=frozenset({ACCOUNT_ID}),
            paused_deployment_ids=frozenset({DEPLOYMENT_ID}),
        )
    )

    decision = governor.evaluate(_request(order_intent=order_intent))

    assert decision.approved is True
    assert decision.reason == "protective_exit_allowed"
    assert decision.projected_state is not None
    assert decision.projected_state["order_intent"] == order_intent.value


def test_max_positions_rejects() -> None:
    portfolio = PortfolioSnapshot(
        equity=100_000,
        positions=(
            PositionSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                symbol="SPY",
                quantity=10,
                market_value=1000,
            ),
        ),
    )
    governor = PortfolioGovernor(GovernorPolicy(max_open_positions=1))

    decision = governor.evaluate(_request(portfolio=portfolio))

    assert decision.approved is False
    assert decision.reason == "max_open_positions_exceeded"
    assert decision.rule_id == "max_open_positions"


def test_projected_exposure_rejection() -> None:
    portfolio = PortfolioSnapshot(equity=10_000)
    governor = PortfolioGovernor(GovernorPolicy(max_gross_exposure_pct=50))

    decision = governor.evaluate(_request(portfolio=portfolio, candidate_market_value=6_000))

    assert decision.approved is False
    assert decision.reason == "projected_gross_exposure_exceeded"
    assert decision.rule_id == "max_gross_exposure_pct"
    assert decision.projected_state is not None
    assert decision.projected_state["gross_exposure_pct"] == 60


def test_symbol_concentration_rejection() -> None:
    portfolio = PortfolioSnapshot(
        equity=10_000,
        positions=(
            PositionSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                symbol="QQQ",
                quantity=10,
                market_value=4_000,
            ),
        ),
    )
    governor = PortfolioGovernor(GovernorPolicy(max_symbol_concentration_pct=40))

    decision = governor.evaluate(_request(portfolio=portfolio, candidate_market_value=6_000))

    assert decision.approved is False
    assert decision.reason == "symbol_concentration_exceeded"
    assert decision.rule_id == "max_symbol_concentration_pct"
    assert decision.projected_state is not None
    assert decision.projected_state["symbol_concentration_pct"] == 60


def test_open_risk_rejection() -> None:
    portfolio = PortfolioSnapshot(
        equity=10_000,
        positions=(
            PositionSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                symbol="QQQ",
                quantity=10,
                market_value=2_000,
                open_risk=200,
            ),
        ),
        pending_opens=(
            PendingOpenSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                symbol="IWM",
                quantity=10,
                market_value=1_000,
                open_risk=100,
            ),
        ),
    )
    governor = PortfolioGovernor(GovernorPolicy(max_open_risk_pct=4))

    decision = governor.evaluate(_request(portfolio=portfolio, candidate_open_risk=200))

    assert decision.approved is False
    assert decision.reason == "open_risk_exceeded"
    assert decision.rule_id == "max_open_risk_pct"
    assert decision.projected_state is not None
    assert decision.projected_state["open_risk_pct"] == 5
    assert decision.projected_state["pending_open_risk_pct"] == 3


def test_rejected_intent_never_creates_order() -> None:
    manager = OrderManager()

    with pytest.raises(OrderManagerError, match="legacy ExecutionIntent/Program order creation has been removed"):
        manager.create_order(account_id=ACCOUNT_ID, execution_intent=object())

    assert manager.ledger.all() == ()


def test_symbol_concentration_projected_state() -> None:
    portfolio = PortfolioSnapshot(
        equity=10_000,
        positions=(
            PositionSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                symbol="SPY",
                quantity=10,
                market_value=1000,
            ),
        )
    )
    governor = PortfolioGovernor(GovernorPolicy(max_symbol_concentration_pct=100))

    decision = governor.evaluate(_request(portfolio=portfolio, candidate_market_value=1_000))

    assert decision.approved is True
    assert decision.projected_state is not None
    assert decision.projected_state["symbol_concentration_pct"] == 100


def test_protective_exit_allowed_under_all_conditions() -> None:
    portfolio = PortfolioSnapshot(equity=10_000)
    governor = PortfolioGovernor(
        GovernorPolicy(
            global_kill_active=True,
            paused_account_ids=frozenset({ACCOUNT_ID}),
            paused_deployment_ids=frozenset({DEPLOYMENT_ID}),
            max_gross_exposure_pct=1,
            max_net_exposure_pct=1,
            max_symbol_concentration_pct=1,
            max_open_risk_pct=1,
        )
    )

    decision = governor.evaluate(
        _request(
            broker_sync=BrokerSyncFreshness(is_stale=True, reason="timeout"),
            portfolio=portfolio,
            order_intent=InternalOrderIntent.STOP_LOSS,
            candidate_market_value=100_000,
            candidate_open_risk=100_000,
        )
    )

    assert decision.approved is True
    assert decision.reason == "protective_exit_allowed"
    assert decision.projected_state is not None
    assert decision.projected_state["broker_sync_stale"] is True


def test_governor_has_no_feature_engine_or_broker_adapter_dependency() -> None:
    import backend.app.governor.service as governor_service

    source_names = governor_service.PortfolioGovernor.evaluate.__globals__

    assert "FeatureEngine" not in source_names
    assert "BrokerAdapter" not in source_names


# ---------------------------------------------------------------------------
# policy_override (Slice A — GOVERNOR_WIRING_MAP §G-2)
# Per-evaluation policy must override the persisted singleton without
# mutating self._policy.
# ---------------------------------------------------------------------------


def test_policy_override_blocks_when_persisted_would_allow() -> None:
    governor = PortfolioGovernor()  # persisted policy: all None, no gates
    tighter = GovernorPolicy(max_open_positions=0)
    decision = governor.evaluate(_request(), policy_override=tighter)
    assert decision.approved is False
    assert decision.reason == "max_open_positions_exceeded"
    assert decision.rule_id == "max_open_positions"


def test_policy_override_allows_when_persisted_would_block_kill_via_override_does_not_relax_kill() -> None:
    # The override is applied verbatim — if it carries kill or pause, those
    # gates fire too. This guards against accidentally constructing an
    # override that "loses" a kill switch from the floor (the resolver's job
    # is to preserve kill/pause; this test confirms evaluate honors whatever
    # policy it gets).
    governor = PortfolioGovernor()
    kill_override = GovernorPolicy(global_kill_active=True)
    decision = governor.evaluate(_request(), policy_override=kill_override)
    assert decision.approved is False
    assert decision.reason == "global_kill_active"


def test_policy_override_does_not_mutate_persisted_policy() -> None:
    governor = PortfolioGovernor()
    persisted_before = governor.policy
    governor.evaluate(_request(), policy_override=GovernorPolicy(max_open_positions=0))
    assert governor.policy is persisted_before
    assert governor.policy.max_open_positions is None


def test_policy_override_omitted_uses_persisted_policy() -> None:
    # Backwards-compat sanity: the new keyword default is None and the
    # behavior matches today's evaluate().
    governor = PortfolioGovernor(GovernorPolicy(max_open_positions=0))
    decision = governor.evaluate(_request())
    assert decision.approved is False
    assert decision.reason == "max_open_positions_exceeded"


def test_policy_override_projected_state_uses_override_for_slots_remaining() -> None:
    # The projected_state's new_open_slots_remaining must be computed from
    # the policy that actually made the decision, not from self._policy.
    governor = PortfolioGovernor()  # persisted: None, would yield None slots
    override = GovernorPolicy(max_open_positions=3)
    decision = governor.evaluate(_request(), policy_override=override)
    assert decision.approved is True
    assert decision.projected_state is not None
    assert decision.projected_state["new_open_slots_remaining"] == 2  # 3 - 1


# ---------------------------------------------------------------------------
# Slice B: account_missing_risk_plan_for_horizon rejection rule
# Fires when active_policy.requires_risk_plan is True, AFTER kill/pause
# checks but BEFORE numeric limit checks.
# ---------------------------------------------------------------------------


def test_missing_risk_plan_rule_rejects_entry() -> None:
    governor = PortfolioGovernor()
    policy = GovernorPolicy(requires_risk_plan=True)

    decision = governor.evaluate(_request(), policy_override=policy)

    assert decision.approved is False
    assert decision.reason == "account_has_no_risk_plan_for_horizon"
    assert decision.rule_id == "account_missing_risk_plan_for_horizon"


def test_missing_risk_plan_rule_does_not_block_protective_exit() -> None:
    """Protective exits (STOP, CLOSE, etc.) bypass ALL rules including the plan check."""
    governor = PortfolioGovernor()
    policy = GovernorPolicy(requires_risk_plan=True)

    decision = governor.evaluate(
        _request(order_intent=InternalOrderIntent.STOP_LOSS),
        policy_override=policy,
    )

    assert decision.approved is True
    assert decision.reason == "protective_exit_allowed"


def test_missing_risk_plan_rule_fires_after_kill_switch() -> None:
    """Global kill fires before the missing-plan rule. Order matters."""
    governor = PortfolioGovernor()
    policy = GovernorPolicy(global_kill_active=True, requires_risk_plan=True)

    decision = governor.evaluate(_request(), policy_override=policy)

    # Kill takes precedence — the missing-plan rule is later in the chain.
    assert decision.approved is False
    assert decision.rule_id == "global_kill_blocks_open"


def test_missing_risk_plan_rule_fires_after_account_pause() -> None:
    governor = PortfolioGovernor()
    policy = GovernorPolicy(paused_account_ids=frozenset({ACCOUNT_ID}), requires_risk_plan=True)

    decision = governor.evaluate(_request(account_id=ACCOUNT_ID), policy_override=policy)

    assert decision.approved is False
    assert decision.rule_id == "account_pause_blocks_open"


def test_missing_risk_plan_rule_fires_before_numeric_limits() -> None:
    """requires_risk_plan must fire before max_open_positions so the rejection
    reason clearly names the missing plan (not a confusing 'max positions' reason)."""
    governor = PortfolioGovernor()
    # Both a missing plan and a positions limit exceeded.
    policy = GovernorPolicy(requires_risk_plan=True, max_open_positions=0)

    decision = governor.evaluate(_request(), policy_override=policy)

    assert decision.approved is False
    # Missing-plan check fires first.
    assert decision.rule_id == "account_missing_risk_plan_for_horizon"


def test_missing_risk_plan_false_does_not_block() -> None:
    """When requires_risk_plan=False (default), the rule must not fire."""
    governor = PortfolioGovernor()
    policy = GovernorPolicy(requires_risk_plan=False)

    decision = governor.evaluate(_request(), policy_override=policy)

    assert decision.approved is True


# ---------------------------------------------------------------------------
# W2-A-1b (audit P0 #2 — pre-T-7 bundle, operator decision 2026-04-30):
# PortfolioSnapshot.equity=None must fail-closed for OPEN intents because
# percentage gates collapse to zero via _pct() when equity is falsy. The
# new rule must fire AFTER protective-exit bypass and AFTER kill/pause/stale
# rules so existing higher-priority rejections still surface their reason.
# ---------------------------------------------------------------------------


def test_equity_none_rejects_open_with_portfolio_equity_unavailable() -> None:
    """Without equity, percentage gates cannot be trusted; open must fail closed."""
    governor = PortfolioGovernor()

    decision = governor.evaluate(_request(portfolio=PortfolioSnapshot()))

    assert decision.approved is False
    assert decision.reason == "portfolio_equity_unavailable"
    assert decision.rule_id == "portfolio_equity_unavailable"


def test_equity_none_does_not_block_protective_exit() -> None:
    """Protective exits bypass equity check the same way they bypass everything else."""
    governor = PortfolioGovernor()

    decision = governor.evaluate(
        _request(
            order_intent=InternalOrderIntent.STOP_LOSS,
            portfolio=PortfolioSnapshot(),
        )
    )

    assert decision.approved is True
    assert decision.reason == "protective_exit_allowed"


def test_equity_none_fires_after_kill_switch() -> None:
    """Global kill is stricter than equity-unavailable; kill rule must surface first."""
    governor = PortfolioGovernor(GovernorPolicy(global_kill_active=True))

    decision = governor.evaluate(_request(portfolio=PortfolioSnapshot()))

    assert decision.approved is False
    assert decision.rule_id == "global_kill_blocks_open"


def test_equity_none_fires_after_stale_broker_sync() -> None:
    """Stale sync is stricter than equity-unavailable; stale rule must surface first."""
    governor = PortfolioGovernor()

    decision = governor.evaluate(
        _request(
            broker_sync=BrokerSyncFreshness(is_stale=True, reason="timeout"),
            portfolio=PortfolioSnapshot(),
        )
    )

    assert decision.approved is False
    assert decision.rule_id == "stale_broker_sync_blocks_open"


def test_equity_none_does_not_block_when_intent_is_open_with_explicit_intent() -> None:
    """Confirm fail-closed fires when explicit OPEN intent is set, not just default."""
    governor = PortfolioGovernor()

    decision = governor.evaluate(
        _request(
            order_intent=InternalOrderIntent.OPEN,
            portfolio=PortfolioSnapshot(),
        )
    )

    assert decision.approved is False
    assert decision.rule_id == "portfolio_equity_unavailable"


# ---------------------------------------------------------------------------
# W2-A-1a (audit P0 #1 — pre-T-7 bundle):
# GovernorRequest must carry non-zero candidate_market_value /
# candidate_open_risk on opening evaluations so the percentage gates evaluate
# against real incremental exposure. The audit's confirmed silent-no-op was
# that the orchestrator built GovernorRequest with these fields at their
# zero default and so max_gross_exposure_pct / max_open_risk_pct never fired.
# This test set guards against regressing back to that silent behavior.
# ---------------------------------------------------------------------------


def test_zero_candidate_market_value_skips_gross_exposure_cap_silently() -> None:
    """Regression guard: with candidate_market_value=0, an OPEN that should
    breach the cap is silently approved. This documents the broken pre-fix
    behavior so any future regression is visible.

    The orchestrator's _governor_candidate_inputs helper is what makes this
    not happen in production — see test_runtime_orchestrator.py for that
    integration test. This unit test just locks the math contract.
    """
    portfolio = PortfolioSnapshot(equity=10_000)
    governor = PortfolioGovernor(GovernorPolicy(max_gross_exposure_pct=50))

    # candidate_market_value=0 — the broken pre-fix shape.
    decision = governor.evaluate(_request(portfolio=portfolio, candidate_market_value=0))

    # With zero candidate exposure, the projected gross is 0/10_000 = 0% which
    # is under the 50% cap. The cap silently does not fire.
    assert decision.approved is True
    assert decision.projected_state is not None
    assert decision.projected_state["gross_exposure_pct"] == 0


def test_populated_candidate_market_value_makes_gross_exposure_cap_fire() -> None:
    """The cap fires once candidate_market_value carries the real qty*price."""
    portfolio = PortfolioSnapshot(equity=10_000)
    governor = PortfolioGovernor(GovernorPolicy(max_gross_exposure_pct=50))

    # qty=100 @ $60 = $6_000 = 60% of $10_000 equity → exceeds 50% cap.
    decision = governor.evaluate(_request(portfolio=portfolio, candidate_market_value=6_000))

    assert decision.approved is False
    assert decision.rule_id == "max_gross_exposure_pct"
    assert decision.projected_state is not None
    assert decision.projected_state["gross_exposure_pct"] == 60


def test_populated_candidate_open_risk_makes_open_risk_cap_fire() -> None:
    """The open_risk cap fires once candidate_open_risk carries qty * stop_distance."""
    portfolio = PortfolioSnapshot(equity=10_000)
    governor = PortfolioGovernor(GovernorPolicy(max_open_risk_pct=2))

    # qty=100 with $3 stop distance → $300 candidate open risk = 3% of equity → exceeds 2%.
    decision = governor.evaluate(_request(portfolio=portfolio, candidate_open_risk=300))

    assert decision.approved is False
    assert decision.rule_id == "max_open_risk_pct"
    assert decision.projected_state is not None
    assert decision.projected_state["open_risk_pct"] == 3


def test_candidate_inputs_zero_for_protective_exit_intents() -> None:
    """Protective exits never contribute candidate exposure; _projected_state
    zeros these fields anyway, but the orchestrator helper short-circuits
    before that. This test pins the protective-exit math contract."""
    portfolio = PortfolioSnapshot(equity=10_000)
    governor = PortfolioGovernor(GovernorPolicy(max_gross_exposure_pct=50))

    # Even with a hostile candidate_market_value passed in, a protective exit
    # bypasses all numeric checks via _is_protective_exit() at the top of
    # evaluate(). Operator can rely on this when a partial-fill exit lands
    # on a fully-loaded book.
    decision = governor.evaluate(
        _request(
            order_intent=InternalOrderIntent.STOP_LOSS,
            portfolio=portfolio,
            candidate_market_value=100_000,
            candidate_open_risk=100_000,
        )
    )

    assert decision.approved is True
    assert decision.reason == "protective_exit_allowed"

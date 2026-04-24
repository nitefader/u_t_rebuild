from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
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
from backend.app.runtime import ExecutionIntent, RuntimeState


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_ACCOUNT_ID = UUID("22222222-3333-4444-5555-666666666666")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
OTHER_DEPLOYMENT_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
PROGRAM_ID = UUID("99999999-8888-7777-6666-555555555555")


def _intent(
    *,
    deployment_id: UUID = DEPLOYMENT_ID,
    intent_type: IntentType = IntentType.ENTRY,
    approved: bool = False,
) -> ExecutionIntent:
    return ExecutionIntent(
        deployment_id=deployment_id,
        program_version_id=PROGRAM_ID,
        symbol="SPY",
        side=CandidateSide.LONG,
        intent_type=intent_type,
        qty=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        signal_name="entry",
        reason="signal_condition_true",
        governor_approved=approved,
        governor_reason="approved" if approved else None,
    )


def _request(
    *,
    account_id: UUID = ACCOUNT_ID,
    intent: ExecutionIntent | None = None,
    broker_sync: BrokerSyncFreshness | None = None,
    portfolio: PortfolioSnapshot | None = None,
    order_intent: InternalOrderIntent | None = None,
    candidate_market_value: float = 0,
    candidate_open_risk: float = 0,
) -> GovernorRequest:
    execution_intent = intent or _intent()
    return GovernorRequest(
        account_id=account_id,
        execution_intent=execution_intent,
        runtime_state=RuntimeState(deployment_id=execution_intent.deployment_id),
        broker_sync=broker_sync or BrokerSyncFreshness(),
        portfolio=portfolio or PortfolioSnapshot(),
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

    blocked = governor.evaluate(_request(intent=_intent(deployment_id=DEPLOYMENT_ID)))
    allowed = governor.evaluate(_request(intent=_intent(deployment_id=OTHER_DEPLOYMENT_ID)))

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
    exit_intent = _intent(intent_type=IntentType.EXIT)

    close_decision = governor.evaluate(_request(intent=exit_intent, order_intent=InternalOrderIntent.CLOSE))
    tp_decision = governor.evaluate(_request(intent=exit_intent, order_intent=InternalOrderIntent.TAKE_PROFIT))
    sl_decision = governor.evaluate(_request(intent=exit_intent, order_intent=InternalOrderIntent.STOP_LOSS))

    assert close_decision.approved is True
    assert tp_decision.approved is True
    assert sl_decision.approved is True
    assert close_decision.reason == "protective_exit_allowed"


def test_max_positions_rejects() -> None:
    portfolio = PortfolioSnapshot(
        positions=(
            PositionSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                program_id=PROGRAM_ID,
                symbol="SPY",
                quantity=10,
                market_value=1000,
            ),
        )
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
                program_id=PROGRAM_ID,
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
                program_id=PROGRAM_ID,
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
                program_id=PROGRAM_ID,
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
    decision = PortfolioGovernor(GovernorPolicy(global_kill_active=True)).evaluate(_request())
    rejected_intent = _intent(approved=decision.approved)

    with pytest.raises(OrderManagerError):
        manager.create_order(account_id=ACCOUNT_ID, execution_intent=rejected_intent)

    assert manager.ledger.all() == ()


def test_symbol_concentration_projected_state() -> None:
    portfolio = PortfolioSnapshot(
        equity=10_000,
        positions=(
            PositionSummary(
                account_id=ACCOUNT_ID,
                deployment_id=DEPLOYMENT_ID,
                program_id=PROGRAM_ID,
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
            intent=_intent(intent_type=IntentType.EXIT),
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

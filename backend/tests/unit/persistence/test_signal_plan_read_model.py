from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    SignalPlan,
    SignalPlanIntent,
    SignalPlanSide,
)
from backend.app.persistence import SQLiteRuntimeStore


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
OTHER_DEPLOYMENT_ID = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
STRATEGY_ID = UUID("99999999-8888-7777-6666-555555555555")
STRATEGY_VERSION_ID = UUID("88888888-7777-6666-5555-444444444444")
NOW = datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc)


def _signal_plan(
    *,
    signal_plan_id: UUID | None = None,
    deployment_id: UUID = DEPLOYMENT_ID,
    symbol: str = "SPY",
    created_at: datetime = NOW,
) -> SignalPlan:
    return SignalPlan(
        signal_plan_id=signal_plan_id or uuid4(),
        deployment_id=deployment_id,
        strategy_id=STRATEGY_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        symbol=symbol,
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        created_at=created_at,
    )


def _evaluation(signal_plan: SignalPlan) -> AccountSignalPlanEvaluation:
    return AccountSignalPlanEvaluation(
        evaluation_id=uuid4(),
        account_id=ACCOUNT_ID,
        signal_plan_id=signal_plan.signal_plan_id,
        deployment_id=signal_plan.deployment_id,
        strategy_id=signal_plan.strategy_id,
        status=AccountEvaluationStatus.ACCEPTED,
        participation_decision=AccountParticipationDecision.PARTICIPATE,
        evaluated_at=NOW,
    )


def test_signal_plan_round_trips_across_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "runtime.sqlite"
    store_a = SQLiteRuntimeStore(db_path)
    plan = _signal_plan()

    store_a.save_signal_plan(plan)

    store_b = SQLiteRuntimeStore(db_path)

    assert store_b.load_signal_plan(plan.signal_plan_id) == plan


def test_signal_plan_list_filters_by_deployment_symbol_and_account(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite")
    target = _signal_plan(symbol="SPY", created_at=NOW)
    other_symbol = _signal_plan(symbol="QQQ", created_at=NOW - timedelta(minutes=1))
    other_deployment = _signal_plan(deployment_id=OTHER_DEPLOYMENT_ID, symbol="SPY")
    for plan in (target, other_symbol, other_deployment):
        store.save_signal_plan(plan)
    store.save_account_signal_plan_evaluation(_evaluation(target))

    rows = store.list_signal_plans(
        account_id=ACCOUNT_ID,
        deployment_id=DEPLOYMENT_ID,
        symbol="spy",
    )

    assert rows == (target,)


def test_signal_plan_list_is_newest_created_first_and_limited(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite")
    older = _signal_plan(created_at=NOW - timedelta(minutes=5))
    newer = _signal_plan(created_at=NOW)
    store.save_signal_plan(older)
    store.save_signal_plan(newer)

    rows = store.list_signal_plans(limit=1)

    assert rows == (newer,)

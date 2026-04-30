"""W2-A-2 (audit P0 #2 — pre-T-7 bundle, 2026-04-30).

Persistence contract for AccountSignalPlanEvaluation. Pre-W2-A the
RuntimeOrchestrator built these in memory and Operations reconstructed them
from the order ledger only, so PARTICIPATE-without-order, REJECT, IGNORE,
and DEFER decisions were invisible. The new ``account_signal_plan_evaluations``
table + repo methods give Operations a durable read path independent of the
order ledger.

Test scope:
- save / load round-trip across SQLiteRuntimeStore reopen (restart-safety).
- list filters by account_id, deployment_id, signal_plan_id.
- list ordering by persisted_at DESC is stable.
- save is idempotent on evaluation_id (subsequent writes upsert payload).
- Non-order participation decisions (REJECT, IGNORE, DEFER) round-trip.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
)
from backend.app.persistence import SQLiteRuntimeStore


ACCOUNT_A = UUID("11111111-2222-3333-4444-555555555555")
ACCOUNT_B = UUID("22222222-3333-4444-5555-666666666666")
DEPLOYMENT_A = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
DEPLOYMENT_B = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")
STRATEGY_A = UUID("99999999-8888-7777-6666-555555555555")


def _evaluation(
    *,
    evaluation_id: UUID | None = None,
    account_id: UUID = ACCOUNT_A,
    signal_plan_id: UUID | None = None,
    deployment_id: UUID = DEPLOYMENT_A,
    strategy_id: UUID = STRATEGY_A,
    status: AccountEvaluationStatus = AccountEvaluationStatus.ACCEPTED,
    participation: AccountParticipationDecision = AccountParticipationDecision.PARTICIPATE,
    rejection_reasons: tuple[str, ...] = (),
    governor_decision: GovernorDecisionTrace | None = None,
    evaluated_at: datetime | None = None,
) -> AccountSignalPlanEvaluation:
    return AccountSignalPlanEvaluation(
        evaluation_id=evaluation_id or uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan_id or uuid4(),
        deployment_id=deployment_id,
        strategy_id=strategy_id,
        status=status,
        participation_decision=participation,
        risk_resolver_result=None,
        governor_decision=governor_decision,
        evaluated_at=evaluated_at or datetime(2026, 4, 30, 12, 0, tzinfo=timezone.utc),
        rejection_reasons=rejection_reasons,
    )


def _governor_trace(*, signal_plan_id: UUID, account_id: UUID = ACCOUNT_A, approved: bool = True) -> GovernorDecisionTrace:
    return GovernorDecisionTrace(
        governor_decision_id=uuid4(),
        account_id=account_id,
        signal_plan_id=signal_plan_id,
        status=GovernorDecisionStatus.APPROVED if approved else GovernorDecisionStatus.REJECTED,
        approved=approved,
        reasons=("approved",) if approved else ("max_open_positions_exceeded",),
    )


def test_save_and_load_round_trip_across_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "evaluations.sqlite"
    store_a = SQLiteRuntimeStore(db_path)
    evaluation = _evaluation()

    store_a.save_account_signal_plan_evaluation(evaluation)

    # Reopen the same SQLite file in a fresh store instance — simulates a
    # process restart. Persistence must survive.
    store_b = SQLiteRuntimeStore(db_path)
    loaded = store_b.load_account_signal_plan_evaluation(evaluation.evaluation_id)

    assert loaded == evaluation


def test_load_unknown_evaluation_raises_key_error(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    try:
        store.load_account_signal_plan_evaluation(uuid4())
        raise AssertionError("expected KeyError for unknown evaluation_id")
    except KeyError:
        pass


def test_save_is_idempotent_on_evaluation_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Re-saving the same evaluation_id must overwrite payload without error."""
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    evaluation_id = uuid4()
    first = _evaluation(evaluation_id=evaluation_id, status=AccountEvaluationStatus.ACCEPTED)
    second = _evaluation(
        evaluation_id=evaluation_id,
        status=AccountEvaluationStatus.BLOCKED,
        participation=AccountParticipationDecision.REJECT,
        signal_plan_id=first.signal_plan_id,
        rejection_reasons=("revised",),
    )

    store.save_account_signal_plan_evaluation(first)
    store.save_account_signal_plan_evaluation(second)
    loaded = store.load_account_signal_plan_evaluation(evaluation_id)

    assert loaded.status == AccountEvaluationStatus.BLOCKED
    assert loaded.participation_decision == AccountParticipationDecision.REJECT
    assert loaded.rejection_reasons == ("revised",)


def test_list_filter_by_account_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    eval_a = _evaluation(account_id=ACCOUNT_A)
    eval_b = _evaluation(account_id=ACCOUNT_B)
    store.save_account_signal_plan_evaluation(eval_a)
    store.save_account_signal_plan_evaluation(eval_b)

    only_a = store.list_account_signal_plan_evaluations(account_id=ACCOUNT_A)

    assert len(only_a) == 1
    assert only_a[0].account_id == ACCOUNT_A


def test_list_filter_by_deployment_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    eval_a = _evaluation(deployment_id=DEPLOYMENT_A)
    eval_b = _evaluation(deployment_id=DEPLOYMENT_B)
    store.save_account_signal_plan_evaluation(eval_a)
    store.save_account_signal_plan_evaluation(eval_b)

    only_a = store.list_account_signal_plan_evaluations(deployment_id=DEPLOYMENT_A)

    assert len(only_a) == 1
    assert only_a[0].deployment_id == DEPLOYMENT_A


def test_list_filter_by_signal_plan_id(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Both Accounts evaluating the SAME SignalPlan are visible — that's the
    audit's missing visibility (e.g., one Account REJECTs while another
    PARTICIPATEs; pre-W2-A only the order-creating one was visible)."""
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    plan_id = uuid4()
    eval_a = _evaluation(account_id=ACCOUNT_A, signal_plan_id=plan_id)
    eval_b = _evaluation(
        account_id=ACCOUNT_B,
        signal_plan_id=plan_id,
        status=AccountEvaluationStatus.BLOCKED,
        participation=AccountParticipationDecision.REJECT,
        rejection_reasons=("max_open_positions_exceeded",),
    )
    store.save_account_signal_plan_evaluation(eval_a)
    store.save_account_signal_plan_evaluation(eval_b)

    rows = store.list_account_signal_plan_evaluations(signal_plan_id=plan_id)

    assert len(rows) == 2
    decisions = {row.participation_decision for row in rows}
    assert decisions == {
        AccountParticipationDecision.PARTICIPATE,
        AccountParticipationDecision.REJECT,
    }


def test_list_orders_newest_persisted_first(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """persisted_at DESC is the stable ordering. Three saves in a row must
    return in reverse-write order regardless of evaluated_at."""
    import time
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    earliest_eval_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    latest_eval_at = datetime(2026, 12, 31, tzinfo=timezone.utc)

    # Save: oldest evaluated_at first, newest evaluated_at second.
    # persisted_at is assigned at save time, so the LATER write wins ordering.
    first_saved = _evaluation(evaluated_at=latest_eval_at)
    store.save_account_signal_plan_evaluation(first_saved)
    time.sleep(0.005)  # ensure persisted_at differs at ms granularity
    second_saved = _evaluation(evaluated_at=earliest_eval_at)
    store.save_account_signal_plan_evaluation(second_saved)

    rows = store.list_account_signal_plan_evaluations()

    assert len(rows) == 2
    # Second write was persisted later, so it appears first regardless of
    # the evaluated_at "future" date on the first write.
    assert rows[0].evaluation_id == second_saved.evaluation_id
    assert rows[1].evaluation_id == first_saved.evaluation_id


def test_non_order_decisions_round_trip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """REJECT, IGNORE, DEFER decisions persist with their full reason context.

    This is the audit's headline gap — these never appeared in Operations
    pre-W2-A because they didn't create orders.
    """
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    plan_id = uuid4()
    rejected = _evaluation(
        signal_plan_id=plan_id,
        status=AccountEvaluationStatus.BLOCKED,
        participation=AccountParticipationDecision.REJECT,
        rejection_reasons=("portfolio_equity_unavailable",),
        governor_decision=_governor_trace(signal_plan_id=plan_id, approved=False),
    )
    ignored = _evaluation(
        signal_plan_id=uuid4(),
        status=AccountEvaluationStatus.BLOCKED,
        participation=AccountParticipationDecision.IGNORE,
        rejection_reasons=("account_has_no_matching_position",),
    )
    deferred = _evaluation(
        signal_plan_id=uuid4(),
        status=AccountEvaluationStatus.BLOCKED,
        participation=AccountParticipationDecision.DEFER,
    )

    for evaluation in (rejected, ignored, deferred):
        store.save_account_signal_plan_evaluation(evaluation)

    rows = {
        row.participation_decision: row
        for row in store.list_account_signal_plan_evaluations()
    }

    assert rows[AccountParticipationDecision.REJECT].rejection_reasons == ("portfolio_equity_unavailable",)
    assert rows[AccountParticipationDecision.REJECT].governor_decision is not None
    assert rows[AccountParticipationDecision.IGNORE].rejection_reasons == ("account_has_no_matching_position",)
    assert rows[AccountParticipationDecision.DEFER].rejection_reasons == ()


def test_list_limit_is_clamped(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Hostile callers cannot exhaust memory via large limit values."""
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    # Save 6 rows, then list with a hostile limit of 99_999 — must clamp to
    # at most 500 (cap), but our 6 rows are well under.
    for _ in range(6):
        store.save_account_signal_plan_evaluation(_evaluation())
    rows = store.list_account_signal_plan_evaluations(limit=99_999)

    assert len(rows) == 6  # all of our rows; cap doesn't truncate them


def test_list_limit_caps_at_500(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The bounded_limit clamp at 500 is honored even for a small request
    window (no off-by-one on the lower bound either)."""
    store = SQLiteRuntimeStore(tmp_path / "evaluations.sqlite")
    # A limit below 1 must clamp to 1, not 0 or negative.
    store.save_account_signal_plan_evaluation(_evaluation())
    rows = store.list_account_signal_plan_evaluations(limit=0)
    assert len(rows) == 1
    rows = store.list_account_signal_plan_evaluations(limit=-100)
    assert len(rows) == 1

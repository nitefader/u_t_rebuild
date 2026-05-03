"""W2-A-2 (audit P0 #2 — pre-T-7 bundle, 2026-04-30): orchestrator-driven
persistence integration tests.

Verifies that RuntimeOrchestrator writes every AccountSignalPlanEvaluation
to the persisted ``account_signal_plan_evaluations`` table, not just the
in-memory PipelineResult.

Pre-W2-A:
- The orchestrator built evaluations in memory only.
- Operations reconstructed them from the order ledger only via
  ``_evaluation_from_order``.
- PARTICIPATE-without-order, REJECT, IGNORE, DEFER outcomes were invisible.

This integration test fails before the W2-A-2b wiring lands and passes
after, lock-in style.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import BrokerOrderStatus, FakeBrokerAdapter
from backend.app.composition import SignalSourceRegistry, StrategyArtifactKind, StrategyArtifactResolver
from backend.app.decision.signal_sources import V4ExpressionSignalSource
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    ExecutionStyleVersion,
    IntentType,
    OrderType,
    ProgramVersion,
    RiskProfileVersion,
    StrategyControlsVersion,
    StrategyVersion,
    TimeInForce,
    UniverseSnapshot,
    UniverseSymbol,
)
from backend.app.domain.execution_style import (
    BracketStopTargetPreset,
    ExecutionMode,
)
from backend.app.domain.risk_profile import PositionSizingMethod
from backend.app.domain.strategy import SignalRule
from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLegV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.features import IncrementalFeatureEngine, NormalizedBar, ResolvedDeploymentComponents
from backend.app.governor import GovernorPolicy, PortfolioGovernor, PortfolioSnapshot
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.pipeline import RuntimeOrchestrator
from backend.app.runtime import DeploymentContext, RuntimeState, RuntimeStatus


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
OTHER_ACCOUNT_ID = UUID("22222222-3333-4444-5555-666666666666")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _components(*, side: CandidateSide = CandidateSide.LONG) -> ResolvedDeploymentComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    condition = ConditionNode(
        left_feature="5m.close[0]",
        operator=ConditionOperator.GREATER_THAN,
        right_feature="5m.open[0]",
    )
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="W2-A persistence",
        entry_rules=[
            SignalRule(
                name="entry_rule",
                side=side,
                intent_type=IntentType.ENTRY,
                condition=condition,
            )
        ],
    )
    strategy_v4 = StrategyVersionV4(
        id=uuid4(),
        strategy_v4_id=uuid4(),
        version=1,
        name="W2-A persistence v4",
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(
                expression_text="5m.close > 5m.open",
                feature_requirements=("5m.close", "5m.open"),
            )
        ),
        stops=(StrategyStopV4(mode="simple", scope="all", simple_type="%", simple_value=5.0),),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="%",
                target_value=10.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        ),
        feature_requirements=("5m.close", "5m.open"),
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="5m Controls",
        timeframe="5m",
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Fixed Shares",
        sizing_method=PositionSizingMethod.FIXED_SHARES,
        fixed_shares=10,
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Bracket 5/10",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        execution_mode=ExecutionMode.POST_FILL_BRACKET,
        preset=BracketStopTargetPreset(stop_pct=5.0, target_pct=10.0),
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="W2-A Universe",
        symbols=[UniverseSymbol(symbol="SPY")],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="W2-A Program",
        version=1,
        strategy_version_id=strategy_id,
        strategy_controls_version_id=controls_id,
        risk_profile_version_id=risk_id,
        execution_style_version_id=execution_id,
        universe_snapshot_id=universe_id,
    )
    return ResolvedDeploymentComponents(
        program=program,
        strategy=strategy,
        strategy_version_v4=strategy_v4,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _deployment(components: ResolvedDeploymentComponents) -> DeploymentContext:
    return DeploymentContext(
        deployment_id=DEPLOYMENT_ID,
        strategy_version_id=components.strategy_version_v4.id,
        strategy_version=components.strategy_version_v4.version,
    )


def _bar(*, open_: float = 99, close: float = 100) -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000,
    )


def _strategy_artifact_resolver(components: ResolvedDeploymentComponents) -> StrategyArtifactResolver:
    registry = SignalSourceRegistry()
    registry.register(StrategyArtifactKind.EXPRESSION_V1, lambda _metadata: V4ExpressionSignalSource())

    def lookup(strategy_version_v4_id: UUID) -> StrategyVersionV4:
        sv4 = components.strategy_version_v4
        if sv4 is None or sv4.id != strategy_version_v4_id:
            raise KeyError(strategy_version_v4_id)
        return sv4

    return StrategyArtifactResolver(registry=registry, strategy_v4_lookup=lookup)


def _orchestrator_with_store(
    *,
    runtime_store: SQLiteRuntimeStore,
    components: ResolvedDeploymentComponents | None = None,
    governor: PortfolioGovernor | None = None,
    account_ids: tuple[UUID, ...] | None = None,
    portfolio_snapshot: PortfolioSnapshot | None = None,
) -> RuntimeOrchestrator:
    resolved = components or _components()
    runtime_store.save_deployment_runtime_state(
        RuntimeState(deployment_id=DEPLOYMENT_ID, status=RuntimeStatus.RECOVERED_READY)
    )
    return RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        account_ids=account_ids,
        deployment=_deployment(resolved),
        components=resolved,
        feature_engine=IncrementalFeatureEngine(),
        broker_adapter=FakeBrokerAdapter(
            [BrokerOrderStatus.FILLED, BrokerOrderStatus.ACCEPTED, BrokerOrderStatus.ACCEPTED]
            * 5  # generous for multi-account fanout
        ),
        governor=governor,
        runtime_store=runtime_store,
        portfolio_snapshot=portfolio_snapshot or PortfolioSnapshot(equity=100_000),
        strategy_artifact_resolver=_strategy_artifact_resolver(resolved),
    )


def test_entry_evaluation_is_persisted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Approved OPEN evaluation must land in the persisted store, not just memory."""
    store = SQLiteRuntimeStore(tmp_path / "evals.sqlite")
    pipeline = _orchestrator_with_store(runtime_store=store)

    result = pipeline.process_bar(_bar(open_=99, close=100))

    # In-memory result has the evaluation.
    assert len(result.account_evaluations) == 1
    in_memory = result.account_evaluations[0]
    assert in_memory.participation_decision == AccountParticipationDecision.PARTICIPATE

    # Persisted store has the same row.
    persisted = store.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)
    assert len(persisted) == 1
    assert persisted[0].evaluation_id == in_memory.evaluation_id
    assert persisted[0].participation_decision == AccountParticipationDecision.PARTICIPATE

    signal_plans = store.list_signal_plans(deployment_id=DEPLOYMENT_ID)
    assert len(signal_plans) == 1
    assert signal_plans[0].signal_plan_id == result.signal_plans[0].signal_plan_id


def test_governor_rejected_evaluation_is_persisted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Audit's headline gap: REJECT outcomes without orders must be visible.

    A blocked entry creates no order, so pre-W2-A Operations could not see it.
    Now the persisted row makes it Operations-visible.
    """
    store = SQLiteRuntimeStore(tmp_path / "evals.sqlite")
    # Tight gross exposure cap so the entry is rejected.
    pipeline = _orchestrator_with_store(
        runtime_store=store,
        governor=PortfolioGovernor(GovernorPolicy(max_gross_exposure_pct=0.5)),
    )

    result = pipeline.process_bar(_bar(open_=99, close=100))

    # No order created (Governor rejected).
    assert result.orders == ()
    # In-memory evaluation exists with REJECT.
    assert len(result.account_evaluations) == 1
    rejected = result.account_evaluations[0]
    assert rejected.participation_decision == AccountParticipationDecision.REJECT
    assert rejected.governor_decision is not None
    assert rejected.governor_decision.approved is False

    # Persisted row mirrors the in-memory rejection.
    persisted = store.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)
    assert len(persisted) == 1
    assert persisted[0].participation_decision == AccountParticipationDecision.REJECT
    assert persisted[0].governor_decision is not None
    assert persisted[0].governor_decision.approved is False


def test_equity_unavailable_rejection_is_persisted(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The new W2-A-1b fail-closed rule still produces a persisted REJECT row.

    This proves the W2-A-1 + W2-A-2 paths compose correctly: even when the
    Governor short-circuits on equity=None, the evaluation is recorded.
    """
    store = SQLiteRuntimeStore(tmp_path / "evals.sqlite")
    pipeline = _orchestrator_with_store(
        runtime_store=store,
        portfolio_snapshot=PortfolioSnapshot(),  # equity=None on purpose
    )

    result = pipeline.process_bar(_bar(open_=99, close=100))

    assert result.orders == ()
    persisted = store.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)
    assert len(persisted) == 1
    assert persisted[0].participation_decision == AccountParticipationDecision.REJECT
    # Governor decision carries the new rule_id.
    assert persisted[0].governor_decision is not None
    # The rejection_reasons tuple includes the new rule's reason.
    assert "portfolio_equity_unavailable" in persisted[0].rejection_reasons


def test_multi_account_fanout_persists_each_evaluation(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """One SignalPlan fanned to N accounts must yield N persisted rows."""
    store = SQLiteRuntimeStore(tmp_path / "evals.sqlite")
    pipeline = _orchestrator_with_store(
        runtime_store=store,
        account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID),
    )

    result = pipeline.process_bar(_bar(open_=99, close=100))

    assert len(result.account_evaluations) == 2
    persisted_a = store.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)
    persisted_b = store.list_account_signal_plan_evaluations(account_id=OTHER_ACCOUNT_ID)
    assert len(persisted_a) == 1
    assert len(persisted_b) == 1
    # Both Accounts evaluating the same SignalPlan are independently visible.
    plan_id = result.signal_plans[0].signal_plan_id
    by_plan = store.list_account_signal_plan_evaluations(signal_plan_id=plan_id)
    assert len(by_plan) == 2
    assert {row.account_id for row in by_plan} == {ACCOUNT_ID, OTHER_ACCOUNT_ID}


def test_evaluation_persists_across_orchestrator_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """The evaluation must survive process restart — same SQLite file,
    fresh orchestrator and fresh store, evaluation still readable."""
    store_a = SQLiteRuntimeStore(tmp_path / "evals.sqlite")
    pipeline_a = _orchestrator_with_store(runtime_store=store_a)
    pipeline_a.process_bar(_bar(open_=99, close=100))

    # Reopen the same DB in a fresh store handle.
    store_b = SQLiteRuntimeStore(tmp_path / "evals.sqlite")
    persisted = store_b.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)
    assert len(persisted) == 1
    assert persisted[0].participation_decision == AccountParticipationDecision.PARTICIPATE


def test_persist_failure_emits_event_and_keeps_in_memory_result(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """W2-A adversarial-critic fix #3: a persist-side raise (e.g.
    IntegrityError, disk full) must emit an EVALUATION_PERSIST_FAILED
    pipeline event and NOT re-raise. The in-memory PipelineResult must
    still carry the evaluation so the bar's outcome is consistent.
    """
    from backend.app.pipeline import PipelineEventType
    from backend.app.persistence import SQLiteRuntimeStore

    class FailingStore(SQLiteRuntimeStore):
        def save_account_signal_plan_evaluation(self, evaluation):  # type: ignore[no-untyped-def]
            raise RuntimeError("simulated SQLite IntegrityError")

    store = FailingStore(tmp_path / "evals.sqlite")
    pipeline = _orchestrator_with_store(runtime_store=store)

    result = pipeline.process_bar(_bar(open_=99, close=100))

    # In-memory bucket survives.
    assert len(result.account_evaluations) == 1
    assert result.account_evaluations[0].participation_decision == AccountParticipationDecision.PARTICIPATE
    # The structured event is emitted with full lineage.
    persist_failed = [
        event
        for event in result.events
        if event.event_type == PipelineEventType.EVALUATION_PERSIST_FAILED
    ]
    assert len(persist_failed) == 1
    assert persist_failed[0].details["account_id"] == str(ACCOUNT_ID)
    assert persist_failed[0].details["error_type"] == "RuntimeError"
    assert "simulated SQLite IntegrityError" in persist_failed[0].details["error"]


def test_signal_plan_persist_failure_emits_event_and_keeps_in_memory_result(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from backend.app.pipeline import PipelineEventType
    from backend.app.persistence import SQLiteRuntimeStore

    class FailingSignalPlanStore(SQLiteRuntimeStore):
        def save_signal_plan(self, signal_plan):  # type: ignore[no-untyped-def]
            raise RuntimeError("simulated SignalPlan persist failure")

    store = FailingSignalPlanStore(tmp_path / "evals.sqlite")
    pipeline = _orchestrator_with_store(runtime_store=store)

    result = pipeline.process_bar(_bar(open_=99, close=100))

    assert len(result.signal_plans) == 1
    persist_failed = [
        event
        for event in result.events
        if event.event_type == PipelineEventType.SIGNAL_PLAN_PERSIST_FAILED
    ]
    assert len(persist_failed) == 1
    assert persist_failed[0].details["deployment_id"] == str(DEPLOYMENT_ID)
    assert persist_failed[0].details["error_type"] == "RuntimeError"
    assert "simulated SignalPlan persist failure" in persist_failed[0].details["error"]


def test_persist_failure_in_one_account_does_not_block_other_accounts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Multi-account fanout: account #1's persist failure must NOT prevent
    account #2 from evaluating. Both end up in the in-memory result; only
    the failed account is missing from the durable store, with a structured
    EVALUATION_PERSIST_FAILED event identifying it.
    """
    from backend.app.pipeline import PipelineEventType
    from backend.app.persistence import SQLiteRuntimeStore

    class SelectiveFailingStore(SQLiteRuntimeStore):
        def save_account_signal_plan_evaluation(self, evaluation):  # type: ignore[no-untyped-def]
            if evaluation.account_id == ACCOUNT_ID:
                raise RuntimeError("simulated failure for ACCOUNT_ID only")
            return super().save_account_signal_plan_evaluation(evaluation)

    store = SelectiveFailingStore(tmp_path / "evals.sqlite")
    pipeline = _orchestrator_with_store(
        runtime_store=store,
        account_ids=(ACCOUNT_ID, OTHER_ACCOUNT_ID),
    )

    result = pipeline.process_bar(_bar(open_=99, close=100))

    # Both Accounts evaluated and in-memory bucket has both.
    assert len(result.account_evaluations) == 2
    eval_account_ids = {ev.account_id for ev in result.account_evaluations}
    assert eval_account_ids == {ACCOUNT_ID, OTHER_ACCOUNT_ID}

    # Persisted store has only OTHER_ACCOUNT_ID (the one that didn't fail).
    persisted_a = store.list_account_signal_plan_evaluations(account_id=ACCOUNT_ID)
    persisted_b = store.list_account_signal_plan_evaluations(account_id=OTHER_ACCOUNT_ID)
    assert len(persisted_a) == 0
    assert len(persisted_b) == 1

    # Exactly one EVALUATION_PERSIST_FAILED event, naming the failed account.
    persist_failed = [
        event
        for event in result.events
        if event.event_type == PipelineEventType.EVALUATION_PERSIST_FAILED
    ]
    assert len(persist_failed) == 1
    assert persist_failed[0].details["account_id"] == str(ACCOUNT_ID)

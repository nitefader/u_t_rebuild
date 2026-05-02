"""End-to-end Optimization spine integration test.

Asserts the unified spine is exercised: every candidate generates a real
BacktestRun-equivalent metrics dict, the winner is correctly scored, the
candidate landscape is complete, and the WF handoff payload is well-formed
(top-K candidates feeding the WF sweep grid).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.app.data_center.ingest_service import HistoricalBarIngestService
from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    IntentType,
    RiskPlan,
    RiskPlanConfig,
    RiskPlanSizingMethod,
    RiskPlanTier,
    RiskPlanVersion,
    SignalRule,
    StrategyVersion,
    StrategyControlsVersion,
    ExecutionStyleVersion,
    OrderType,
    TimeInForce,
)
from backend.app.domain.execution_style import BracketSpec
from backend.app.execution_plans.persistence import ExecutionPlanRepository
from backend.app.features import NormalizedBar
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.research.optimization import (
    OptimizationExecutionRequest,
    OptimizationExecutionService,
    OptimizationSweepConfig,
    OptimizationSweepParameter,
)
from backend.app.strategy_controls.persistence import StrategyControlsRepository


def _strategy_payload(strategy_id, version_id) -> StrategyVersion:
    return StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        version=1,
        name="Optimization reference strategy",
        entry_rules=[
            SignalRule(
                name="green_bar_entry",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="1d.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="1d.open[0]",
                ),
            )
        ],
    )


class _FakeRecord:
    def __init__(self, payload: StrategyVersion) -> None:
        self.payload = payload


class _FakeStrategyService:
    def __init__(self, payload: StrategyVersion) -> None:
        self._payload = payload

    def get_version(self, _strategy_version_id):
        return _FakeRecord(self._payload)


class _FakeBarsSource:
    def fetch(self, *, symbol, timeframe, start, end, adjustment_policy):
        bars: list[NormalizedBar] = []
        cursor = start
        price = 100.0
        while cursor <= end:
            open_p = price + 0.10
            close_p = open_p + 0.50
            bars.append(
                NormalizedBar(
                    symbol=symbol.upper(),
                    timeframe=timeframe,
                    timestamp=cursor,
                    open=open_p,
                    high=close_p + 0.30,
                    low=open_p - 0.20,
                    close=close_p,
                    volume=1_000_000.0,
                )
            )
            price = close_p
            cursor = cursor + timedelta(days=1)
        return tuple(bars), {"endpoint": "fake", "symbol": symbol}


def _save_risk_plan(store: SQLiteRuntimeStore):
    plan = RiskPlan(
        name="Optimization Base Risk Plan",
        risk_score=5,
        risk_tier=RiskPlanTier.BALANCED,
    )
    version = RiskPlanVersion(
        risk_plan_id=plan.risk_plan_id,
        version=1,
        config=RiskPlanConfig(
            sizing_method=RiskPlanSizingMethod.FIXED_SHARES,
            fixed_shares=10,
            max_open_positions=5,
        ),
    )
    store.save_risk_plan(plan)
    store.save_risk_plan_version(version)
    return version


def _save_components(store: SQLiteRuntimeStore) -> tuple:
    db_path = store._session_factory.path
    controls = StrategyControlsVersion(
        id=uuid4(),
        strategy_controls_id=uuid4(),
        version=1,
        name="Optimization 1d Controls",
        timeframe="1d",
    )
    execution = ExecutionStyleVersion(
        id=uuid4(),
        execution_style_id=uuid4(),
        version=1,
        name="Optimization Execution Plan",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        bracket=BracketSpec(enabled=False),
    )
    StrategyControlsRepository(db_path).save_version(controls)
    ExecutionPlanRepository(db_path).save_version(execution)
    return controls.id, execution.id


def test_optimization_runs_grid_and_emits_landscape_and_wf_handoff(tmp_path) -> None:
    strategy_id = uuid4()
    version_id = uuid4()
    payload = _strategy_payload(strategy_id, version_id)
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    fake = _FakeBarsSource()
    ingest = HistoricalBarIngestService(store=store, sources={"yahoo": fake, "alpaca": fake})
    service = OptimizationExecutionService(
        strategy_lookup=_FakeStrategyService(payload),
        ingest_service=ingest,
        store=store,
        risk_decision_sink=store,
    )
    risk_plan_version = _save_risk_plan(store)
    controls_version_id, execution_plan_version_id = _save_components(store)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 4, 1, tzinfo=timezone.utc)
    req = OptimizationExecutionRequest(
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        strategy_controls_version_id=controls_version_id,
        execution_plan_version_id=execution_plan_version_id,
        symbols=("SPY",),
        start=start,
        end=end,
        initial_capital=100_000,
        cost_model={"commission_per_trade": 0.0, "slippage_bps": 0.0},
        sweep=OptimizationSweepConfig(
            base_risk_plan_version_id=risk_plan_version.risk_plan_version_id,
            parameters=(
                OptimizationSweepParameter(field="fixed_shares", values=(5.0, 10.0, 20.0, 40.0)),
            ),
        ),
        method="grid",
        max_candidates=200,
        timeframe="1d",
        source="yahoo",
    )
    run = service.create_run(req)

    # Persisted shape carries every candidate
    assert run.candidate_count == 4
    metrics = run.best_metrics
    assert metrics["method"] == "grid"
    assert metrics["selection_criterion"] == "max_dd_bounded_sharpe"
    assert metrics["risk_plan_id"] == str(risk_plan_version.risk_plan_id)
    assert metrics["risk_plan_version_id"] == str(risk_plan_version.risk_plan_version_id)
    assert metrics["research_artifact"]["strategy_controls_version_id"] == str(controls_version_id)
    assert run.artifact_id is not None
    assert store.load_research_run_artifact_for_run(run.run_id).artifact_id == run.artifact_id
    assert metrics["needs_walk_forward_validation"] is True

    candidates = metrics["candidates"]
    assert len(candidates) == 4
    # The first candidate (sorted desc by score) is the recommended winner
    assert candidates[0]["recommended"] is True
    assert all("metrics" in c and "sharpe" in c["metrics"] for c in candidates)
    assert candidates[0]["risk_decision_card_ids"]
    sample_card = store.load_risk_decision_card(candidates[0]["risk_decision_card_ids"][0])
    assert sample_card.risk_plan_id == risk_plan_version.risk_plan_id
    assert sample_card.risk_plan_version_id == risk_plan_version.risk_plan_version_id

    # WF handoff payload references the top-K candidates' parameter values
    handoff = metrics["follow_up_walk_forward_request"]
    assert handoff["window_mode"] == "rolling"
    assert handoff["sweep"]["enabled"] is True
    handoff_values = handoff["sweep"]["parameters"][0]["values"]
    assert len(handoff_values) <= 3  # default top_k = 3
    # Every value used in the handoff must exist in the original sweep
    for v in handoff_values:
        assert v in (5.0, 10.0, 20.0, 40.0)

    # Best parameters are the winner's parameters
    assert run.best_parameters == candidates[0]["parameters"]


def test_optimization_grid_above_hard_limit_is_rejected(tmp_path) -> None:
    """6-parameter grid (5⁶ = 15,625 candidates) should fail fast in grid mode."""
    import pytest

    strategy_id = uuid4()
    version_id = uuid4()
    payload = _strategy_payload(strategy_id, version_id)
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    fake = _FakeBarsSource()
    ingest = HistoricalBarIngestService(store=store, sources={"yahoo": fake, "alpaca": fake})
    service = OptimizationExecutionService(
        strategy_lookup=_FakeStrategyService(payload),
        ingest_service=ingest,
    )
    risk_plan_version = _save_risk_plan(store)
    controls_version_id, execution_plan_version_id = _save_components(store)

    req = OptimizationExecutionRequest(
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        strategy_controls_version_id=controls_version_id,
        execution_plan_version_id=execution_plan_version_id,
        symbols=("SPY",),
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 4, 1, tzinfo=timezone.utc),
        initial_capital=100_000,
        cost_model={},
        sweep=OptimizationSweepConfig(
            base_risk_plan_version_id=risk_plan_version.risk_plan_version_id,
            parameters=tuple(
                OptimizationSweepParameter(field=f"f{i}", values=(1.0, 2.0, 3.0, 4.0, 5.0))
                for i in range(6)
            ),
        ),
        method="grid",
        max_candidates=None,
    )
    with pytest.raises(ValueError):
        service.create_run(req)

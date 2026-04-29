"""End-to-end Walk-Forward spine integration test.

Doctrine: same spine as Backtest. Each fold runs HistoricalReplayEngine twice
(IS + OOS); recommendation aggregates; output is a `WalkForwardRun` carrying
real OOS metrics + recommended_risk_plan + recommendation enum.

This test injects a fake StrategyVersion lookup and a fake bars source, runs
a small WF, and asserts that:
- folds were generated and run
- the recommendation enum is populated
- the candidate landscape contains the swept parameters
- per-fold metrics carry the 11 standard backtest metrics
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
)
from backend.app.features import NormalizedBar
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.research.walk_forward import (
    WalkForwardExecutionRequest,
    WalkForwardExecutionService,
)
from backend.app.research.walk_forward.service import (
    WalkForwardSweepConfig,
    WalkForwardSweepParameter,
)
from backend.app.research.walk_forward.window_planner import LengthSpec


def _strategy_payload(strategy_id, version_id) -> StrategyVersion:
    return StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        version=1,
        name="WF reference strategy",
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
        # Generate one daily bar per day across the requested window.
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
        name="WF Base Risk Plan",
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


def test_walk_forward_runs_folds_and_emits_recommendation(tmp_path) -> None:
    strategy_id = uuid4()
    version_id = uuid4()
    payload = _strategy_payload(strategy_id, version_id)
    store = SQLiteRuntimeStore(tmp_path / "runtime.db")
    fake_source = _FakeBarsSource()
    ingest = HistoricalBarIngestService(
        store=store, sources={"yahoo": fake_source, "alpaca": fake_source}
    )
    service = WalkForwardExecutionService(
        strategy_lookup=_FakeStrategyService(payload),
        ingest_service=ingest,
        store=store,
        risk_decision_sink=store,
    )
    risk_plan_version = _save_risk_plan(store)

    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 8, 1, tzinfo=timezone.utc)
    req = WalkForwardExecutionRequest(
        strategy_id=strategy_id,
        strategy_version_id=version_id,
        symbols=("SPY",),
        start=start,
        end=end,
        initial_capital=100_000,
        cost_model={"commission_per_trade": 0.0, "slippage_bps": 0.0},
        timeframe="1d",
        source="yahoo",
        window_mode="rolling",
        is_length=LengthSpec(unit="days", value=60),
        oos_length=LengthSpec(unit="days", value=30),
        step=LengthSpec(unit="days", value=30),
        max_folds=3,
        sweep=WalkForwardSweepConfig(
            enabled=True,
            base_risk_plan_version_id=risk_plan_version.risk_plan_version_id,
            parameters=(
                WalkForwardSweepParameter(field="fixed_shares", values=(5.0, 10.0, 20.0)),
            ),
        ),
    )
    run = service.create_run(req)

    # Persisted shape
    assert run.window_count >= 1
    assert run.metrics["risk_plan_id"] == str(risk_plan_version.risk_plan_id)
    assert run.metrics["risk_plan_version_id"] == str(risk_plan_version.risk_plan_version_id)
    assert run.metrics["recommended_risk_plan"]["candidate_risk_plan_version_id"] == str(
        risk_plan_version.risk_plan_version_id
    )
    assert run.metrics["risk_decision_card_ids"]
    sample_card = store.load_risk_decision_card(run.metrics["risk_decision_card_ids"][0])
    assert sample_card.risk_plan_id == risk_plan_version.risk_plan_id
    assert sample_card.risk_plan_version_id == risk_plan_version.risk_plan_version_id
    assert run.metrics["selection_criterion"] == "max_dd_bounded_sharpe"
    assert run.metrics["recommendation"] in {
        "ship_recommended",
        "needs_more_data",
        "do_not_ship",
    }

    # Per-fold metrics carry the 11 standard backtest metrics
    folds = run.metrics["folds"]
    assert len(folds) >= 1
    sample = folds[0]
    assert "is_metrics" in sample and "oos_metrics" in sample
    for key in (
        "cagr",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "hit_rate",
        "profit_factor",
        "expectancy",
        "exposure",
        "turnover",
        "time_in_market",
    ):
        assert key in sample["oos_metrics"]

    # Candidate landscape contains every swept parameter combination
    candidates = run.metrics["candidates"]
    assert len(candidates) == 3
    assert any(c.get("recommended") for c in candidates)

    # Recommended risk plan payload is present (may be null when fold count = 0)
    if folds:
        assert run.metrics["recommended_risk_plan"] is not None
        recommended = run.metrics["recommended_risk_plan"]
        assert "explanation" in recommended
        assert "parameters" in recommended

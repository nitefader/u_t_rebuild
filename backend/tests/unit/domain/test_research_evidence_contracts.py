from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from backend.app.domain import (
    BacktestRun,
    ChartLabPreviewEvidence,
    OptimizationRun,
    PromotionEvidenceBundle,
    SimulationRunEvidence,
    WalkForwardRun,
)


START = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
END = START + timedelta(days=30)


def test_chart_lab_preview_evidence_is_research_only() -> None:
    evidence = ChartLabPreviewEvidence(
        evidence_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        symbol="SPY",
        timeframe="5m",
        start=START,
        end=END,
        feature_snapshot_count=25,
        signal_marker_count=3,
    )

    assert evidence.symbol == "SPY"
    assert evidence.signal_marker_count == 3


@pytest.mark.parametrize(
    "model,payload",
    [
        (
            BacktestRun,
            {
                "run_id": uuid4(),
                "strategy_id": uuid4(),
                "strategy_version_id": uuid4(),
                "start": START,
                "end": END,
                "bar_count": 100,
                "signal_plan_count": 4,
                "simulated_trade_count": 2,
            },
        ),
        (
            SimulationRunEvidence,
            {
                "run_id": uuid4(),
                "strategy_id": uuid4(),
                "strategy_version_id": uuid4(),
                "scenario_name": "baseline",
                "start": START,
                "end": END,
                "signal_plan_count": 4,
                "simulated_order_count": 6,
                "simulated_fill_count": 6,
            },
        ),
        (
            OptimizationRun,
            {
                "run_id": uuid4(),
                "strategy_id": uuid4(),
                "strategy_version_id": uuid4(),
                "objective": "sharpe",
                "candidate_count": 12,
            },
        ),
        (
            WalkForwardRun,
            {
                "run_id": uuid4(),
                "strategy_id": uuid4(),
                "strategy_version_id": uuid4(),
                "window_count": 6,
                "passed_window_count": 5,
            },
        ),
    ],
)
def test_research_evidence_rejects_broker_truth_fields(model, payload) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="research evidence cannot contain trading truth fields"):
        model(**payload, client_order_id="broker-truth-is-forbidden")


def test_promotion_evidence_bundle_reports_readiness_without_trading_authority() -> None:
    bundle = PromotionEvidenceBundle(
        bundle_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        chart_lab_evidence_ids=(uuid4(),),
        backtest_run_ids=(uuid4(),),
        simulation_run_ids=(uuid4(),),
        optimization_run_ids=(uuid4(),),
        walk_forward_run_ids=(uuid4(),),
        readiness_score=100,
    )

    assert bundle.ready is True


def test_backtest_run_carries_operator_grade_results_without_broker_truth() -> None:
    run = BacktestRun(
        run_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        universe=("SPY",),
        start=START,
        end=END,
        initial_capital=100_000,
        cost_model={"settlement": "T+1", "slippage_bps": 2},
        status="completed",
        status_history=({"status": "queued"}, {"status": "running"}, {"status": "completed"}),
        bar_count=20,
        signal_plan_count=1,
        simulated_trade_count=1,
        metrics={
            "cagr": 0.1,
            "sharpe": 1.2,
            "sortino": 1.5,
            "calmar": 2.0,
            "max_drawdown": -0.05,
            "hit_rate": 1.0,
            "profit_factor": 3.0,
            "expectancy": 12.5,
            "exposure": 0.8,
            "turnover": 1.1,
            "time_in_market": 0.8,
        },
        results={
            "equity_curve": [{"step": 0, "equity": 100_000}],
            "trade_ledger": [{"trade_ref": "BT-SPY-001", "symbol": "SPY"}],
            "per_symbol_breakdown": [{"symbol": "SPY", "net_pnl": 100}],
            "drawdown_series": [{"step": 0, "drawdown": 0}],
        },
    )

    assert run.status == "completed"
    assert run.results["trade_ledger"][0]["trade_ref"] == "BT-SPY-001"


def test_walk_forward_passed_windows_cannot_exceed_total() -> None:
    with pytest.raises(ValueError, match="passed walk-forward windows"):
        WalkForwardRun(
            run_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            window_count=3,
            passed_window_count=4,
        )

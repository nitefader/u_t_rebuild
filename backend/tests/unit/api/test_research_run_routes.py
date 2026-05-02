from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import research_runs
from backend.app.domain import BacktestRun, OptimizationRun, SimulationRunEvidence, WalkForwardRun
from backend.app.domain import CandidateSide, ConditionNode, ConditionOperator, IntentType, SignalRule, StrategyVersion
from backend.app.domain import ExecutionStyleVersion, OrderType, StrategyControlsVersion, TimeInForce
from backend.app.domain import ResearchDataPolicy, ResearchRunKind, RiskPlanSizingMethod
from backend.app.domain.execution_style import BracketSpec
from backend.app.execution_plans.persistence import ExecutionPlanRepository
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.research.artifacts import build_research_run_artifact
from backend.app.research.components import load_research_components
from backend.app.strategy_controls.persistence import StrategyControlsRepository


def _store(tmp_path) -> SQLiteRuntimeStore:  # type: ignore[no-untyped-def]
    return SQLiteRuntimeStore(tmp_path / "runtime.db")


def _window() -> tuple[datetime, datetime]:
    return (
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
    )


def _http_client(store: SQLiteRuntimeStore) -> TestClient:
    app = FastAPI()
    app.include_router(research_runs.router)
    app.dependency_overrides[research_runs.get_research_store] = lambda: store
    return TestClient(app)


def _save_research_components(store: SQLiteRuntimeStore, *, timeframe: str = "1d") -> tuple[UUID, UUID]:
    db_path = store._session_factory.path
    controls = StrategyControlsVersion(
        id=uuid4(),
        strategy_controls_id=uuid4(),
        version=1,
        name=f"{timeframe} Research Controls",
        timeframe=timeframe,
    )
    execution = ExecutionStyleVersion(
        id=uuid4(),
        execution_style_id=uuid4(),
        version=1,
        name="Research Execution Plan",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        bracket=BracketSpec(enabled=True, take_profit_r_multiple=2, stop_loss_r_multiple=1),
    )
    StrategyControlsRepository(db_path).save_version(controls)
    ExecutionPlanRepository(db_path).save_version(execution)
    return controls.id, execution.id


def _green_bar_strategy(strategy_id: UUID, version_id: UUID, *, timeframe: str = "1d") -> StrategyVersion:
    return StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        version=1,
        name="Research reference strategy",
        entry_rules=[
            SignalRule(
                name="green_bar_entry",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature=f"{timeframe}.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature=f"{timeframe}.open[0]",
                ),
                stop_candidate_feature=f"{timeframe}.low[0]",
                target_candidate_feature=f"{timeframe}.high[0]",
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


def _save_fixed_risk_plan(store: SQLiteRuntimeStore) -> research_runs.RiskPlanVersion:
    risk_plan = research_runs.RiskPlan(
        name="Research Base Risk Plan",
        risk_score=5,
        risk_tier=research_runs.RiskPlanTier.BALANCED,
    )
    version = research_runs.RiskPlanVersion(
        risk_plan_id=risk_plan.risk_plan_id,
        version=1,
        config=research_runs.RiskPlanConfig(
            sizing_method=RiskPlanSizingMethod.FIXED_SHARES,
            fixed_shares=10,
        ),
    )
    store.save_risk_plan(risk_plan)
    store.save_risk_plan_version(version)
    return version


def _attach_research_artifact(
    store: SQLiteRuntimeStore,
    *,
    run_id: UUID,
    run_kind: ResearchRunKind,
    strategy_id: UUID,
    strategy_version_id: UUID,
    risk_plan_version_id: UUID,
    symbols: tuple[str, ...] = ("SPY",),
    timeframe: str = "1d",
) -> None:
    controls_version_id, execution_plan_version_id = _save_research_components(store, timeframe=timeframe)
    components = load_research_components(
        strategy_lookup=_FakeStrategyService(
            _green_bar_strategy(strategy_id, strategy_version_id, timeframe=timeframe)
        ),
        store=store,
        strategy_version_id=strategy_version_id,
        strategy_controls_version_id=controls_version_id,
        execution_plan_version_id=execution_plan_version_id,
        risk_plan_version_id=risk_plan_version_id,
        symbols=symbols,
        timeframe=timeframe,
        universe_name="Research artifact symbols",
        purpose="test",
    )
    start, end = _window()
    artifact = build_research_run_artifact(
        run_id=run_id,
        run_kind=run_kind,
        components=components,
        data_policy=ResearchDataPolicy(
            provider="yahoo",
            timeframe=timeframe,
            start=start,
            end=end,
        ),
    )
    store.save_research_run_artifact(artifact)


def test_backtest_rejects_client_authored_placeholder_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    strategy_id = uuid4()
    version_id = uuid4()
    start, end = _window()

    with pytest.raises(Exception, match="research spine"):
        research_runs.create_backtest_run(
            research_runs.BacktestRunRequest(
                strategy_id=strategy_id,
                strategy_version_id=version_id,
                start=start,
                end=end,
                bar_count=25,
                signal_plan_count=2,
                simulated_trade_count=1,
                metrics={"sharpe": 1.2},
            ),
            store=store,
        )


def test_sim_lab_legacy_session_routes_reject_client_authored_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    start, end = _window()

    with pytest.raises(Exception, match="research spine"):
        research_runs.create_sim_lab_session(
            research_runs.SimulationSessionRequest(
                strategy_id=uuid4(),
                strategy_version_id=uuid4(),
                scenario_name="Morning replay",
                start=start,
                end=end,
            ),
            store=store,
        )
    with pytest.raises(Exception, match="research spine"):
        research_runs.run_sim_lab_session(
            uuid4(),
            request=research_runs.SimulationRunRequest(
                signal_plan_count=3,
                simulated_order_count=2,
                simulated_fill_count=2,
                metrics={"net": 42},
            ),
            store=store,
        )


def test_research_sim_lab_batch_run_executes_fixed_window_replay(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    client = _http_client(store)
    strategy_id = uuid4()
    version_id = uuid4()
    controls_version_id, execution_plan_version_id = _save_research_components(store, timeframe="5m")
    risk_plan = research_runs.RiskPlan(
        name="Sim Lab Risk Plan",
        risk_score=5,
        risk_tier=research_runs.RiskPlanTier.BALANCED,
    )
    risk_plan_version = research_runs.RiskPlanVersion(
        risk_plan_id=risk_plan.risk_plan_id,
        version=1,
        config=research_runs.RiskPlanConfig(
                sizing_method=RiskPlanSizingMethod.FIXED_SHARES,
            fixed_shares=10,
        ),
    )
    store.save_risk_plan(risk_plan)
    store.save_risk_plan_version(risk_plan_version)
    start, end = _window()
    original_lookup = research_runs._get_strategy_lookup
    research_runs._get_strategy_lookup = lambda: _FakeStrategyService(
        _green_bar_strategy(strategy_id, version_id, timeframe="5m")
    )  # type: ignore[assignment]

    try:
        response = client.post(
            "/api/v1/research/sim_lab/runs",
            json={
                "strategy_id": str(strategy_id),
                "strategy_version_id": str(version_id),
                "strategy_controls_version_id": str(controls_version_id),
                "execution_plan_version_id": str(execution_plan_version_id),
                "risk_plan_version_id": str(risk_plan_version.risk_plan_version_id),
                "scenario_name": "Fixed window replay",
                "universe": ["SPY"],
                "timeframe": "5m",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "initial_cash": 100000,
                "bar_count": 6,
            },
        )
    finally:
        research_runs._get_strategy_lookup = original_lookup  # type: ignore[assignment]

    assert response.status_code == 200
    payload = response.json()
    run = payload["run"]
    assert run["strategy_id"] == str(strategy_id)
    assert run["strategy_version_id"] == str(version_id)
    assert run["scenario_name"] == "Fixed window replay"
    assert run["artifact_id"]
    assert run["deployment_snapshot_id"]
    assert run["signal_plan_count"] > 0
    assert run["simulated_order_count"] == len(payload["orders"])
    assert run["simulated_fill_count"] == len(payload["fills"])
    assert payload["events"]
    assert payload["equity_curve"]

    stored = client.get(f"/api/v1/sim-lab/sessions/{run['run_id']}")
    assert stored.status_code == 200
    assert stored.json()["run_id"] == run["run_id"]


def test_research_sim_lab_stream_emits_ordered_replay_artifacts(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    client = _http_client(store)
    strategy_id = uuid4()
    version_id = uuid4()
    controls_version_id, execution_plan_version_id = _save_research_components(store, timeframe="5m")
    risk_plan = research_runs.RiskPlan(
        name="Sim Lab Stream Risk Plan",
        risk_score=5,
        risk_tier=research_runs.RiskPlanTier.BALANCED,
    )
    risk_plan_version = research_runs.RiskPlanVersion(
        risk_plan_id=risk_plan.risk_plan_id,
        version=1,
        config=research_runs.RiskPlanConfig(
                sizing_method=RiskPlanSizingMethod.FIXED_SHARES,
            fixed_shares=10,
        ),
    )
    store.save_risk_plan(risk_plan)
    store.save_risk_plan_version(risk_plan_version)
    start, end = _window()
    original_lookup = research_runs._get_strategy_lookup
    original_runtime_path = research_runs.get_runtime_db_path
    research_runs._get_strategy_lookup = lambda: _FakeStrategyService(
        _green_bar_strategy(strategy_id, version_id, timeframe="5m")
    )  # type: ignore[assignment]
    research_runs.get_runtime_db_path = lambda: store._session_factory.path  # type: ignore[assignment]
    query = urlencode(
        {
            "strategy_id": str(strategy_id),
            "strategy_version_id": str(version_id),
            "strategy_controls_version_id": str(controls_version_id),
            "execution_plan_version_id": str(execution_plan_version_id),
            "risk_plan_version_id": str(risk_plan_version.risk_plan_version_id),
            "scenario_name": "Streaming replay",
            "universe": "SPY",
            "timeframe": "5m",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "initial_cash": "100000",
            "bar_count": "6",
        }
    )

    messages: list[dict[str, object]] = []
    try:
        with client.websocket_connect(f"/api/v1/research/sim_lab/stream?{query}") as websocket:
            while True:
                message = websocket.receive_json()
                messages.append(message)
                if message["type"] == "session_completed":
                    websocket.close()
                    break
    finally:
        research_runs._get_strategy_lookup = original_lookup  # type: ignore[assignment]
        research_runs.get_runtime_db_path = original_runtime_path  # type: ignore[assignment]

    message_types = [message["type"] for message in messages]
    assert messages[0]["type"] == "session_started"
    assert messages[-1]["type"] == "session_completed"
    assert "bar" in message_types
    assert "signal_plan" in message_types
    assert "virtual_fill" in message_types
    assert "position" in message_types
    assert "equity" in message_types
    assert [message["sequence"] for message in messages] == list(range(len(messages)))

    signal_message = next(message for message in messages if message["type"] == "signal_plan")
    signal_payload = signal_message["payload"]  # type: ignore[index]
    assert signal_payload["signal_plan"]["simulation_only"] is True  # type: ignore[index]
    assert signal_payload["signal_plan"]["strategy_id"] == str(strategy_id)  # type: ignore[index]

    fill_payload = next(message["payload"] for message in messages if message["type"] == "virtual_fill")  # type: ignore[misc]
    assert fill_payload["side"] == "buy"  # type: ignore[index]
    assert fill_payload["qty"] > 0  # type: ignore[index]
    assert fill_payload["price"] > 0  # type: ignore[index]

    position_payload = next(message["payload"] for message in messages if message["type"] == "position")  # type: ignore[misc]
    assert position_payload["symbol"] == "SPY"  # type: ignore[index]
    assert position_payload["qty"] > 0  # type: ignore[index]
    assert position_payload["avg_price"] > 0  # type: ignore[index]
    sessions = research_runs.list_sim_lab_sessions(store=store).sessions
    assert len(sessions) == 1
    evidence = sessions[0]
    assert evidence.artifact_id is not None
    assert evidence.deployment_snapshot_id is not None
    assert evidence.deployment_snapshot is not None
    assert evidence.deployment_snapshot.strategy_controls_version_id == controls_version_id
    assert evidence.deployment_snapshot.execution_plan_version_id == execution_plan_version_id
    assert evidence.deployment_snapshot.risk_plan_version_id == risk_plan_version.risk_plan_version_id
    assert evidence.metrics["research_artifact"]["run_kind"] == "sim_lab"
    artifact = store.load_research_run_artifact_for_run(evidence.run_id)
    assert artifact.run_kind == ResearchRunKind.SIM_LAB
    assert artifact.deployment_snapshot.snapshot_id == evidence.deployment_snapshot_id


def test_optimization_rejects_client_authored_placeholder_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)

    with pytest.raises(Exception, match="research spine"):
        research_runs.create_optimization_run(
            research_runs.OptimizationRunRequest(
                strategy_id=uuid4(),
                strategy_version_id=uuid4(),
                objective="maximize_sharpe",
                candidate_count=12,
                best_parameters={"rsi": 21},
                best_metrics={"sharpe": 1.4},
            ),
            store=store,
        )


def test_walk_forward_rejects_client_authored_placeholder_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)

    with pytest.raises(Exception, match="research spine"):
        research_runs.create_walk_forward_run(
            research_runs.WalkForwardRunRequest(
                strategy_id=uuid4(),
                strategy_version_id=uuid4(),
                window_count=6,
                passed_window_count=5,
                metrics={"oos_sharpe": 0.9},
            ),
            store=store,
        )


def test_research_routes_are_registered() -> None:
    routes = {
        (next(iter(route.methods)), route.path)
        for route in research_runs.router.routes
        if getattr(route, "methods", None)
    }

    assert ("GET", "/api/v1/backtests") in routes
    assert ("POST", "/api/v1/backtests") in routes
    assert ("GET", "/api/v1/research/backtests") in routes
    assert ("POST", "/api/v1/research/backtests") in routes
    assert ("GET", "/api/v1/research/backtests/{run_id}/results") in routes
    assert ("GET", "/api/v1/research/backtests/{run_id}/metrics") in routes
    assert ("GET", "/api/v1/sim-lab/sessions") in routes
    assert ("POST", "/api/v1/research/sim_lab/runs") in routes
    assert ("POST", "/api/v1/optimization/runs") in routes
    assert ("POST", "/api/v1/walk-forward/runs") in routes
    assert "/api/v1/research/sim_lab/stream" in {
        route.path for route in research_runs.router.routes if route.__class__.__name__.lower().endswith("websocketroute")
    }


def test_research_evidence_rejects_trading_truth_fields_in_domain_model() -> None:
    start, end = _window()

    with pytest.raises(Exception, match="research evidence cannot contain trading truth fields"):
        BacktestRun(
            run_id=uuid4(),
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            start=start,
            end=end,
            metrics={"account_id": str(uuid4())},
        )


def test_research_api_rejects_client_authored_trading_truth_placeholder(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    start, end = _window()

    with pytest.raises(Exception, match="research spine"):
        research_runs.create_backtest_run(
            research_runs.BacktestRunRequest(
                strategy_id=uuid4(),
                strategy_version_id=uuid4(),
                start=start,
                end=end,
                metrics={"account_id": str(uuid4())},
            ),
            store=store,
        )


def test_research_http_contract_supports_frontend_backtest_client(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = _http_client(_store(tmp_path))
    strategy_id = uuid4()
    version_id = uuid4()
    start, end = _window()

    created_response = client.post(
        "/api/v1/backtests",
        json={
            "strategy_id": str(strategy_id),
            "strategy_version_id": str(version_id),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "bar_count": 120,
            "signal_plan_count": 4,
            "simulated_trade_count": 2,
            "metrics": {"expectancy": 1.7},
        },
    )
    assert created_response.status_code == 422
    assert "research spine" in created_response.text


def test_research_http_contract_supports_frontend_sim_optimization_and_walk_forward_clients(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    client = _http_client(_store(tmp_path))
    strategy_id = uuid4()
    version_id = uuid4()
    start, end = _window()

    session_response = client.post(
        "/api/v1/sim-lab/sessions",
        json={
            "strategy_id": str(strategy_id),
            "strategy_version_id": str(version_id),
            "scenario_name": "Opening range replay",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "metrics": {"source": "frontend-contract"},
        },
    )
    assert session_response.status_code == 422
    assert "research spine" in session_response.text

    run_response = client.post(
        f"/api/v1/sim-lab/sessions/{uuid4()}/run",
        json={
            "signal_plan_count": 5,
            "simulated_order_count": 5,
            "simulated_fill_count": 4,
            "metrics": {"net_profit": 215.75},
        },
    )
    assert run_response.status_code == 422
    assert "research spine" in run_response.text

    optimization_response = client.post(
        "/api/v1/optimization/runs",
        json={
            "strategy_id": str(strategy_id),
            "strategy_version_id": str(version_id),
            "objective": "maximize_expectancy",
            "candidate_count": 9,
            "best_parameters": {"rsi_length": 21},
            "best_metrics": {"expectancy": 1.9},
        },
    )
    assert optimization_response.status_code == 422
    assert "research spine" in optimization_response.text

    walk_forward_response = client.post(
        "/api/v1/walk-forward/runs",
        json={
            "strategy_id": str(strategy_id),
            "strategy_version_id": str(version_id),
            "window_count": 6,
            "passed_window_count": 5,
            "metrics": {"oos_sharpe": 0.92},
        },
    )
    assert walk_forward_response.status_code == 422
    assert "research spine" in walk_forward_response.text


def test_research_backtest_create_status_results_metrics_and_cost_model(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Drives the unified spine end-to-end via the route.

    Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §13: no synthetic engine,
    no final quantity without RiskDecisionCard. The route now invokes
    HistoricalReplayEngine which calls SignalPlanBuilder + RiskResolver.
    """
    from datetime import timedelta
    from uuid import uuid4 as _uuid4

    from backend.app.api.routes import research_runs as rr
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

    store = _store(tmp_path)
    strategy_id = _uuid4()
    version_id = _uuid4()
    risk_plan = RiskPlan(
        name="Backtest Base Risk Plan",
        risk_score=5,
        risk_tier=RiskPlanTier.BALANCED,
    )
    risk_plan_version = RiskPlanVersion(
        risk_plan_id=risk_plan.risk_plan_id,
        version=1,
        config=RiskPlanConfig(
            sizing_method=RiskPlanSizingMethod.FIXED_SHARES,
            fixed_shares=10,
            max_open_positions=5,
        ),
    )
    store.save_risk_plan(risk_plan)
    store.save_risk_plan_version(risk_plan_version)
    risk_plan_version_id = risk_plan_version.risk_plan_version_id
    controls_version_id, execution_plan_version_id = _save_research_components(store, timeframe="1d")
    start, end = _window()
    end = start + timedelta(days=30)

    strategy_payload = StrategyVersion(
        id=version_id,
        strategy_id=strategy_id,
        version=1,
        name="Backtest reference strategy",
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
                stop_candidate_feature="1d.low[0]",
                target_candidate_feature="1d.high[0]",
            )
        ],
    )

    class _FakeRecord:
        payload = strategy_payload

    class _FakeStrategyService:
        def get_version(self, _strategy_version_id):
            return _FakeRecord()

    class _FakeBarsSource:
        def fetch(self, *, symbol, timeframe, start, end, adjustment_policy):
            bars: list[NormalizedBar] = []
            from datetime import timedelta as _td

            for index in range(20):
                ts = start + _td(days=index)
                price = 100.0 + index * 0.5
                bars.append(
                    NormalizedBar(
                        symbol=symbol.upper(),
                        timeframe=timeframe,
                        timestamp=ts,
                        open=price,
                        high=price + 1.5,
                        low=price - 0.5,
                        close=price + 0.75,
                        volume=1_000_000.0,
                    )
                )
            return tuple(bars), {"endpoint": "fake", "symbol": symbol}

    fake_strategy_service = _FakeStrategyService()
    fake_source = _FakeBarsSource()

    app = FastAPI()
    app.include_router(rr.router)
    app.dependency_overrides[rr.get_research_store] = lambda: store

    # Patch the bars source + strategy lookup factories on the route module
    original_lookup = rr._get_strategy_lookup
    rr._get_strategy_lookup = lambda: fake_strategy_service  # type: ignore[assignment]
    # Monkeypatch ingest sources by wrapping HistoricalBarIngestService
    import backend.app.api.routes.research_runs as research_runs_module

    real_yahoo = research_runs_module.YahooBarsSource
    real_alpaca = research_runs_module.AlpacaBarsSource
    research_runs_module.YahooBarsSource = lambda: fake_source  # type: ignore[assignment]
    research_runs_module.AlpacaBarsSource = lambda: fake_source  # type: ignore[assignment]

    try:
        client = TestClient(app)
        created_response = client.post(
            "/api/v1/research/backtests",
            json={
                "strategy_id": str(strategy_id),
                "strategy_version_id": str(version_id),
                "strategy_controls_version_id": str(controls_version_id),
                "execution_plan_version_id": str(execution_plan_version_id),
                "risk_plan_version_id": str(risk_plan_version_id),
                "symbols": ["SPY", "QQQ"],
                "timeframe": "1d",
                "start": start.isoformat(),
                "end": end.isoformat(),
                "initial_capital": 100_000,
                "cost_model": {
                    "commission_per_trade": 1,
                    "slippage_bps": 2,
                },
                "source": "yahoo",
            },
        )
        assert created_response.status_code == 200, created_response.text
        created = created_response.json()
        assert created["status"] == "completed"
        assert [item["status"] for item in created["status_history"]] == [
            "queued",
            "running",
            "completed",
        ]
        assert created["universe"] == ["SPY", "QQQ"]
        assert created["initial_capital"] == 100_000
        assert created["artifact_id"]
        assert created["deployment_snapshot_id"]
        assert created["deployment_snapshot"]["symbols"] == ["SPY", "QQQ"]
        assert created["deployment_snapshot"]["data_policy"]["provider"] == "yahoo"
        assert created["deployment_snapshot"]["strategy_controls_version_id"] == str(controls_version_id)
        assert created["deployment_snapshot"]["execution_plan_version_id"] == str(execution_plan_version_id)

        results_response = client.get(f"/api/v1/research/backtests/{created['run_id']}/results")
        assert results_response.status_code == 200
        results = results_response.json()
        assert results["equity_curve"]
        assert created["metrics"]["risk_plan_version_id"] == str(risk_plan_version_id)
        assert created["metrics"]["risk_decision_card_ids"]
        assert created["metrics"]["research_artifact"]["artifact_id"] == created["artifact_id"]
        assert (
            created["metrics"]["research_artifact"]["deployment_snapshot_id"]
            == created["deployment_snapshot_id"]
        )
        sample_card = store.load_risk_decision_card(UUID(created["metrics"]["risk_decision_card_ids"][0]))
        assert sample_card.risk_plan_id == risk_plan.risk_plan_id
        assert sample_card.risk_plan_version_id == risk_plan_version_id
        artifact = store.load_research_run_artifact_for_run(UUID(created["run_id"]))
        assert artifact.artifact_id == UUID(created["artifact_id"])
        assert artifact.deployment_snapshot.snapshot_id == UUID(created["deployment_snapshot_id"])
        assert artifact.deployment_snapshot.risk_plan_version_id == risk_plan_version_id
        assert artifact.deployment_snapshot.symbols == ("SPY", "QQQ")
        # Trade ledger may be empty if signals never fired in this stub data;
        # the spine assertion is that the route ran without error and persisted real evidence.

        metrics_response = client.get(f"/api/v1/research/backtests/{created['run_id']}/metrics")
        assert metrics_response.status_code == 200
        metrics_json = metrics_response.json()
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
            assert key in metrics_json["metrics"]
        assert metrics_json["cost_model"]["slippage_bps"] == 2.0
    finally:
        rr._get_strategy_lookup = original_lookup  # type: ignore[assignment]
        research_runs_module.YahooBarsSource = real_yahoo  # type: ignore[assignment]
        research_runs_module.AlpacaBarsSource = real_alpaca  # type: ignore[assignment]


def test_walk_forward_save_recommendation_as_draft_risk_plan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    base_risk_plan_version = _save_fixed_risk_plan(store)
    run = WalkForwardRun(
        run_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        window_count=1,
        passed_window_count=1,
        metrics={
            "recommended_risk_plan": {
                "parameters": {
                    "risk_per_trade_pct": 0.5,
                    "max_positions": 3,
                    "max_daily_loss_pct": 2,
                },
                "explanation": "Stable OOS profile.",
            }
        },
    )
    _attach_research_artifact(
        store,
        run_id=run.run_id,
        run_kind=ResearchRunKind.WALK_FORWARD,
        strategy_id=run.strategy_id,
        strategy_version_id=run.strategy_version_id,
        risk_plan_version_id=base_risk_plan_version.risk_plan_version_id,
    )
    store.save_research_evidence(run)
    client = _http_client(store)

    response = client.post(
        f"/api/v1/walk-forward/runs/{run.run_id}/save-risk-plan",
        json={"name": "WF Stable Draft", "created_by": "operator"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_run_id"] == str(run.run_id)
    assert body["risk_plan"]["name"] == "WF Stable Draft"
    assert body["risk_plan"]["status"] == "draft"
    assert body["risk_plan"]["source"] == "walk_forward_recommended"
    assert body["risk_plan_version"]["status"] == "draft"
    assert body["risk_plan_version"]["config"]["risk_per_trade_pct"] == 0.5
    assert body["risk_plan_version"]["config"]["max_open_positions"] == 3
    persisted = store.load_risk_plan(UUID(body["risk_plan"]["risk_plan_id"]))
    assert persisted.source_run_id == run.run_id
    assert persisted.evidence_lineage["source_run_id"] == str(run.run_id)
    assert persisted.evidence_lineage["source_evidence_type"] == "WalkForwardRun"
    assert persisted.evidence_lineage["parameters"]["max_positions"] == 3


def test_optimization_save_winner_as_draft_risk_plan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    base_risk_plan_version = _save_fixed_risk_plan(store)
    run = OptimizationRun(
        run_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        objective="max_dd_bounded_sharpe",
        candidate_count=1,
        best_parameters={
            "fixed_shares": 12,
            "max_symbol_exposure_pct": 20,
            "max_daily_loss_pct": 3,
        },
        best_metrics={"best_parameters": {"fixed_shares": 12, "max_symbol_exposure_pct": 20}},
    )
    _attach_research_artifact(
        store,
        run_id=run.run_id,
        run_kind=ResearchRunKind.OPTIMIZATION,
        strategy_id=run.strategy_id,
        strategy_version_id=run.strategy_version_id,
        risk_plan_version_id=base_risk_plan_version.risk_plan_version_id,
    )
    store.save_research_evidence(run)
    client = _http_client(store)

    response = client.post(
        f"/api/v1/optimization/runs/{run.run_id}/save-risk-plan",
        json={"name": "Optimization Winner Draft"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["source_run_id"] == str(run.run_id)
    assert body["risk_plan"]["status"] == "draft"
    assert body["risk_plan"]["source"] == "optimization_generated"
    assert body["risk_plan_version"]["config"]["sizing_method"] == "fixed_shares"
    assert body["risk_plan_version"]["config"]["fixed_shares"] == 12
    persisted = store.load_risk_plan(UUID(body["risk_plan"]["risk_plan_id"]))
    assert persisted.source_run_id == run.run_id
    assert persisted.evidence_lineage["source_run_id"] == str(run.run_id)
    assert persisted.evidence_lineage["source_evidence_type"] == "OptimizationRun"
    assert persisted.evidence_lineage["parameters"]["fixed_shares"] == 12

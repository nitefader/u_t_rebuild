from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4
from urllib.parse import urlencode

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.routes import research_runs
from backend.app.domain import BacktestRun, OptimizationRun, SimulationRunEvidence, WalkForwardRun
from backend.app.persistence import SQLiteRuntimeStore


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


def test_backtest_routes_create_list_get_and_cancel_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    strategy_id = uuid4()
    version_id = uuid4()
    start, end = _window()

    created = research_runs.create_backtest_run(
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

    listed = research_runs.list_backtests(store=store)
    loaded = research_runs.get_backtest_run(created.run_id, store=store)
    canceled = research_runs.cancel_backtest_run(
        created.run_id,
        request=research_runs.CancelRunRequest(reason="operator stopped run"),
        store=store,
    )

    assert isinstance(created, BacktestRun)
    assert listed.runs == (created,)
    assert loaded == created
    assert canceled.metrics["status"] == "canceled"
    assert canceled.metrics["status_reason"] == "operator stopped run"


def test_sim_lab_routes_create_run_results_and_archive_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    start, end = _window()
    session = research_runs.create_sim_lab_session(
        research_runs.SimulationSessionRequest(
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            scenario_name="Morning replay",
            start=start,
            end=end,
        ),
        store=store,
    )

    completed = research_runs.run_sim_lab_session(
        session.run_id,
        request=research_runs.SimulationRunRequest(
            signal_plan_count=3,
            simulated_order_count=2,
            simulated_fill_count=2,
            metrics={"net": 42},
        ),
        store=store,
    )
    results = research_runs.get_sim_lab_results(session.run_id, store=store)
    archived = research_runs.archive_sim_lab_session(session.run_id, store=store)

    assert isinstance(session, SimulationRunEvidence)
    assert completed.metrics["status"] == "completed"
    assert results == completed
    assert archived.metrics["status"] == "archived"


def test_research_sim_lab_batch_run_executes_fixed_window_replay(tmp_path) -> None:  # type: ignore[no-untyped-def]
    client = _http_client(_store(tmp_path))
    strategy_id = uuid4()
    version_id = uuid4()
    start, end = _window()

    response = client.post(
        "/api/v1/research/sim_lab/runs",
        json={
            "strategy_id": str(strategy_id),
            "strategy_version_id": str(version_id),
            "scenario_name": "Fixed window replay",
            "universe": ["SPY"],
            "timeframe": "5m",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "initial_cash": 100000,
            "bar_count": 6,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    run = payload["run"]
    assert run["strategy_id"] == str(strategy_id)
    assert run["strategy_version_id"] == str(version_id)
    assert run["scenario_name"] == "historical_replay"
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
    start, end = _window()
    query = urlencode(
        {
            "strategy_id": str(strategy_id),
            "strategy_version_id": str(version_id),
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
    with client.websocket_connect(f"/api/v1/research/sim_lab/stream?{query}") as websocket:
        while True:
            message = websocket.receive_json()
            messages.append(message)
            if message["type"] == "session_completed":
                websocket.close()
                break

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
    assert research_runs.list_sim_lab_sessions(store=store).sessions == ()


def test_optimization_routes_create_query_and_archive_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)

    created = research_runs.create_optimization_run(
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

    assert isinstance(created, OptimizationRun)
    assert research_runs.list_optimization_runs(store=store).runs == (created,)
    assert research_runs.get_optimization_run(created.run_id, store=store) == created
    archived = research_runs.archive_optimization_run(created.run_id, store=store)
    assert archived.best_metrics["status"] == "archived"
    assert research_runs.list_optimization_runs(store=store).runs == (archived,)


def test_walk_forward_routes_create_query_and_archive_evidence(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)

    created = research_runs.create_walk_forward_run(
        research_runs.WalkForwardRunRequest(
            strategy_id=uuid4(),
            strategy_version_id=uuid4(),
            window_count=6,
            passed_window_count=5,
            metrics={"oos_sharpe": 0.9},
        ),
        store=store,
    )

    assert isinstance(created, WalkForwardRun)
    assert research_runs.list_walk_forward_runs(store=store).runs == (created,)
    assert research_runs.get_walk_forward_run(created.run_id, store=store) == created
    archived = research_runs.archive_walk_forward_run(created.run_id, store=store)
    assert archived.metrics["status"] == "archived"
    assert research_runs.list_walk_forward_runs(store=store).runs == (archived,)


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


def test_research_evidence_rejects_trading_truth_fields_through_api_request(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
    start, end = _window()

    try:
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
    except Exception as exc:  # noqa: BLE001
        assert "research evidence cannot contain trading truth fields" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("trading truth field was accepted")


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
    assert created_response.status_code == 200
    created = created_response.json()

    assert UUID(created["run_id"])
    assert created["strategy_id"] == str(strategy_id)
    assert created["strategy_version_id"] == str(version_id)
    assert created["created_at"]
    assert created["metrics"]["status"] == "recorded"

    list_response = client.get("/api/v1/backtests")
    assert list_response.status_code == 200
    assert list_response.json()["runs"][0]["run_id"] == created["run_id"]

    cancel_response = client.post(
        f"/api/v1/backtests/{created['run_id']}/cancel",
        json={"reason": "operator canceled"},
    )
    assert cancel_response.status_code == 200
    canceled = cancel_response.json()
    assert canceled["metrics"]["status"] == "canceled"
    assert canceled["metrics"]["status_reason"] == "operator canceled"


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
    assert session_response.status_code == 200
    session = session_response.json()
    assert session["scenario_name"] == "Opening range replay"
    assert session["metrics"]["status"] == "created"

    run_response = client.post(
        f"/api/v1/sim-lab/sessions/{session['run_id']}/run",
        json={
            "signal_plan_count": 5,
            "simulated_order_count": 5,
            "simulated_fill_count": 4,
            "metrics": {"net_profit": 215.75},
        },
    )
    assert run_response.status_code == 200
    assert run_response.json()["metrics"]["status"] == "completed"

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
    assert optimization_response.status_code == 200
    optimization = optimization_response.json()
    assert optimization["candidate_count"] == 9
    assert optimization["best_parameters"]["rsi_length"] == 21

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
    assert walk_forward_response.status_code == 200
    walk_forward = walk_forward_response.json()
    assert walk_forward["window_count"] == 6
    assert walk_forward["passed_window_count"] == 5


def test_research_backtest_create_status_results_metrics_and_cost_model(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Drives the unified spine end-to-end via the route.

    Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §13: no synthetic engine,
    no final quantity without RiskDecisionCard. The route now invokes
    HistoricalReplayEngine which calls SignalPlanBuilder + RiskResolver.
    """
    from datetime import timedelta
    from uuid import uuid4 as _uuid4

    from backend.app.api.routes import research_runs as rr
    from backend.app.api.routes.strategies import get_strategy_service
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
    original_ingest_factory = HistoricalBarIngestService

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

        results_response = client.get(f"/api/v1/research/backtests/{created['run_id']}/results")
        assert results_response.status_code == 200
        results = results_response.json()
        assert results["equity_curve"]
        assert created["metrics"]["risk_plan_version_id"] == str(risk_plan_version_id)
        assert created["metrics"]["risk_decision_card_ids"]
        sample_card = store.load_risk_decision_card(UUID(created["metrics"]["risk_decision_card_ids"][0]))
        assert sample_card.risk_plan_id == risk_plan.risk_plan_id
        assert sample_card.risk_plan_version_id == risk_plan_version_id
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
    assert store.load_risk_plan(UUID(body["risk_plan"]["risk_plan_id"]))


def test_optimization_save_winner_as_draft_risk_plan(tmp_path) -> None:  # type: ignore[no-untyped-def]
    store = _store(tmp_path)
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

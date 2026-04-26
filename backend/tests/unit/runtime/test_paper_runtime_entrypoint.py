from __future__ import annotations

from pathlib import Path

import backend.app.brokers.alpaca as alpaca_module
import backend.app.market_data.alpaca as market_data_alpaca_module
from backend.app.runtime import paper_runtime_entrypoint


class _FakeTradingClient:
    """Stand-in for alpaca-py TradingClient that satisfies the adapter."""

    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self._args = args
        self._kwargs = kwargs

    def get_clock(self) -> dict:
        return {"is_open": False}


class _FakeStockDataStream:
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        pass

    def subscribe_bars(self, handler, *symbols) -> None:  # type: ignore[no-untyped-def]
        self._handler = handler
        self._symbols = symbols

    def run(self) -> None: ...

    def stop(self) -> None: ...


class _FakeTradingStream:
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        pass

    def subscribe_trade_updates(self, handler) -> None:  # type: ignore[no-untyped-def]
        self._handler = handler

    def run(self) -> None: ...

    def stop(self) -> None: ...


def test_run_paper_runtime_with_no_active_deployments_returns_idle_supervisor(
    tmp_path: Path, monkeypatch
) -> None:
    """When the runtime store has no paper deployments, the supervisor still
    starts cleanly — no streams open, no bar subscriptions registered.

    This is the smoke-test path for `python -m backend.app.runtime.paper_runtime_entrypoint`
    against a fresh database: the process should start without crashing and
    be safe to stop immediately.
    """
    monkeypatch.setattr(alpaca_module, "TradingClient", _FakeTradingClient)
    monkeypatch.setattr(market_data_alpaca_module, "StockDataStream", _FakeStockDataStream)
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

    sqlite_path = tmp_path / "empty.sqlite"
    supervisor = paper_runtime_entrypoint.run_paper_runtime(
        sqlite_path=sqlite_path,
        block_until_signal=False,
    )
    try:
        assert supervisor.is_running is True
        assert supervisor.active_deployment_ids == ()
        assert supervisor.subscribed_symbols == ()
    finally:
        supervisor.stop()
        assert supervisor.is_running is False


def test_run_paper_runtime_loads_explicit_deployments(tmp_path: Path, monkeypatch) -> None:
    """Caller-supplied deployments seed BrokerRuntimeOrchestrator and bring the supervisor up."""
    from datetime import datetime, timezone
    from uuid import UUID, uuid4

    from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
    from backend.app.brokers import BrokerSyncState
    from backend.app.domain import (
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
        TradingMode,
        UniverseSnapshot,
        UniverseSymbol,
    )
    from backend.app.domain.risk_profile import PositionSizingMethod
    from backend.app.domain.strategy import SignalRule
    from backend.app.features import ResolvedProgramComponents
    from backend.app.persistence import SQLiteRuntimeStore
    from backend.app.runtime import (
        BrokerRuntimeDeployment,
        DeploymentContext,
        RuntimeState,
        RuntimeStatus,
    )

    monkeypatch.setattr(alpaca_module, "TradingClient", _FakeTradingClient)
    monkeypatch.setattr(alpaca_module, "TradingStream", _FakeTradingStream)
    monkeypatch.setattr(market_data_alpaca_module, "StockDataStream", _FakeStockDataStream)
    monkeypatch.setenv("ALPACA_API_KEY", "test-key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test-secret")

    account_id = UUID("11111111-2222-3333-4444-555555555555")
    deployment_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    sqlite_path = tmp_path / "active.sqlite"
    store = SQLiteRuntimeStore(sqlite_path)
    store.save_broker_account(
        BrokerAccount(
            id=account_id,
            display_name="Paper",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref="test",
            validation_status=BrokerAccountValidationStatus.VALID,
        )
    )
    now = datetime.now(timezone.utc)
    store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=account_id,
            last_sync_at=now,
            last_successful_sync_at=now,
            is_stale=False,
        )
    )
    store.save_deployment_runtime_state(
        RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.RECOVERED_READY)
    )

    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    components = ResolvedProgramComponents(
        program=ProgramVersion(
            id=uuid4(),
            program_id=uuid4(),
            name="P",
            version=1,
            strategy_version_id=strategy_id,
            strategy_controls_version_id=controls_id,
            risk_profile_version_id=risk_id,
            execution_style_version_id=execution_id,
            universe_snapshot_id=universe_id,
        ),
        strategy=StrategyVersion(
            id=strategy_id,
            strategy_id=uuid4(),
            version=1,
            name="S",
            entry_rules=[
                SignalRule(
                    name="r",
                    side=CandidateSide.LONG,
                    intent_type=IntentType.ENTRY,
                    condition=ConditionNode(
                        left_feature="5m.close[0]",
                        operator=ConditionOperator.GREATER_THAN,
                        right_feature="5m.open[0]",
                    ),
                )
            ],
        ),
        strategy_controls=StrategyControlsVersion(
            id=controls_id,
            strategy_controls_id=uuid4(),
            version=1,
            name="c",
            timeframe="5m",
        ),
        risk_profile=RiskProfileVersion(
            id=risk_id,
            risk_profile_id=uuid4(),
            version=1,
            name="r",
            sizing_method=PositionSizingMethod.FIXED_SHARES,
            fixed_shares=10,
        ),
        execution_style=ExecutionStyleVersion(
            id=execution_id,
            execution_style_id=uuid4(),
            version=1,
            name="e",
            entry_order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        ),
        universe=UniverseSnapshot(
            id=universe_id,
            universe_id=uuid4(),
            version=1,
            name="u",
            symbols=[UniverseSymbol(symbol="SPY")],
        ),
    )
    deployment = BrokerRuntimeDeployment(
        deployment=DeploymentContext(deployment_id=deployment_id, program=components.program, mode=TradingMode.BROKER_PAPER.value),
        components=components,
        account_id=account_id,
    )

    supervisor = paper_runtime_entrypoint.run_paper_runtime(
        sqlite_path=sqlite_path,
        deployments=(deployment,),
        block_until_signal=False,
    )
    try:
        assert supervisor.is_running is True
        assert deployment_id in supervisor.active_deployment_ids
        assert supervisor.subscribed_symbols == ("SPY",)
    finally:
        supervisor.stop()

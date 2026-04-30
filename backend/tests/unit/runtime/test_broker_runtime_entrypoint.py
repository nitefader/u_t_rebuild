from __future__ import annotations

from pathlib import Path

import backend.app.brokers.alpaca as alpaca_module
import backend.app.market_data.alpaca as market_data_alpaca_module
from backend.app.runtime import account_trading_entrypoint


class _FakeTradingClient:
    def __init__(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        pass

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


def _fake_market_data_hub():
    """Stand up a hub backed by a fake market-data adapter so the broker
    entrypoint tests don't depend on market-data credentials. The next
    slice (inline AI / market-data credentials) replaces the in-process
    market-data adapter with one that resolves credentials from the
    operator-driven Market Data Service catalog.
    """
    from backend.app.market_data import AlpacaMarketDataAdapter, MarketDataStreamHub

    fake_stream = _FakeStockDataStream()
    adapter = AlpacaMarketDataAdapter(stream_client=fake_stream, load_env=False)
    return MarketDataStreamHub(market_data_adapter=adapter)


def _seed_account_and_credentials(tmp_path: Path, sqlite_path: Path, *, monkeypatch) -> None:
    """Pre-stage a registered broker account + persisted credentials.

    The entrypoint resolves credentials from the encrypted store (no env
    fallback). Tests must populate both the SQLite runtime store and the
    encrypted credential store at the runtime dir before run_account_trading.
    """
    import base64
    from datetime import datetime, timezone
    from uuid import UUID

    from backend.app.broker_accounts import BrokerCredentialStore
    from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
    from backend.app.brokers import BrokerSyncState
    from backend.app.domain import TradingMode
    from backend.app.persistence import SQLiteRuntimeStore

    monkeypatch.setenv("OPERATIONS_RUNTIME_DB_PATH", str(sqlite_path))
    monkeypatch.setenv("UTOS_CREDENTIAL_KEY", base64.b64encode(b"\x01" * 32).decode("ascii"))
    monkeypatch.setenv("UTOS_ENVIRONMENT", "dev")

    account_id = UUID("11111111-2222-3333-4444-555555555555")
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
    creds = BrokerCredentialStore(store_path=sqlite_path.parent / "broker_credentials.enc")
    creds.put(account_id, api_key="test-key", api_secret="test-secret")
    return account_id


def test_run_account_trading_with_no_active_deployments_returns_idle_supervisor(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(alpaca_module, "TradingClient", _FakeTradingClient)
    monkeypatch.setattr(market_data_alpaca_module, "StockDataStream", _FakeStockDataStream)

    sqlite_path = tmp_path / "empty.sqlite"
    _seed_account_and_credentials(tmp_path, sqlite_path, monkeypatch=monkeypatch)
    supervisor, hub = account_trading_entrypoint.run_account_trading(
        sqlite_path=sqlite_path,
        market_data_hub=_fake_market_data_hub(),
        block_until_signal=False,
    )
    try:
        assert supervisor.is_running is True
        assert supervisor.active_deployment_ids == ()
        assert hub.subscribed_symbols == ()
    finally:
        supervisor.stop()
        hub.stop()


def test_run_account_trading_loads_explicit_deployments(tmp_path: Path, monkeypatch) -> None:
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
    from backend.app.features import ResolvedDeploymentComponents
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

    deployment_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    sqlite_path = tmp_path / "active.sqlite"
    account_id = _seed_account_and_credentials(tmp_path, sqlite_path, monkeypatch=monkeypatch)
    store = SQLiteRuntimeStore(sqlite_path)
    store.save_deployment_runtime_state(
        RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.RECOVERED_READY)
    )

    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    components = ResolvedDeploymentComponents(
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
        deployment=DeploymentContext(
            deployment_id=deployment_id,
            strategy_version_id=components.strategy.id,
            strategy_version=components.strategy.version,
            mode=TradingMode.BROKER_PAPER.value,
        ),
        components=components,
        account_id=account_id,
    )

    supervisor, hub = account_trading_entrypoint.run_account_trading(
        sqlite_path=sqlite_path,
        deployments=(deployment,),
        market_data_hub=_fake_market_data_hub(),
        block_until_signal=False,
    )
    try:
        assert supervisor.is_running is True
        assert deployment_id in supervisor.active_deployment_ids
        assert hub.subscribed_symbols == ("SPY",)
    finally:
        supervisor.stop()
        hub.stop()


def test_parse_args_resolves_sqlite_like_get_runtime_db_path_when_omitted(tmp_path, monkeypatch) -> None:
    from backend.app.config.runtime_paths import (
        LEGACY_SQLITE_PATH_ENV,
        OPERATIONS_RUNTIME_DB_PATH_ENV,
        get_runtime_db_path,
    )

    configured = tmp_path / "configured.db"
    monkeypatch.setenv(OPERATIONS_RUNTIME_DB_PATH_ENV, str(configured))
    monkeypatch.delenv(LEGACY_SQLITE_PATH_ENV, raising=False)

    args = account_trading_entrypoint._parse_args([])
    resolved = args.sqlite_path if args.sqlite_path is not None else str(get_runtime_db_path())
    assert resolved == str(configured)


def test_parse_args_explicit_sqlite_path_overrides_env(tmp_path, monkeypatch) -> None:
    from backend.app.config.runtime_paths import OPERATIONS_RUNTIME_DB_PATH_ENV, get_runtime_db_path

    monkeypatch.setenv(OPERATIONS_RUNTIME_DB_PATH_ENV, str(tmp_path / "env.db"))
    explicit = tmp_path / "cli.db"
    args = account_trading_entrypoint._parse_args(["--sqlite-path", str(explicit)])
    resolved = args.sqlite_path if args.sqlite_path is not None else str(get_runtime_db_path())
    assert resolved == str(explicit)


# ---------------------------------------------------------------------------
# W2-A architecture-critic fix #1 + #2: build_portfolio_snapshot_factory
# (audit P0 #1, pre-T-7 bundle, 2026-04-30)
# ---------------------------------------------------------------------------


def test_build_portfolio_snapshot_factory_returns_equity_when_snapshot_present(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from datetime import datetime, timezone
    from uuid import uuid4

    from backend.app.brokers import BrokerAccountSnapshot
    from backend.app.governor import PortfolioSnapshot
    from backend.app.persistence import SQLiteRuntimeStore
    from backend.app.runtime.account_trading_entrypoint import build_portfolio_snapshot_factory

    store = SQLiteRuntimeStore(tmp_path / "factory.sqlite")
    account_id = uuid4()
    snapshot = BrokerAccountSnapshot(
        account_id=account_id,
        equity=125_432.10,
        cash=50_000.0,
        buying_power=125_432.10,
        last_equity=125_000.0,
        last_synced_at=datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc),
    )
    store.save_broker_account_snapshot(snapshot)

    factory = build_portfolio_snapshot_factory(store)
    result = factory(account_id)

    assert isinstance(result, PortfolioSnapshot)
    assert result.equity == 125_432.10


def test_build_portfolio_snapshot_factory_returns_equity_none_when_no_snapshot(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from uuid import uuid4

    from backend.app.governor import PortfolioSnapshot
    from backend.app.persistence import SQLiteRuntimeStore
    from backend.app.runtime.account_trading_entrypoint import build_portfolio_snapshot_factory

    store = SQLiteRuntimeStore(tmp_path / "factory.sqlite")
    factory = build_portfolio_snapshot_factory(store)

    result = factory(uuid4())

    assert isinstance(result, PortfolioSnapshot)
    assert result.equity is None  # fail-closed via portfolio_equity_unavailable


def test_build_portfolio_snapshot_factory_maps_zero_equity_to_none(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """W2-A adversarial-critic fix #1: BrokerAccountSnapshot.equity is ``ge=0``
    but PortfolioSnapshot.equity is ``gt=0``. A stale-and-flat poll, blocked
    account, post-liquidation account, or fresh-unfunded account can carry
    equity=0 and would (a) crash PortfolioSnapshot construction, (b) silently
    bypass percentage gates via _pct(value, 0)=0. Factory must map to None.
    """
    from datetime import datetime, timezone
    from uuid import uuid4

    from backend.app.brokers import BrokerAccountSnapshot
    from backend.app.governor import PortfolioSnapshot
    from backend.app.persistence import SQLiteRuntimeStore
    from backend.app.runtime.account_trading_entrypoint import build_portfolio_snapshot_factory

    store = SQLiteRuntimeStore(tmp_path / "factory.sqlite")
    account_id = uuid4()
    snapshot = BrokerAccountSnapshot(
        account_id=account_id,
        equity=0.0,
        cash=0.0,
        buying_power=0.0,
        last_equity=None,
        last_synced_at=datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc),
    )
    store.save_broker_account_snapshot(snapshot)

    factory = build_portfolio_snapshot_factory(store)
    result = factory(account_id)

    assert isinstance(result, PortfolioSnapshot)
    assert result.equity is None


def test_factory_is_called_per_invocation_not_cached(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """W2-A architecture-critic fix #2: snapshot resolution must be per-call,
    not cached at construction. Equity changes mid-loop must be visible to
    subsequent Governor evaluations."""
    from datetime import datetime, timezone
    from uuid import uuid4

    from backend.app.brokers import BrokerAccountSnapshot
    from backend.app.persistence import SQLiteRuntimeStore
    from backend.app.runtime.account_trading_entrypoint import build_portfolio_snapshot_factory

    store = SQLiteRuntimeStore(tmp_path / "factory.sqlite")
    account_id = uuid4()
    initial = BrokerAccountSnapshot(
        account_id=account_id,
        equity=100_000.0,
        cash=50_000.0,
        buying_power=100_000.0,
        last_synced_at=datetime(2026, 4, 30, 14, 0, tzinfo=timezone.utc),
    )
    store.save_broker_account_snapshot(initial)

    factory = build_portfolio_snapshot_factory(store)
    first = factory(account_id)
    assert first.equity == 100_000.0

    # Mutate the broker snapshot — the factory's next call must see the new value.
    updated = BrokerAccountSnapshot(
        account_id=account_id,
        equity=50_000.0,
        cash=25_000.0,
        buying_power=50_000.0,
        last_synced_at=datetime(2026, 4, 30, 14, 5, tzinfo=timezone.utc),
    )
    store.save_broker_account_snapshot(updated)

    second = factory(account_id)
    assert second.equity == 50_000.0

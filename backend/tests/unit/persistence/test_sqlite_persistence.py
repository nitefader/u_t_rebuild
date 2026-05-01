from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.brokers import BrokerOrderMapping
from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerFillUpdateEvent,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSync,
    BrokerSyncService,
)
from backend.app.broker_accounts.models import (
    AccountRestrictions,
    AccountRiskConfig,
    BrokerAccount,
    BrokerAccountValidationStatus,
)
from backend.app.control_plane import ControlPlane
from backend.app.domain import (
    BacktestRun,
    CandidateSide,
    ChartLabPreviewEvidence,
    OrderType,
    RiskPlan,
    RiskPlanConfig,
    RiskPlanSizingMethod,
    RiskPlanStatus,
    RiskPlanTier,
    RiskPlanVersion,
    RiskPlanVersionStatus,
    TimeInForce,
    TradingMode,
)
from backend.app.governor import GovernorPolicy
from backend.app.governor import PortfolioGovernor
from backend.app.orders import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManager, OrderOrigin
from backend.app.persistence import (
    SQLiteBrokerOrderMappingStore,
    SQLiteDeploymentStateStore,
    SQLiteGovernorStateStore,
    SQLiteOrderLedger,
    SQLiteRuntimeStore,
    SQLiteTradeLedger,
)
from backend.app.runtime import RuntimeState, RuntimeStatus
from backend.tests.fixtures.modern_order import make_signal_plan_order
from backend.app.simulation import SimulatedOrderIntent, SimulatedTrade


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def test_order_persists_across_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    ledger = SQLiteOrderLedger(db_path)
    manager = OrderManager(ledger=ledger)
    order = make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)
    manager.update_status(order_id=order.order_id, status=InternalOrderStatus.ACCEPTED, reason="broker_accepted")

    restarted_ledger = SQLiteOrderLedger(db_path)
    persisted = restarted_ledger.get(order.order_id)

    assert persisted.order_id == order.order_id
    assert persisted.status == InternalOrderStatus.ACCEPTED
    assert persisted.reason == "broker_accepted"
    assert restarted_ledger.by_account(ACCOUNT_ID)[0].client_order_id == order.client_order_id


def test_order_load_ignores_stale_payload_extras(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    ledger = SQLiteOrderLedger(db_path)
    manager = OrderManager(ledger=ledger)
    order = make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)

    with sqlite3.connect(db_path) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT payload FROM internal_orders WHERE order_id = ?",
                (str(order.order_id),),
            ).fetchone()[0]
        )
        payload["program_id"] = None
        connection.execute(
            "UPDATE internal_orders SET payload = ? WHERE order_id = ?",
            (json.dumps(payload), str(order.order_id)),
        )

    restarted_ledger = SQLiteOrderLedger(db_path)
    loaded = restarted_ledger.get(order.order_id)

    assert loaded.order_id == order.order_id
    assert loaded.origin == OrderOrigin.SIGNAL_PLAN


def test_signal_plan_order_lineage_persists_and_indexes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    now = datetime.now(timezone.utc)
    signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    order = InternalOrder(
        order_id=uuid4(),
        client_order_id="signal-plan-order",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        signal_plan_id=signal_plan_id,
        opening_signal_plan_id=signal_plan_id,
        current_signal_plan_id=signal_plan_id,
        position_lineage_id=position_lineage_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        leg_label="T1",
        lifecycle_intent=InternalOrderIntent.TARGET.value,
        symbol="SPY",
        side=CandidateSide.LONG,
        quantity=1,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.TARGET,
        status=InternalOrderStatus.CREATED,
        created_at=now,
        updated_at=now,
    )

    store = SQLiteRuntimeStore(db_path)
    store.save_order(order)
    restarted = SQLiteRuntimeStore(db_path)

    assert restarted.load_order(order.order_id).signal_plan_id == signal_plan_id
    assert restarted.list_orders_by_signal_plan(signal_plan_id) == (order,)
    assert restarted.list_orders_by_position_lineage(position_lineage_id) == (order,)


def test_fresh_internal_orders_table_has_signal_plan_lineage_indexes(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(internal_orders)").fetchall()}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(internal_orders)").fetchall()}

    assert "signal_plan_id" in columns
    assert "position_lineage_id" in columns
    assert "program_id" not in columns
    assert "ix_internal_orders_signal_plan_id" in indexes
    assert "ix_internal_orders_program_id" not in indexes
    assert store.list_orders() == ()


def test_risk_plan_and_versions_persist_with_indexes(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    risk_plan = RiskPlan(
        name="Balanced Momentum Risk",
        status=RiskPlanStatus.DRAFT,
        risk_score=5,
        risk_tier=RiskPlanTier.BALANCED,
    )
    version = RiskPlanVersion(
        risk_plan_id=risk_plan.risk_plan_id,
        version=1,
        status=RiskPlanVersionStatus.DRAFT,
        config=RiskPlanConfig(
            sizing_method=RiskPlanSizingMethod.RISK_PERCENT,
            risk_per_trade_pct=1,
            max_open_positions=5,
        ),
    )

    store.save_risk_plan(risk_plan)
    store.save_risk_plan_version(version)
    restarted = SQLiteRuntimeStore(db_path)

    assert restarted.load_risk_plan(risk_plan.risk_plan_id) == risk_plan
    assert restarted.load_risk_plan_version(version.risk_plan_version_id) == version
    assert restarted.list_risk_plans(status="draft", risk_tier="balanced") == (risk_plan,)
    assert restarted.list_risk_plan_versions(risk_plan.risk_plan_id, status="draft") == (version,)

    with sqlite3.connect(db_path) as connection:
        plan_indexes = {row[1] for row in connection.execute("PRAGMA index_list(risk_plans)").fetchall()}
        version_indexes = {row[1] for row in connection.execute("PRAGMA index_list(risk_plan_versions)").fetchall()}

    assert "ix_risk_plans_status" in plan_indexes
    assert "ix_risk_plans_tier" in plan_indexes
    assert "ix_risk_plans_source" in plan_indexes
    assert "ix_risk_plans_account_id" in plan_indexes
    assert "ix_risk_plan_versions_status" in version_indexes


def test_broker_account_default_risk_plan_mapping_persists(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    risk_plan_id = uuid4()
    risk_plan_version_id = uuid4()
    account = BrokerAccount(
        id=ACCOUNT_ID,
        display_name="Alpaca Paper Account 1",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:acct:fingerprint",
        validation_status=BrokerAccountValidationStatus.VALID,
        default_risk_plan_id=risk_plan_id,
        default_risk_plan_version_id=risk_plan_version_id,
    )

    store.save_broker_account(account)
    restarted = SQLiteRuntimeStore(db_path)
    persisted = restarted.load_broker_account(ACCOUNT_ID)

    assert persisted.default_risk_plan_id == risk_plan_id
    assert persisted.default_risk_plan_version_id == risk_plan_version_id

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            """
            SELECT default_risk_plan_id, default_risk_plan_version_id
            FROM broker_accounts
            WHERE account_id = ?
            """,
            (str(ACCOUNT_ID),),
        ).fetchone()

    assert row == (str(risk_plan_id), str(risk_plan_version_id))


def test_existing_broker_accounts_table_migrates_default_risk_plan_columns(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE broker_accounts (
                account_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                mode TEXT NOT NULL,
                external_account_id TEXT,
                validation_status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL
            );
            """
        )

    SQLiteRuntimeStore(db_path)

    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(broker_accounts)").fetchall()}
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(broker_accounts)").fetchall()}

    assert "default_risk_plan_id" in columns
    assert "default_risk_plan_version_id" in columns
    assert "ix_broker_accounts_default_risk_plan" in indexes


def test_account_risk_config_and_restrictions_persist(tmp_path) -> None:
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    config = AccountRiskConfig(
        account_id=ACCOUNT_ID,
        sizing_method="fixed_shares",
        fixed_shares=10,
        risk_per_trade_pct=None,
        max_open_positions=3,
    )
    restrictions = AccountRestrictions(
        account_id=ACCOUNT_ID,
        symbol_blocklist=("TSLA", "GME"),
        long_only=True,
        notes="operator blocklist",
    )

    store.save_account_risk_config(config)
    store.save_account_restrictions(restrictions)
    restarted = SQLiteRuntimeStore(db_path)

    assert restarted.load_account_risk_config(ACCOUNT_ID) == config
    assert restarted.load_account_restrictions(ACCOUNT_ID) == restrictions

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert "account_risk_configs" in tables
    assert "account_restrictions" in tables


def test_trade_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    trade = SimulatedTrade(
        id="TRD-1",
        symbol="SPY",
        side="long",
        qty=10,
        entry_price=100,
        exit_price=101,
        entry_order_id="ORD-1",
        exit_order_id="ORD-2",
        opened_at=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        closed_at=datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
        realized_pnl=10,
        exit_reason=SimulatedOrderIntent.TAKE_PROFIT,
    )

    SQLiteTradeLedger(db_path).add(trade)
    persisted = SQLiteTradeLedger(db_path).get("TRD-1")

    assert persisted == trade
    assert SQLiteTradeLedger(db_path).all() == (trade,)


def test_fill_persists_across_restart_by_deployment(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    fill = BrokerFillUpdateEvent(
        account_id=ACCOUNT_ID,
        client_order_id="utos-aaaaaaaa-open-12345678",
        symbol="SPY",
        qty=5,
        price=101,
        side="buy",
        broker_order_id="alpaca-123",
        broker_execution_id="fill-1",
        event_at=datetime(2026, 1, 2, 14, 31, tzinfo=timezone.utc),
    )

    SQLiteRuntimeStore(db_path).save_fill(fill, deployment_id=DEPLOYMENT_ID)
    persisted = SQLiteRuntimeStore(db_path).load_trades_by_deployment(DEPLOYMENT_ID)

    assert persisted == (fill,)


def test_broker_mapping_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    mapping = BrokerOrderMapping(
        order_id=uuid4(),
        client_order_id="utos-abc",
        broker_order_id="alpaca-123",
        provider="alpaca",
        account_id=ACCOUNT_ID,
    )

    SQLiteBrokerOrderMappingStore(db_path).save(mapping)
    persisted = SQLiteBrokerOrderMappingStore(db_path).get_by_order_id(mapping.order_id)

    assert persisted == mapping
    assert SQLiteBrokerOrderMappingStore(db_path).get_by_broker_order_id("alpaca-123", provider="alpaca") == mapping


def test_broker_sync_persists_mapping_snapshot_and_freshness(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    manager = OrderManager(ledger=SQLiteOrderLedger(db_path))
    order = make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)
    sync = BrokerSync(ledger=manager.ledger, runtime_store=store, provider="alpaca")

    sync.apply_result(
        BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.ACCEPTED,
            broker_order_id="alpaca-accepted-1",
            received_at=datetime(2026, 1, 2, 14, 31, tzinfo=timezone.utc),
        )
    )
    snapshot = BrokerAccountSnapshot(account_id=ACCOUNT_ID, buying_power=50_000, cash=25_000, equity=75_000)
    service = BrokerSyncService(
        adapter=object(),
        broker_sync=sync,
        order_ledger=manager.ledger,
        runtime_store=store,
        max_stale_seconds=1,
    )
    service.handle_account_update(snapshot)

    restarted = SQLiteRuntimeStore(db_path)
    persisted_mapping = restarted.lookup_broker_mapping_by_broker_order_id("alpaca-accepted-1", provider="alpaca")
    persisted_snapshot = restarted.load_broker_account_snapshot(ACCOUNT_ID)
    persisted_freshness = restarted.load_broker_sync_freshness(ACCOUNT_ID)

    assert persisted_mapping.order_id == order.order_id
    assert persisted_snapshot.equity == 75_000
    assert persisted_freshness.is_stale is False


def test_stale_broker_sync_remains_stale_after_restart(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    manager = OrderManager(ledger=SQLiteOrderLedger(db_path))
    service = BrokerSyncService(
        adapter=object(),
        broker_sync=BrokerSync(ledger=manager.ledger),
        order_ledger=manager.ledger,
        runtime_store=store,
    )

    stale = service.current_sync_state(ACCOUNT_ID)
    persisted = SQLiteRuntimeStore(db_path).load_broker_sync_freshness(ACCOUNT_ID)

    assert stale.is_stale is True
    assert persisted.is_stale is True
    assert persisted.stale_reason == "broker_truth_never_synced"


def test_governor_state_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    policy = GovernorPolicy(
        global_kill_active=True,
        paused_account_ids=frozenset({ACCOUNT_ID}),
        paused_deployment_ids=frozenset({DEPLOYMENT_ID}),
        max_open_positions=3,
    )

    SQLiteGovernorStateStore(db_path).save_policy("portfolio-governor", policy)
    persisted = SQLiteGovernorStateStore(db_path).load_policy("portfolio-governor")

    assert persisted == policy


def test_portfolio_governor_loads_persisted_state(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    store = SQLiteRuntimeStore(db_path)
    policy = GovernorPolicy(global_kill_active=True, paused_account_ids=frozenset({ACCOUNT_ID}))

    PortfolioGovernor(policy, state_store=store).save_state()
    restarted = PortfolioGovernor(state_store=SQLiteRuntimeStore(db_path))

    assert restarted.policy == policy


def test_deployment_runtime_state_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    state = RuntimeState(
        deployment_id=DEPLOYMENT_ID,
        status=RuntimeStatus.RUNNING,
        processed_bar_count=5,
        candidate_intent_count=2,
        signal_plan_count=1,
        last_bar_timestamp_by_symbol_timeframe={
            "SPY:1m": datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
        },
        last_signal_timestamp=datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
        last_signal_plan_timestamp=datetime(2026, 1, 2, 14, 35, tzinfo=timezone.utc),
    )

    SQLiteDeploymentStateStore(db_path).save_runtime_state(state)
    persisted = SQLiteDeploymentStateStore(db_path).load_runtime_state(DEPLOYMENT_ID)

    assert persisted == state


def test_research_evidence_persists_and_queries_by_strategy(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    strategy_id = uuid4()
    strategy_version_id = uuid4()
    chart_evidence = ChartLabPreviewEvidence(
        evidence_id=uuid4(),
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        symbol="SPY",
        timeframe="5m",
        start=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        end=datetime(2026, 1, 2, 15, 30, tzinfo=timezone.utc),
        feature_snapshot_count=10,
        signal_marker_count=2,
    )
    backtest = BacktestRun(
        run_id=uuid4(),
        strategy_id=strategy_id,
        strategy_version_id=strategy_version_id,
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 2, 1, tzinfo=timezone.utc),
        bar_count=100,
        signal_plan_count=5,
        simulated_trade_count=3,
    )

    store = SQLiteRuntimeStore(db_path)
    store.save_research_evidence(chart_evidence)
    store.save_research_evidence(backtest)
    restarted = SQLiteRuntimeStore(db_path)

    assert restarted.load_research_evidence(chart_evidence.evidence_id) == chart_evidence
    assert restarted.list_research_evidence(strategy_id=strategy_id) == (chart_evidence, backtest)
    assert restarted.list_research_evidence(evidence_type="backtest_run") == (backtest,)


def test_broker_positions_can_be_queried_by_deployment_lineage(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    other_deployment_id = uuid4()
    strategy_id = uuid4()
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    matching = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=10,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=1_000,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=strategy_id,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        status="open",
    )
    other = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="QQQ",
        qty=5,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=500,
        deployment_id=other_deployment_id,
        strategy_id=strategy_id,
        opening_signal_plan_id=uuid4(),
        position_lineage_id=uuid4(),
        status="open",
    )

    store = SQLiteRuntimeStore(db_path)
    store.save_broker_position_snapshot(matching)
    store.save_broker_position_snapshot(other)
    restarted = SQLiteRuntimeStore(db_path)

    assert restarted.list_broker_position_snapshots_by_deployment(DEPLOYMENT_ID) == (matching,)
    assert restarted.list_broker_position_snapshots_by_deployment(other_deployment_id) == (other,)
    assert restarted.list_broker_position_snapshots_by_deployment(uuid4()) == ()


def test_control_plane_state_persists(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    control_plane = ControlPlane(state_store=SQLiteRuntimeStore(db_path))

    control_plane.activate_global_kill()
    control_plane.pause_account(ACCOUNT_ID)
    control_plane.pause_deployment(DEPLOYMENT_ID)
    restarted = ControlPlane(state_store=SQLiteRuntimeStore(db_path))

    assert restarted.global_kill_active is True
    assert restarted.is_account_paused(ACCOUNT_ID) is True
    assert restarted.is_deployment_paused(DEPLOYMENT_ID) is True


def test_runtime_store_does_not_create_orders_without_order_manager(tmp_path) -> None:  # type: ignore[no-untyped-def]
    db_path = tmp_path / "utos.db"
    manager = OrderManager(ledger=SQLiteOrderLedger(db_path))
    order = make_signal_plan_order(manager, account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_ID)

    assert SQLiteRuntimeStore(db_path).load_order(order.order_id).order_id == order.order_id


def test_broker_adapter_cannot_create_or_persist_internal_order() -> None:
    import inspect
    import backend.app.brokers.adapter as adapter_module

    source = inspect.getsource(adapter_module.BrokerAdapter)

    assert ".add(" not in source
    assert "save_order" not in source
    assert "InternalOrder(" not in source


def test_broker_sync_is_only_broker_truth_persistence_writer() -> None:
    import inspect
    import backend.app.brokers.adapter as adapter_module
    import backend.app.brokers.sync as sync_module

    adapter_source = inspect.getsource(adapter_module)
    sync_module_source = inspect.getsource(sync_module)

    assert "save_broker_account_snapshot" not in adapter_source
    assert "save_broker_sync_freshness" not in adapter_source
    assert "save_broker_order_mapping" not in adapter_source
    assert "save_broker_account_snapshot" in sync_module_source
    assert "save_broker_sync_freshness" in sync_module_source


def test_sim_lab_does_not_use_broker_adapter_or_runtime_persistence() -> None:
    import inspect
    import backend.app.simulation.historical_replay as historical_replay

    source = inspect.getsource(historical_replay)

    assert "BrokerAdapter" not in source
    assert "SQLiteRuntimeStore" not in source
    assert "runtime_store" not in source
    assert "persistence" not in source


def test_chart_lab_does_not_create_orders_trades_or_broker_state() -> None:
    import inspect
    import backend.app.chart_lab.preview_service as preview_service

    source = inspect.getsource(preview_service)

    for forbidden in ["OrderManager", "InternalOrder", "BrokerSync", "BrokerAdapter", "TradeLedger", "SQLiteRuntimeStore"]:
        assert forbidden not in source

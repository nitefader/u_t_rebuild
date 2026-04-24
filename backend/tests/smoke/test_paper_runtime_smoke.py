from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import backend.app.brokers.alpaca as alpaca_module
from backend.app.brokers import (
    AlpacaBrokerAdapter,
    BrokerAccountSnapshot,
    BrokerOpenOrderSnapshot,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSync,
    BrokerSyncState,
)
from backend.app.broker_accounts import BrokerAccount, BrokerAccountValidationStatus
from backend.app.control_plane import ControlPlane
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
from backend.app.features import BatchFeatureEngine, NormalizedBar, ResolvedProgramComponents
from backend.app.governor import BrokerSyncFreshness as GovernorBrokerSyncFreshness
from backend.app.governor import GovernorPolicy, PortfolioGovernor
from backend.app.operations import OperationsCenterService
from backend.app.orders import InternalOrder, InternalOrderStatus, OrderManager
from backend.app.persistence import SQLiteOrderLedger, SQLiteRuntimeStore
from backend.app.pipeline import PipelineEventType, RuntimeOrchestrator
from backend.app.runtime import DeploymentContext, RuntimeRecoveryOrchestrator, RuntimeStatus


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
NOW = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)


class FakeAlpacaOrderRequest:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class MockAlpacaClient:
    def __init__(self) -> None:
        self.submitted_client_order_ids: list[str] = []
        self.orders_by_client_order_id: dict[str, dict[str, object]] = {}
        self.account_payload = {
            "buying_power": "90000",
            "daytrading_buying_power": "90000",
            "cash": "50000",
            "equity": "100000",
            "status": "ACTIVE",
            "trading_blocked": False,
            "account_blocked": False,
            "pattern_day_trader": False,
            "shorting_enabled": True,
        }
        self.positions_payload = [
            {
                "symbol": "SPY",
                "qty": "10",
                "market_value": "4010",
                "avg_entry_price": "400",
                "unrealized_pl": "10",
            }
        ]

    @property
    def submit_count(self) -> int:
        return len(self.submitted_client_order_ids)

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, object]:
        try:
            return self.orders_by_client_order_id[client_order_id]
        except KeyError as exc:
            raise RuntimeError("order not found") from exc

    def submit_order(self, *, order_data: FakeAlpacaOrderRequest) -> dict[str, object]:
        client_order_id = str(order_data.kwargs["client_order_id"])
        self.submitted_client_order_ids.append(client_order_id)
        payload = {
            "id": f"alpaca-{client_order_id}",
            "client_order_id": client_order_id,
            "symbol": order_data.kwargs["symbol"],
            "side": "buy",
            "type": "market",
            "qty": str(order_data.kwargs["qty"]),
            "filled_qty": "0",
            "status": "new",
            "submitted_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
        }
        self.orders_by_client_order_id[client_order_id] = payload
        return payload

    def get_orders(self) -> list[dict[str, object]]:
        return list(self.orders_by_client_order_id.values())

    def get_account(self) -> dict[str, object]:
        return dict(self.account_payload)

    def get_all_positions(self) -> list[dict[str, object]]:
        return list(self.positions_payload)


def _components() -> ResolvedProgramComponents:
    strategy_id = uuid4()
    controls_id = uuid4()
    risk_id = uuid4()
    execution_id = uuid4()
    universe_id = uuid4()
    strategy = StrategyVersion(
        id=strategy_id,
        strategy_id=uuid4(),
        version=1,
        name="Paper Smoke Strategy",
        entry_rules=[
            SignalRule(
                name="close_above_open",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close[0]",
                    operator=ConditionOperator.GREATER_THAN,
                    right_feature="5m.open[0]",
                ),
                stop_candidate_feature="5m.low[0]",
                target_candidate_feature="5m.high[0]",
            )
        ],
    )
    controls = StrategyControlsVersion(
        id=controls_id,
        strategy_controls_id=uuid4(),
        version=1,
        name="Paper Smoke Controls",
        timeframe="5m",
    )
    risk = RiskProfileVersion(
        id=risk_id,
        risk_profile_id=uuid4(),
        version=1,
        name="Fixed Smoke Shares",
        sizing_method=PositionSizingMethod.FIXED_SHARES,
        fixed_shares=10,
    )
    execution = ExecutionStyleVersion(
        id=execution_id,
        execution_style_id=uuid4(),
        version=1,
        name="Paper Market",
        entry_order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    universe = UniverseSnapshot(
        id=universe_id,
        universe_id=uuid4(),
        version=1,
        name="Paper Smoke Universe",
        symbols=[UniverseSymbol(symbol="SPY")],
    )
    program = ProgramVersion(
        id=uuid4(),
        program_id=uuid4(),
        name="Paper Smoke Program",
        version=1,
        strategy_version_id=strategy_id,
        strategy_controls_version_id=controls_id,
        risk_profile_version_id=risk_id,
        execution_style_version_id=execution_id,
        universe_snapshot_id=universe_id,
    )
    return ResolvedProgramComponents(
        program=program,
        strategy=strategy,
        strategy_controls=controls,
        risk_profile=risk,
        execution_style=execution,
        universe=universe,
    )


def _deployment(components: ResolvedProgramComponents) -> DeploymentContext:
    return DeploymentContext(deployment_id=DEPLOYMENT_ID, program=components.program)


def _bar(*, index: int = 0, open_: float = 99, close: float = 100) -> NormalizedBar:
    return NormalizedBar(
        symbol="SPY",
        timeframe="5m",
        timestamp=NOW + timedelta(minutes=5 * index),
        open=open_,
        high=max(open_, close) + 2,
        low=min(open_, close) - 2,
        close=close,
        volume=100_000 + index,
    )


def _paper_context(tmp_path, monkeypatch, *, broker_freshness: GovernorBrokerSyncFreshness | None = None, control_plane: ControlPlane | None = None):
    monkeypatch.setattr(alpaca_module, "MarketOrderRequest", FakeAlpacaOrderRequest)
    db_path = tmp_path / "paper-runtime-smoke.db"
    store = SQLiteRuntimeStore(db_path)
    ledger = SQLiteOrderLedger(db_path)
    manager = OrderManager(ledger=ledger, control_plane=control_plane)
    client = MockAlpacaClient()
    adapter = AlpacaBrokerAdapter(trading_client=client, load_env=False)
    broker_sync = BrokerSync(ledger=ledger, adapter=adapter, runtime_store=store, provider="alpaca")
    components = _components()
    deployment = _deployment(components)
    governor_policy = GovernorPolicy(max_open_positions=5)
    store.save_portfolio_governor_state("portfolio-governor", governor_policy)
    runtime_control_plane = control_plane or ControlPlane(state_store=store)
    pipeline = RuntimeOrchestrator(
        account_id=ACCOUNT_ID,
        deployment=deployment,
        components=components,
        governor=PortfolioGovernor(governor_policy, state_store=store),
        order_manager=manager,
        broker_adapter=adapter,
        broker_sync=broker_sync,
        broker_freshness=broker_freshness or GovernorBrokerSyncFreshness(),
        control_plane=runtime_control_plane,
        runtime_store=store,
    )
    return {
        "store": store,
        "ledger": ledger,
        "manager": manager,
        "client": client,
        "adapter": adapter,
        "broker_sync": broker_sync,
        "components": components,
        "deployment": deployment,
        "control_plane": runtime_control_plane,
        "pipeline": pipeline,
        "governor_policy": governor_policy,
    }


def _seed_broker_truth(store: SQLiteRuntimeStore, adapter: AlpacaBrokerAdapter, broker_sync: BrokerSync, order: InternalOrder) -> None:
    account_snapshot = adapter.get_account_snapshot(ACCOUNT_ID)
    store.save_broker_account(
        BrokerAccount(
            id=ACCOUNT_ID,
            display_name="Paper smoke account",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            credentials_ref=f"alpaca-paper:{ACCOUNT_ID}:smoke",
            validation_status=BrokerAccountValidationStatus.VALID,
            last_account_snapshot=account_snapshot,
            created_at=NOW,
        )
    )
    broker_sync.sync_account(ACCOUNT_ID)
    for open_order in adapter.list_open_orders(ACCOUNT_ID):
        broker_sync.record_external_open_order(open_order)
        store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=ACCOUNT_ID,
            last_sync_at=NOW,
            last_poll_sync_at=NOW,
            last_successful_sync_at=NOW,
            is_stale=False,
        )
    )
    store.save_broker_account_snapshot(account_snapshot.model_copy(update={"timestamp": NOW}))
    if not store.list_broker_open_order_snapshots(ACCOUNT_ID):
        store.save_broker_open_order_snapshot(
            BrokerOpenOrderSnapshot(
                account_id=ACCOUNT_ID,
                broker_order_id=f"alpaca-{order.client_order_id}",
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side.value,
                qty=order.quantity,
                status=BrokerOrderStatus.ACCEPTED,
                order_type=order.order_type.value,
                timestamp=NOW,
            )
        )


def _operations_service(context: dict[str, object], latest_events=(), latest_decisions=()) -> OperationsCenterService:
    return OperationsCenterService(
        control_plane=context["control_plane"],
        runtime_store=context["store"],
        broker_sync_reader=_ReadOnlyBrokerSyncReader(),
        deployments=(context["deployment"],),
        latest_pipeline_events=latest_events,
        latest_governor_decisions=latest_decisions,
        governor_state=context["governor_policy"],
    )


class _ReadOnlyBrokerSyncReader:
    def latest_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return (
            BrokerPositionSnapshot(
                account_id=account_id,
                symbol="SPY",
                qty=10,
                side=BrokerPositionSide.LONG,
                avg_entry_price=400,
                market_value=4010,
                timestamp=NOW,
            ),
        )

    def fills(self) -> tuple[object, ...]:
        return ()


def test_end_to_end_market_order_paper_flow(tmp_path, monkeypatch) -> None:
    context = _paper_context(tmp_path, monkeypatch)
    result = context["pipeline"].process_bar(_bar())
    order = result.orders[0]
    _seed_broker_truth(context["store"], context["adapter"], context["broker_sync"], order)
    overview = _operations_service(context, result.events, result.governor_decisions).get_runtime_overview()

    batch_snapshot = BatchFeatureEngine().compute(context["pipeline"].feature_plan, [_bar()]).frame_for("SPY", "5m").snapshots[0]
    assert batch_snapshot.value_for(next(key for key in batch_snapshot.values if "price.close" in key)) == 100
    assert len(result.candidate_intents) == 1
    assert any(event.event_type == PipelineEventType.CANDIDATE_TRADE_INTENT for event in result.events)
    assert result.execution_intents[0].qty == 10
    assert result.governor_decisions[0].approved is True
    assert len(result.orders) == 1
    assert context["client"].submitted_client_order_ids == [order.client_order_id]
    assert result.ledger_updates[0].status == InternalOrderStatus.ACCEPTED
    assert context["store"].load_order(order.order_id).status == InternalOrderStatus.ACCEPTED
    assert context["store"].lookup_broker_mapping_by_internal_order_id(order.order_id).broker_order_id == f"alpaca-{order.client_order_id}"
    assert overview.broker_accounts[0].account_id == ACCOUNT_ID
    assert overview.deployments[0].deployment_id == DEPLOYMENT_ID
    assert overview.open_orders_count == 1
    assert overview.open_positions_count == 1


def test_duplicate_submit_protection_through_client_order_id(tmp_path, monkeypatch) -> None:
    context = _paper_context(tmp_path, monkeypatch)
    result = context["pipeline"].process_bar(_bar())
    order = result.orders[0]

    second_result = context["adapter"].submit_order(order)

    assert context["client"].submitted_client_order_ids == [order.client_order_id]
    assert second_result.client_order_id == order.client_order_id
    assert second_result.broker_order_id == f"alpaca-{order.client_order_id}"


def test_recovery_after_submitted_order_does_not_create_duplicate_order(tmp_path, monkeypatch) -> None:
    context = _paper_context(tmp_path, monkeypatch)
    result = context["pipeline"].process_bar(_bar())
    order = result.orders[0]
    _seed_broker_truth(context["store"], context["adapter"], context["broker_sync"], order)
    before_submit_count = context["client"].submit_count
    before_order_ids = {stored.order_id for stored in context["store"].list_orders()}

    recovery = RuntimeRecoveryOrchestrator(
        persistence_store=context["store"],
        broker_adapter=context["adapter"],
        broker_sync=context["broker_sync"],
        governor_service=PortfolioGovernor(context["governor_policy"], state_store=context["store"]),
        control_plane=context["control_plane"],
        runtime_state_store=context["store"],
    )
    recovery_result = recovery.run_startup_recovery()

    assert recovery_result.recovered_accounts == 1
    assert context["client"].submit_count == before_submit_count
    assert {stored.order_id for stored in context["store"].list_orders()} == before_order_ids


def test_operations_overview_shows_recovered_runtime_state(tmp_path, monkeypatch) -> None:
    context = _paper_context(tmp_path, monkeypatch)
    result = context["pipeline"].process_bar(_bar())
    order = result.orders[0]
    _seed_broker_truth(context["store"], context["adapter"], context["broker_sync"], order)
    RuntimeRecoveryOrchestrator(
        persistence_store=context["store"],
        broker_adapter=context["adapter"],
        broker_sync=context["broker_sync"],
        governor_service=PortfolioGovernor(context["governor_policy"], state_store=context["store"]),
        control_plane=context["control_plane"],
        runtime_state_store=context["store"],
    ).run_startup_recovery()

    overview = _operations_service(context, result.events, result.governor_decisions).get_runtime_overview()

    assert overview.deployments[0].status == RuntimeStatus.RECOVERED_READY
    assert overview.deployments[0].is_running is False
    assert overview.latest_governor_decisions == result.governor_decisions
    assert overview.latest_runtime_event_timestamp == max(event.timestamp for event in result.events)


def test_stale_broker_sync_blocks_new_opens(tmp_path, monkeypatch) -> None:
    context = _paper_context(
        tmp_path,
        monkeypatch,
        broker_freshness=GovernorBrokerSyncFreshness(is_stale=True, reason="broker_sync_stale"),
    )

    result = context["pipeline"].process_bar(_bar())

    assert len(result.candidate_intents) == 1
    assert result.governor_decisions[0].approved is False
    assert result.governor_decisions[0].reason == "broker_sync_stale"
    assert result.orders == ()
    assert context["client"].submitted_client_order_ids == []


def test_global_kill_blocks_new_opens_but_preserves_existing_broker_truth(tmp_path, monkeypatch) -> None:
    context = _paper_context(tmp_path, monkeypatch)
    accepted = context["pipeline"].process_bar(_bar())
    existing_order = accepted.orders[0]
    _seed_broker_truth(context["store"], context["adapter"], context["broker_sync"], existing_order)
    context["control_plane"].activate_global_kill()

    blocked = context["pipeline"].process_bar(_bar(index=1, open_=101, close=102))
    overview = _operations_service(context, accepted.events + blocked.events, accepted.governor_decisions + blocked.governor_decisions).get_runtime_overview()

    assert blocked.candidate_intents
    assert blocked.orders == ()
    assert context["client"].submitted_client_order_ids == [existing_order.client_order_id]
    assert context["store"].lookup_broker_mapping_by_internal_order_id(existing_order.order_id).broker_order_id == f"alpaca-{existing_order.client_order_id}"
    assert context["store"].list_broker_open_order_snapshots(ACCOUNT_ID)[0].client_order_id == existing_order.client_order_id
    assert overview.global_kill_active is True
    assert overview.open_orders_count == 1

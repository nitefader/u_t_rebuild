from __future__ import annotations

import inspect
from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerSync,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)
from backend.app.domain import TradingMode
from backend.app.domain._base import utc_now
from backend.app.features import NormalizedBar
from backend.app.governor import GovernorPolicy, PortfolioGovernor, PortfolioSnapshot
from backend.app.orders import InternalOrder, OrderManager
from backend.app.pipeline import RuntimeOrchestrator
import tools.check_alpaca_readiness as readiness
import tools.paper_order_smoke as smoke
import tools.run_runtime_smoke as runtime_smoke
import tools.run_runtime_dry_run as runtime_dry_run


ACCOUNT_ID = UUID("00000000-0000-0000-0000-000000000001")


class FakeSmokeAdapter:
    submitted_orders: list[InternalOrder] = []
    market_is_open = True
    calls: list[str] = []

    def __init__(self) -> None:
        FakeSmokeAdapter.calls.append("AlpacaBrokerAdapter.__init__")
        self.submitted_orders = FakeSmokeAdapter.submitted_orders

    def get_market_clock(self) -> dict[str, object]:
        FakeSmokeAdapter.calls.append("AlpacaBrokerAdapter.get_market_clock")
        return {"is_open": FakeSmokeAdapter.market_is_open}

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        FakeSmokeAdapter.calls.append("AlpacaBrokerAdapter.submit_order")
        assert isinstance(order, InternalOrder)
        self.submitted_orders.append(order)
        return BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.ACCEPTED,
            broker_order_id="paper-1",
            broker_status="new",
            filled_quantity=0,
            remaining_quantity=order.quantity,
            raw_status="new",
        )


class FakeReadinessAdapter:
    submit_count = 0

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        _ = order
        FakeReadinessAdapter.submit_count += 1
        raise AssertionError("readiness check must not submit orders")

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            account_id=account_id,
            provider="fake",
            mode=TradingMode.BROKER_PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
            last_synced_at=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        )

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        return (
            BrokerPositionSnapshot(
                account_id=account_id,
                symbol="SPY",
                quantity=1,
                market_value=100,
                avg_entry_price=100,
                side=BrokerPositionSide.LONG,
                last_synced_at=utc_now(),
            ),
        )

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOrderResult, ...]:
        return (
            BrokerOrderResult(
                order_id=uuid4(),
                client_order_id="utos-test",
                status=BrokerOrderStatus.ACCEPTED,
                broker_order_id="paper-open-1",
                broker_status="new",
            ),
        )


class FakeRuntimeAdapter:
    submitted_orders: list[InternalOrder] = []
    market_is_open = True
    calls: list[str] = []

    def __init__(self) -> None:
        FakeRuntimeAdapter.calls.append("AlpacaBrokerAdapter.__init__")
        self.submitted_orders = FakeRuntimeAdapter.submitted_orders

    def get_market_clock(self) -> dict[str, object]:
        FakeRuntimeAdapter.calls.append("AlpacaBrokerAdapter.get_market_clock")
        return {"is_open": FakeRuntimeAdapter.market_is_open}

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        FakeRuntimeAdapter.calls.append("AlpacaBrokerAdapter.submit_order")
        assert isinstance(order, InternalOrder)
        self.submitted_orders.append(order)
        return BrokerOrderResult(
            order_id=order.order_id,
            client_order_id=order.client_order_id,
            status=BrokerOrderStatus.ACCEPTED,
            broker_order_id="runtime-paper-1",
            broker_status="new",
            filled_quantity=0,
            remaining_quantity=order.quantity,
            raw_status="new",
        )

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        FakeRuntimeAdapter.calls.append("AlpacaBrokerAdapter.get_account_snapshot")
        return BrokerAccountSnapshot(
            account_id=account_id,
            provider="fake",
            mode=TradingMode.BROKER_PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
            last_synced_at=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
        )

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        FakeRuntimeAdapter.calls.append("AlpacaBrokerAdapter.get_positions")
        return ()

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOrderResult, ...]:
        FakeRuntimeAdapter.calls.append("AlpacaBrokerAdapter.list_open_orders")
        return ()


def _paper_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ALPACA_BASE_URL", smoke.PAPER_BASE_URL)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    monkeypatch.setenv("CONFIRM_PAPER_ORDER", "yes")
    monkeypatch.delenv("UTOS_BROKER_ACCOUNT_ID", raising=False)
    monkeypatch.setattr(smoke, "load_dotenv", lambda: False)
    monkeypatch.setattr(readiness, "load_dotenv", lambda: False)
    monkeypatch.setattr(runtime_smoke, "load_dotenv", lambda: False)
    monkeypatch.setattr(runtime_dry_run, "load_dotenv", lambda: False)


def _runtime_smoke_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    monkeypatch.setenv("CONFIRM_PAPER_RUNTIME", "yes")


class FakeDryRunMarketDataAdapter:
    collect_count = 0

    def collect_bars_sync(self, *, subscription, timeout_seconds):  # type: ignore[no-untyped-def]
        _ = timeout_seconds
        FakeDryRunMarketDataAdapter.collect_count += 1
        return tuple(
            NormalizedBar(
                symbol=subscription.symbol,
                timeframe=subscription.timeframe,
                timestamp=datetime(2026, 1, 2, 14, 30 + index, tzinfo=timezone.utc),
                open=100 + index,
                high=102 + index,
                low=99 + index,
                close=101 + index,
                volume=100_000 + index,
            )
            for index in range(subscription.limit)
        )


def test_cli_refuses_without_confirm(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    monkeypatch.delenv("CONFIRM_PAPER_ORDER", raising=False)
    FakeSmokeAdapter.submitted_orders = []
    monkeypatch.setattr(smoke, "AlpacaBrokerAdapter", FakeSmokeAdapter)

    code = smoke.main([])

    assert code == 2
    assert "CONFIRM_PAPER_ORDER=yes" in capsys.readouterr().err
    assert FakeSmokeAdapter.submitted_orders == []


def test_cli_refuses_non_paper_base_url(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    monkeypatch.setenv("ALPACA_BASE_URL", "https://api.alpaca.markets")
    FakeSmokeAdapter.submitted_orders = []
    monkeypatch.setattr(smoke, "AlpacaBrokerAdapter", FakeSmokeAdapter)

    code = smoke.main([])

    assert code == 2
    assert "ALPACA_BASE_URL" in capsys.readouterr().err
    assert FakeSmokeAdapter.submitted_orders == []


def test_cli_refuses_qty_above_one(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)

    code = smoke.main(["--qty", "2"])

    assert code == 2
    assert "qty > 1" in capsys.readouterr().err


def test_successful_market_open_path_calls_order_manager_adapter_broker_sync(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    FakeSmokeAdapter.submitted_orders = []
    FakeSmokeAdapter.market_is_open = True
    calls: list[str] = []
    FakeSmokeAdapter.calls = calls

    class RecordingOrderManager:
        def __init__(self) -> None:
            calls.append("OrderManager.__init__")
            self._manager = OrderManager()

        @property
        def ledger(self):  # type: ignore[no-untyped-def]
            return self._manager.ledger

        def create_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_order")
            return self._manager.create_order(**kwargs)

        def create_manual_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_manual_order")
            return self._manager.create_manual_order(**kwargs)

        def create_signal_plan_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_signal_plan_order")
            return self._manager.create_signal_plan_order(**kwargs)

    class RecordingBrokerSync:
        def __init__(self, *, ledger, adapter) -> None:  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.__init__")
            self._sync = BrokerSync(ledger=ledger, adapter=adapter)

        def apply_result(self, result):  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.apply_result")
            return self._sync.apply_result(result)

    monkeypatch.setattr(smoke, "AlpacaBrokerAdapter", FakeSmokeAdapter)
    monkeypatch.setattr(smoke, "OrderManager", RecordingOrderManager)
    monkeypatch.setattr(smoke, "BrokerSync", RecordingBrokerSync)

    code = smoke.main([])

    output = capsys.readouterr().out
    assert code == 0
    assert len(FakeSmokeAdapter.submitted_orders) == 1
    order = FakeSmokeAdapter.submitted_orders[0]
    assert order.client_order_id.startswith("manual-00000000-open-")
    assert order.symbol == "SPY"
    assert order.quantity == 1
    assert '"status": "accepted"' in output
    assert calls.index("OrderManager.create_manual_order") < calls.index("AlpacaBrokerAdapter.submit_order")
    assert calls.index("AlpacaBrokerAdapter.submit_order") < calls.index("BrokerSync.apply_result")


def test_cli_refuses_when_market_closed(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    FakeSmokeAdapter.submitted_orders = []
    FakeSmokeAdapter.market_is_open = False
    calls: list[str] = []
    FakeSmokeAdapter.calls = calls

    class RecordingOrderManager:
        def __init__(self) -> None:
            calls.append("OrderManager.__init__")
            self._manager = OrderManager()

        @property
        def ledger(self):  # type: ignore[no-untyped-def]
            return self._manager.ledger

        def create_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_order")
            return self._manager.create_order(**kwargs)

        def create_signal_plan_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_signal_plan_order")
            return self._manager.create_signal_plan_order(**kwargs)

        def create_signal_plan_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_signal_plan_order")
            return self._manager.create_signal_plan_order(**kwargs)

    class RecordingBrokerSync:
        def __init__(self, *, ledger, adapter) -> None:  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.__init__")
            self._sync = BrokerSync(ledger=ledger, adapter=adapter)

        def apply_result(self, result):  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.apply_result")
            return self._sync.apply_result(result)

    monkeypatch.setattr(smoke, "AlpacaBrokerAdapter", FakeSmokeAdapter)
    monkeypatch.setattr(smoke, "OrderManager", RecordingOrderManager)
    monkeypatch.setattr(smoke, "BrokerSync", RecordingBrokerSync)

    code = smoke.main([])

    output = capsys.readouterr().out
    assert code == 0
    assert "Market closed. No order submitted." in output
    assert FakeSmokeAdapter.submitted_orders == []
    assert "OrderManager.create_order" not in calls
    assert "AlpacaBrokerAdapter.submit_order" not in calls
    assert "BrokerSync.apply_result" not in calls


def test_cli_does_not_call_alpaca_directly() -> None:
    source = inspect.getsource(smoke)

    assert "TradingClient" not in source
    assert "alpaca.trading" not in source
    assert ".submit_order(" in source
    assert "OrderManager" in source


def test_readiness_check_submits_no_orders(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    FakeReadinessAdapter.submit_count = 0
    monkeypatch.setattr(readiness, "AlpacaBrokerAdapter", FakeReadinessAdapter)

    code = readiness.main([])

    output = capsys.readouterr().out
    assert code == 0
    assert FakeReadinessAdapter.submit_count == 0
    assert '"positions"' in output
    assert '"open_orders"' in output


def test_runtime_smoke_produces_events(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _runtime_smoke_env(monkeypatch)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.calls = []
    FakeRuntimeAdapter.market_is_open = True
    monkeypatch.setattr(runtime_smoke, "AlpacaBrokerAdapter", FakeRuntimeAdapter)

    code = runtime_smoke.main(["--bars", "1"])

    output = capsys.readouterr().out
    assert code == 0
    assert '"ok": true' in output
    assert '"event_type": "candidate_trade_intent"' in output
    assert '"event_type": "order_created"' in output


def test_runtime_smoke_governor_blocks_when_required() -> None:
    components = runtime_smoke._components(symbol="SPY", qty=1)
    deployment = runtime_smoke.DeploymentContext(
        deployment_id=runtime_smoke.DEFAULT_DEPLOYMENT_ID,
        strategy_version_id=components.strategy.id,
        strategy_version=components.strategy.version,
        mode="runtime_smoke",
    )
    orchestrator = RuntimeOrchestrator(
        account_id=runtime_smoke.DEFAULT_ACCOUNT_ID,
        deployment=deployment,
        components=components,
        governor=PortfolioGovernor(GovernorPolicy(global_kill_active=True)),
        portfolio_snapshot=PortfolioSnapshot(equity=100_000),
    )

    result = orchestrator.process_bar(runtime_smoke._generated_completed_bars(symbol="SPY", count=1)[0])

    assert len(result.governor_decisions) == 1
    assert result.governor_decisions[0].approved is False
    assert result.orders == ()


def test_runtime_smoke_order_flows_through_all_layers(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _runtime_smoke_env(monkeypatch)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.market_is_open = True
    calls: list[str] = []
    FakeRuntimeAdapter.calls = calls

    class RecordingOrderManager:
        def __init__(self) -> None:
            calls.append("OrderManager.__init__")
            self._manager = OrderManager()

        @property
        def ledger(self):  # type: ignore[no-untyped-def]
            return self._manager.ledger

        def create_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_order")
            return self._manager.create_order(**kwargs)

        def create_signal_plan_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_signal_plan_order")
            return self._manager.create_signal_plan_order(**kwargs)

    class RecordingBrokerSync:
        def __init__(self, *, ledger, adapter) -> None:  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.__init__")
            self._sync = BrokerSync(ledger=ledger, adapter=adapter)

        def apply_result(self, result):  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.apply_result")
            return self._sync.apply_result(result)

        def sync_account(self, account_id):  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.sync_account")
            return self._sync.sync_account(account_id)

        def sync_positions(self, account_id):  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.sync_positions")
            return self._sync.sync_positions(account_id)

    monkeypatch.setattr(runtime_smoke, "AlpacaBrokerAdapter", FakeRuntimeAdapter)
    monkeypatch.setattr(runtime_smoke, "OrderManager", RecordingOrderManager)
    monkeypatch.setattr(runtime_smoke, "BrokerSync", RecordingBrokerSync)

    code = runtime_smoke.main(["--bars", "3"])

    output = capsys.readouterr().out
    assert code == 0
    assert len(FakeRuntimeAdapter.submitted_orders) == 1
    assert '"orders_created": 1' in output
    assert calls.index("OrderManager.create_signal_plan_order") < calls.index("AlpacaBrokerAdapter.submit_order")
    assert calls.index("AlpacaBrokerAdapter.submit_order") < calls.index("BrokerSync.apply_result")


def test_runtime_smoke_market_closed_exits_without_submit(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _runtime_smoke_env(monkeypatch)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.calls = []
    FakeRuntimeAdapter.market_is_open = False
    monkeypatch.setattr(runtime_smoke, "AlpacaBrokerAdapter", FakeRuntimeAdapter)

    code = runtime_smoke.main([])

    output = capsys.readouterr().out
    assert code == 0
    assert "Market closed. No runtime executed." in output
    assert FakeRuntimeAdapter.submitted_orders == []
    assert "AlpacaBrokerAdapter.submit_order" not in FakeRuntimeAdapter.calls


def test_runtime_smoke_blocks_without_confirmation(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    FakeRuntimeAdapter.submitted_orders = []
    monkeypatch.setattr(runtime_smoke, "AlpacaBrokerAdapter", FakeRuntimeAdapter)

    code = runtime_smoke.main([])

    assert code == 2
    assert "CONFIRM_PAPER_RUNTIME=yes" in capsys.readouterr().err
    assert FakeRuntimeAdapter.submitted_orders == []


def test_runtime_dry_run_submits_no_orders(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    monkeypatch.delenv("CONFIRM_PAPER_RUNTIME", raising=False)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.market_is_open = True
    FakeRuntimeAdapter.calls = []
    FakeDryRunMarketDataAdapter.collect_count = 0
    monkeypatch.setattr(runtime_dry_run, "AlpacaBrokerAdapter", FakeRuntimeAdapter)
    monkeypatch.setattr(runtime_dry_run, "AlpacaMarketDataAdapter", FakeDryRunMarketDataAdapter)

    code = runtime_dry_run.main(["--bars", "2"])

    output = capsys.readouterr().out
    assert code == 0
    assert '"mode": "dry_run"' in output
    assert '"orders_created": 0' in output
    assert '"candidate_decisions"' in output
    assert '"governor_decisions"' in output
    assert FakeRuntimeAdapter.submitted_orders == []
    assert "AlpacaBrokerAdapter.submit_order" not in FakeRuntimeAdapter.calls
    assert FakeDryRunMarketDataAdapter.collect_count == 1


def test_runtime_dry_run_market_closed_exits_cleanly(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.market_is_open = False
    FakeRuntimeAdapter.calls = []
    FakeDryRunMarketDataAdapter.collect_count = 0
    monkeypatch.setattr(runtime_dry_run, "AlpacaBrokerAdapter", FakeRuntimeAdapter)
    monkeypatch.setattr(runtime_dry_run, "AlpacaMarketDataAdapter", FakeDryRunMarketDataAdapter)

    code = runtime_dry_run.main([])

    output = capsys.readouterr().out
    assert code == 0
    assert "Market closed. No runtime executed." in output
    assert FakeRuntimeAdapter.submitted_orders == []
    assert FakeDryRunMarketDataAdapter.collect_count == 0


def test_runtime_dry_run_execute_requires_confirmation(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    monkeypatch.delenv("CONFIRM_PAPER_RUNTIME", raising=False)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.calls = []
    monkeypatch.setattr(runtime_dry_run, "AlpacaBrokerAdapter", FakeRuntimeAdapter)
    monkeypatch.setattr(runtime_dry_run, "AlpacaMarketDataAdapter", FakeDryRunMarketDataAdapter)

    code = runtime_dry_run.main(["--execute"])

    assert code == 2
    assert "CONFIRM_PAPER_RUNTIME=yes" in capsys.readouterr().err
    assert FakeRuntimeAdapter.submitted_orders == []
    assert FakeRuntimeAdapter.calls == []


def test_runtime_dry_run_execute_confirmation_blocks_before_market_clock(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _paper_env(monkeypatch)
    monkeypatch.delenv("CONFIRM_PAPER_RUNTIME", raising=False)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.calls = []
    FakeRuntimeAdapter.market_is_open = False
    FakeDryRunMarketDataAdapter.collect_count = 0
    monkeypatch.setattr(runtime_dry_run, "AlpacaBrokerAdapter", FakeRuntimeAdapter)
    monkeypatch.setattr(runtime_dry_run, "AlpacaMarketDataAdapter", FakeDryRunMarketDataAdapter)

    code = runtime_dry_run.main(["--execute"])

    captured = capsys.readouterr()
    assert code == 2
    assert "CONFIRM_PAPER_RUNTIME=yes" in captured.err
    assert "Market closed" not in captured.out
    assert FakeRuntimeAdapter.calls == []
    assert FakeRuntimeAdapter.submitted_orders == []
    assert FakeDryRunMarketDataAdapter.collect_count == 0


def test_runtime_dry_run_execute_uses_proper_order_path(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _runtime_smoke_env(monkeypatch)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.market_is_open = True
    FakeDryRunMarketDataAdapter.collect_count = 0
    calls: list[str] = []
    FakeRuntimeAdapter.calls = calls

    class RecordingOrderManager:
        def __init__(self) -> None:
            calls.append("OrderManager.__init__")
            self._manager = OrderManager()

        @property
        def ledger(self):  # type: ignore[no-untyped-def]
            return self._manager.ledger

        def create_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_order")
            return self._manager.create_order(**kwargs)

        def create_signal_plan_order(self, **kwargs):  # type: ignore[no-untyped-def]
            calls.append("OrderManager.create_signal_plan_order")
            return self._manager.create_signal_plan_order(**kwargs)

    class RecordingBrokerSync:
        def __init__(self, *, ledger, adapter) -> None:  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.__init__")
            self._sync = BrokerSync(ledger=ledger, adapter=adapter)

        def apply_result(self, result):  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.apply_result")
            return self._sync.apply_result(result)

        def sync_account(self, account_id):  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.sync_account")
            return self._sync.sync_account(account_id)

        def sync_positions(self, account_id):  # type: ignore[no-untyped-def]
            calls.append("BrokerSync.sync_positions")
            return self._sync.sync_positions(account_id)

    monkeypatch.setattr(runtime_dry_run, "AlpacaBrokerAdapter", FakeRuntimeAdapter)
    monkeypatch.setattr(runtime_dry_run, "AlpacaMarketDataAdapter", FakeDryRunMarketDataAdapter)
    monkeypatch.setattr(runtime_dry_run, "OrderManager", RecordingOrderManager)
    monkeypatch.setattr(runtime_dry_run, "BrokerSync", RecordingBrokerSync)

    code = runtime_dry_run.main(["--execute", "--bars", "3"])

    output = capsys.readouterr().out
    assert code == 0
    assert '"mode": "execute"' in output
    assert '"orders_created": 1' in output
    assert len(FakeRuntimeAdapter.submitted_orders) == 1
    assert calls.index("OrderManager.create_signal_plan_order") < calls.index("AlpacaBrokerAdapter.submit_order")
    assert calls.index("AlpacaBrokerAdapter.submit_order") < calls.index("BrokerSync.apply_result")


def test_runtime_dry_run_execute_enforces_max_one_order(monkeypatch, capsys) -> None:  # type: ignore[no-untyped-def]
    _runtime_smoke_env(monkeypatch)
    FakeRuntimeAdapter.submitted_orders = []
    FakeRuntimeAdapter.market_is_open = True
    FakeRuntimeAdapter.calls = []
    FakeDryRunMarketDataAdapter.collect_count = 0
    monkeypatch.setattr(runtime_dry_run, "AlpacaBrokerAdapter", FakeRuntimeAdapter)
    monkeypatch.setattr(runtime_dry_run, "AlpacaMarketDataAdapter", FakeDryRunMarketDataAdapter)

    code = runtime_dry_run.main(["--execute", "--bars", "5"])

    output = capsys.readouterr().out
    assert code == 0
    assert '"orders_created": 1' in output
    assert len(FakeRuntimeAdapter.submitted_orders) == 1

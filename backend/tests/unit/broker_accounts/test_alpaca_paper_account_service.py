from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

from backend.app.broker_accounts import BrokerAccountCreationError, BrokerAccountValidationStatus
from backend.app.broker_accounts.service import BrokerAccountService
from backend.app.brokers import BrokerAccountSnapshot, BrokerOpenOrderSnapshot, BrokerOrderStatus, BrokerPositionSide, BrokerPositionSnapshot
from backend.app.domain import TradingMode
from backend.app.operations import OperationsCenterService
from backend.app.orders import OrderLedger
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.control_plane import ControlPlane


class RecordingAlpacaPaperAdapter:
    instances: list["RecordingAlpacaPaperAdapter"] = []

    def __init__(self, *, mode, api_key, secret_key, load_env) -> None:
        self.mode = mode
        self.api_key = api_key
        self.secret_key = secret_key
        self.load_env = load_env
        self.calls: list[str] = []
        self.submitted = False
        RecordingAlpacaPaperAdapter.instances.append(self)

    def get_account_snapshot(self, account_id):
        self.calls.append("get_account_snapshot")
        return BrokerAccountSnapshot(
            account_id=account_id,
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            equity=100_000,
            cash=50_000,
            buying_power=75_000,
            account_status="ACTIVE",
        )

    def get_positions(self, account_id):
        self.calls.append("get_positions")
        return (
            BrokerPositionSnapshot(
                account_id=account_id,
                symbol="SPY",
                qty=2,
                side=BrokerPositionSide.LONG,
                avg_entry_price=500,
                market_value=1_000,
            ),
        )

    def list_open_orders(self, account_id):
        self.calls.append("list_open_orders")
        return (
            BrokerOpenOrderSnapshot(
                account_id=account_id,
                broker_order_id="alpaca-open-1",
                client_order_id="external-client-order",
                symbol="SPY",
                side="buy",
                qty=1,
                status=BrokerOrderStatus.ACCEPTED,
                order_type="market",
            ),
        )

    def submit_order(self, order):
        self.submitted = True
        raise AssertionError("account validation must not submit orders")

    def get_order(self, order):
        raise AssertionError("no local orders should be looked up for account creation")


class FailingAlpacaPaperAdapter(RecordingAlpacaPaperAdapter):
    def get_account_snapshot(self, account_id):
        self.calls.append("get_account_snapshot")
        raise RuntimeError("invalid alpaca credentials")


def test_create_alpaca_paper_account_persists_valid_account_and_syncs_broker_truth(tmp_path) -> None:
    RecordingAlpacaPaperAdapter.instances = []
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)

    account = service.create_alpaca_paper_account(
        display_name="Paper account",
        api_key="key",
        api_secret="secret",
    )

    adapter = RecordingAlpacaPaperAdapter.instances[0]
    assert adapter.mode == TradingMode.BROKER_PAPER
    assert adapter.load_env is False
    assert adapter.submitted is False
    assert adapter.calls == [
        "get_account_snapshot",
        "get_positions",
        "list_open_orders",
        "get_account_snapshot",
        "get_positions",
        "list_open_orders",
    ]
    assert account.provider == "alpaca"
    assert account.mode == TradingMode.BROKER_PAPER
    assert account.validation_status == BrokerAccountValidationStatus.VALID
    assert account.credentials_ref.startswith(f"alpaca-paper:{account.id}:")
    assert "secret" not in account.model_dump_json()
    assert store.load_broker_account(account.id) == account
    assert store.load_broker_account_snapshot(account.id).provider == "alpaca"
    assert store.load_broker_sync_freshness(account.id).is_stale is False
    assert len(store.list_broker_position_snapshots(account.id)) == 1
    assert len(store.list_broker_open_order_snapshots(account.id)) == 1
    assert store.list_orders() == ()


def test_invalid_alpaca_credentials_fail_without_persisting_account(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=FailingAlpacaPaperAdapter)

    with pytest.raises(BrokerAccountCreationError, match="invalid alpaca credentials"):
        service.create_alpaca_paper_account(display_name="Bad account", api_key="bad", api_secret="bad")

    assert store.list_broker_accounts() == ()
    assert store.list_broker_account_snapshots() == ()
    assert store.list_broker_sync_freshness() == ()


def test_created_account_appears_in_operations_overview_and_detail(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    account = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter).create_alpaca_paper_account(
        display_name="Paper account",
        api_key="key",
        api_secret="secret",
    )

    operations = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)
    overview = operations.get_runtime_overview()
    detail = operations.get_account_operations(account.id)

    assert [summary.account_id for summary in overview.broker_accounts] == [account.id]
    assert overview.open_orders_count == 0
    assert overview.open_positions_count == 1
    assert detail.broker_account_snapshot is not None
    assert len(detail.positions) == 1
    assert len(detail.open_broker_orders) == 1
    assert detail.broker_sync_freshness is not None


def test_account_creation_does_not_use_internal_order_ledger(tmp_path) -> None:
    class FailingLedger(OrderLedger):
        def all(self):  # type: ignore[no-untyped-def]
            raise AssertionError("account creation should not inspect internal orders")

        def by_account(self, account_id: UUID):  # type: ignore[no-untyped-def]
            return ()

    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(
        runtime_store=store,
        adapter_factory=RecordingAlpacaPaperAdapter,
        order_ledger=FailingLedger(),
    )

    account = service.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret")

    assert account.validation_status == BrokerAccountValidationStatus.VALID


def test_no_operations_demo_seed_paths_remain() -> None:
    root = Path(__file__).resolve().parents[3] / "app"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if "__pycache__" not in path.parts)

    assert "SEED_OPERATIONS_DEMO" not in sources
    assert "seed_operations_demo" not in sources
    assert "operations_demo" not in sources

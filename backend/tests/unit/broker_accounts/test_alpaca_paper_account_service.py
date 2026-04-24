from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.app.broker_accounts import BrokerAccount, BrokerAccountCreationError, BrokerAccountValidationStatus
from backend.app.broker_accounts.models import BrokerAccountCredentialValidationStatus, BrokerAccountDeletionStatus
from backend.app.broker_accounts.service import BrokerAccountService
from backend.app.brokers import BrokerAccountSnapshot, BrokerOpenOrderSnapshot, BrokerOrderMapping, BrokerOrderStatus, BrokerPositionSide, BrokerPositionSnapshot, BrokerSyncState
from backend.app.domain import TradingMode
from backend.app.operations import OperationsCenterService
from backend.app.orders import InternalOrderStatus, OrderLedger, OrderManager
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.control_plane import ControlPlane
from backend.app.runtime import RuntimeState, RuntimeStatus


class RecordingAlpacaPaperAdapter:
    instances: list["RecordingAlpacaPaperAdapter"] = []
    external_account_id = "alpaca-paper-account-1"

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
            external_account_id=self.external_account_id,
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


class LiveModeAlpacaAdapter(RecordingAlpacaPaperAdapter):
    def get_account_snapshot(self, account_id):
        snapshot = super().get_account_snapshot(account_id)
        return snapshot.model_copy(update={"mode": TradingMode.BROKER_LIVE})


def test_create_alpaca_paper_account_persists_valid_account_and_syncs_broker_truth(tmp_path) -> None:
    RecordingAlpacaPaperAdapter.instances = []
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)

    result = service.create_alpaca_paper_account(
        display_name="Paper account",
        api_key="key",
        api_secret="secret",
    )
    account = result.account

    assert result.already_exists is False
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
    assert account.external_account_id == "alpaca-paper-account-1"
    assert account.validation_status == BrokerAccountValidationStatus.VALID
    assert account.credentials_ref.startswith(f"alpaca-paper:{account.id}:")
    assert "secret" not in account.model_dump_json()
    assert store.load_broker_account(account.id) == account
    assert store.load_broker_account_snapshot(account.id).provider == "alpaca"
    assert store.load_broker_sync_freshness(account.id).is_stale is False
    assert len(store.list_broker_position_snapshots(account.id)) == 1
    assert len(store.list_broker_open_order_snapshots(account.id)) == 1
    assert store.list_orders() == ()


def test_create_same_alpaca_paper_account_twice_returns_same_account_and_refreshes_sync(tmp_path) -> None:
    RecordingAlpacaPaperAdapter.instances = []
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)

    first = service.create_alpaca_paper_account(
        display_name="Paper account",
        api_key="key",
        api_secret="secret",
    )
    second = service.create_alpaca_paper_account(
        display_name="Duplicate paper account",
        api_key="key",
        api_secret="secret",
    )

    assert first.account.id == second.account.id
    assert first.already_exists is False
    assert second.already_exists is True
    assert len(store.list_broker_accounts()) == 1
    operations = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)
    assert len(operations.get_runtime_overview().broker_accounts) == 1
    assert store.list_broker_accounts()[0].display_name == "Paper account"
    assert store.list_broker_accounts()[0].validation_status == BrokerAccountValidationStatus.VALID
    assert store.load_broker_sync_freshness(first.account.id).last_sync_at == second.account.broker_sync_freshness.last_sync_at
    assert len(RecordingAlpacaPaperAdapter.instances) == 2
    assert RecordingAlpacaPaperAdapter.instances[1].calls == [
        "get_account_snapshot",
        "get_positions",
        "list_open_orders",
        "get_account_snapshot",
        "get_positions",
        "list_open_orders",
    ]


def test_invalid_alpaca_credentials_fail_without_persisting_account(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=FailingAlpacaPaperAdapter)

    with pytest.raises(BrokerAccountCreationError, match="invalid alpaca credentials"):
        service.create_alpaca_paper_account(display_name="Bad account", api_key="bad", api_secret="bad")

    assert store.list_broker_accounts() == ()
    assert store.list_broker_account_snapshots() == ()
    assert store.list_broker_sync_freshness() == ()


def test_existing_paper_account_credentials_can_be_replaced_and_mark_sync_stale(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)
    account = service.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret").account

    result = service.replace_alpaca_paper_credentials(account_id=account.id, api_key="new-key", api_secret="new-secret")

    assert result.validation_status == BrokerAccountCredentialValidationStatus.VALID
    updated = store.load_broker_account(account.id)
    assert updated.validation_status == BrokerAccountValidationStatus.VALID
    assert updated.credentials_ref != account.credentials_ref
    assert "new-secret" not in updated.model_dump_json()
    assert store.load_broker_sync_freshness(account.id).is_stale is True
    assert store.load_broker_sync_freshness(account.id).stale_reason == "credentials_replaced_requires_broker_sync"


def test_masked_credentials_are_not_accepted_as_real_secrets(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)
    account = service.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret").account

    result = service.replace_alpaca_paper_credentials(account_id=account.id, api_key="********", api_secret="xxxxxxxx")

    assert result.validation_status == BrokerAccountCredentialValidationStatus.MISSING_CREDENTIALS
    assert store.load_broker_account(account.id).credentials_ref == account.credentials_ref


def test_invalid_replacement_credentials_do_not_mark_account_usable(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    creator = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)
    account = creator.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret").account

    result = BrokerAccountService(runtime_store=store, adapter_factory=FailingAlpacaPaperAdapter).replace_alpaca_paper_credentials(
        account_id=account.id,
        api_key="bad",
        api_secret="bad",
    )

    assert result.validation_status == BrokerAccountCredentialValidationStatus.INVALID
    assert store.load_broker_account(account.id).validation_status == BrokerAccountValidationStatus.INVALID
    assert store.load_broker_account(account.id).credentials_ref == account.credentials_ref


def test_mode_mismatch_replacement_is_rejected(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    account = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter).create_alpaca_paper_account(
        display_name="Paper account",
        api_key="key",
        api_secret="secret",
    ).account

    result = BrokerAccountService(runtime_store=store, adapter_factory=LiveModeAlpacaAdapter).replace_alpaca_paper_credentials(
        account_id=account.id,
        api_key="live-key",
        api_secret="live-secret",
    )

    assert result.validation_status == BrokerAccountCredentialValidationStatus.MODE_MISMATCH
    assert store.load_broker_account(account.id).validation_status == BrokerAccountValidationStatus.INVALID


def test_runtime_new_opens_are_blocked_until_replaced_credentials_are_resynced(tmp_path) -> None:
    from backend.tests.unit.runtime.test_broker_runtime_orchestrator import _runtime, _bar

    runtime, store, _broker = _runtime(tmp_path)
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)

    service.replace_alpaca_paper_credentials(account_id=UUID("11111111-2222-3333-4444-555555555555"), api_key="new-key", api_secret="new-secret")

    assert runtime.process_completed_bar(UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"), _bar()) is None
    assert store.load_deployment_runtime_state(UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")).last_error == "credentials_replaced_requires_broker_sync"


def test_active_runtime_account_cannot_silently_replace_credentials(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)
    account = service.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret").account
    deployment_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    store.save_deployment_runtime_state(RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.RUNNING))
    # Add account/deployment attribution through a persisted internal order.
    from backend.tests.unit.operations.test_operations_center_service import _intent
    order = OrderManager().create_order(account_id=account.id, execution_intent=_intent(deployment_id=deployment_id))
    store.save_order(order)

    try:
        service.replace_alpaca_paper_credentials(account_id=account.id, api_key="new-key", api_secret="new-secret")
    except BrokerAccountCreationError as exc:
        assert "must be paused" in str(exc)
    else:
        raise AssertionError("active runtime credential replacement must be blocked")


def test_paused_active_runtime_account_can_replace_credentials(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)
    account = service.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret").account
    deployment_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    store.save_deployment_runtime_state(RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.RUNNING))
    from backend.tests.unit.operations.test_operations_center_service import _intent
    store.save_order(OrderManager().create_order(account_id=account.id, execution_intent=_intent(deployment_id=deployment_id)))
    ControlPlane(state_store=store).pause_account(account.id)

    result = service.replace_alpaca_paper_credentials(account_id=account.id, api_key="new-key", api_secret="new-secret")

    assert result.validation_status == BrokerAccountCredentialValidationStatus.VALID


def test_created_account_appears_in_operations_overview_and_detail(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    result = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter).create_alpaca_paper_account(
        display_name="Paper account",
        api_key="key",
        api_secret="secret",
    )
    account = result.account

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


def test_account_with_running_deployment_cannot_be_deleted(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)
    account = service.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret").account
    from backend.tests.unit.operations.test_operations_center_service import _intent
    order = OrderManager().create_order(account_id=account.id, execution_intent=_intent())
    order = order.model_copy(update={"status": InternalOrderStatus.FILLED})
    store.save_order(order)
    store.save_deployment_runtime_state(RuntimeState(deployment_id=order.deployment_id, status=RuntimeStatus.RUNNING))

    result = service.delete_or_archive_account(account_id=account.id, confirm_display_name="Paper account", confirm_mode=TradingMode.BROKER_PAPER)

    assert result.status == BrokerAccountDeletionStatus.BLOCKED
    assert any(blocker.startswith("deployment_not_stopped") for blocker in result.blockers)


def test_account_with_open_orders_positions_or_stale_sync_cannot_be_deleted(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)
    account = service.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret").account

    result = service.delete_or_archive_account(account_id=account.id, confirm_display_name="Paper account", confirm_mode=TradingMode.BROKER_PAPER)

    assert result.status == BrokerAccountDeletionStatus.BLOCKED
    assert "open_broker_orders" in result.blockers
    assert "open_positions" in result.blockers


def test_account_with_stale_broker_sync_cannot_be_deleted(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    account = BrokerAccount(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        display_name="Stale paper",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:test",
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    store.save_broker_account(account)
    store.save_broker_sync_freshness(
        BrokerSyncState(
            account_id=account.id,
            last_sync_at=datetime.now(timezone.utc),
            is_stale=True,
            stale_reason="too_old",
        )
    )

    result = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter).delete_or_archive_account(
        account_id=account.id,
        confirm_display_name="Stale paper",
        confirm_mode=TradingMode.BROKER_PAPER,
    )

    assert result.status == BrokerAccountDeletionStatus.BLOCKED
    assert "broker_sync_stale" in result.blockers


def test_account_with_historical_records_is_archived_not_hard_deleted(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    account = BrokerAccount(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        display_name="Paper account",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:test",
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    store.save_broker_account(account)
    store.save_broker_sync_freshness(BrokerSyncState(account_id=account.id, last_sync_at=datetime.now(timezone.utc), is_stale=False))
    from backend.tests.unit.operations.test_operations_center_service import _intent
    order = OrderManager().create_order(account_id=account.id, execution_intent=_intent())
    order = order.model_copy(update={"status": InternalOrderStatus.FILLED})
    store.save_order(order)
    service = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter)

    result = service.delete_or_archive_account(account_id=account.id, confirm_display_name="Paper account", confirm_mode=TradingMode.BROKER_PAPER)

    assert result.status == BrokerAccountDeletionStatus.ARCHIVED
    assert store.load_broker_account(account.id).is_archived is True
    assert store.list_broker_accounts() == ()
    assert store.list_broker_accounts(include_archived=True)[0].id == account.id


def test_hard_delete_only_works_for_dependency_free_account(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    account = BrokerAccount(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        display_name="Empty paper",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:test",
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    store.save_broker_account(account)
    store.save_broker_sync_freshness(BrokerSyncState(account_id=account.id, last_sync_at=datetime.now(timezone.utc), is_stale=False))

    result = BrokerAccountService(runtime_store=store, adapter_factory=RecordingAlpacaPaperAdapter).delete_or_archive_account(
        account_id=account.id,
        confirm_display_name="Empty paper",
        confirm_mode=TradingMode.BROKER_PAPER,
    )

    assert result.status == BrokerAccountDeletionStatus.HARD_DELETED
    assert store.list_broker_accounts(include_archived=True) == ()


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

    result = service.create_alpaca_paper_account(display_name="Paper account", api_key="key", api_secret="secret")

    assert result.account.validation_status == BrokerAccountValidationStatus.VALID


def test_persistence_enforces_unique_broker_account_external_identity(tmp_path) -> None:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    account = BrokerAccount(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        display_name="Paper account",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        external_account_id="alpaca-paper-account-1",
        credentials_ref="alpaca-paper:one",
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    duplicate = account.model_copy(
        update={
            "id": UUID("22222222-3333-4444-5555-666666666666"),
            "credentials_ref": "alpaca-paper:two",
        }
    )

    store.save_broker_account(account)

    with pytest.raises(Exception, match="UNIQUE|unique"):
        store.save_broker_account(duplicate)


def test_no_operations_demo_seed_paths_remain() -> None:
    root = Path(__file__).resolve().parents[3] / "app"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if "__pycache__" not in path.parts)

    assert "SEED_OPERATIONS_DEMO" not in sources
    assert "seed_operations_demo" not in sources
    assert "operations_demo" not in sources

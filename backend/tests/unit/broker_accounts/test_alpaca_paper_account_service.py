"""Backend tests for the unified BrokerAccountService.

Per the production-grade principles (no paper-vs-live fork): the service
exposes one ``create_account`` and one ``replace_credentials``; tests
parametrize over ``BROKER_PAPER`` and ``BROKER_LIVE`` so both modes are
proven on every change. Secrets persist through the encrypted
``BrokerCredentialStore`` — never in env.
"""

from __future__ import annotations

import base64
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID

import pytest

from backend.app.broker_accounts import (
    BrokerAccount,
    BrokerAccountCreationError,
    BrokerAccountValidationStatus,
    BrokerCredentialStore,
)
from backend.app.broker_accounts.models import (
    BrokerAccountCredentialValidationStatus,
    BrokerAccountDeletionStatus,
)
from backend.app.broker_accounts.service import BrokerAccountService
from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerOpenOrderSnapshot,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
    BrokerSyncState,
)
from backend.app.control_plane import ControlPlane
from backend.app.domain import TradingMode
from backend.app.operations import OperationsCenterService
from backend.app.orders import InternalOrderStatus, OrderLedger, OrderManager
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.runtime import RuntimeState, RuntimeStatus
from backend.tests.fixtures.modern_order import make_signal_plan_order


def _master_key() -> bytes:
    return base64.b64decode("0" * 43 + "=")


def _make_credential_store(tmp_path: Path) -> BrokerCredentialStore:
    return BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_master_key())


class RecordingAlpacaAdapter:
    instances: list["RecordingAlpacaAdapter"] = []
    external_account_id = "alpaca-account-1"

    def __init__(self, *, mode, api_key, secret_key) -> None:
        self.mode = mode
        self.api_key = api_key
        self.secret_key = secret_key
        self.calls: list[str] = []
        self.submitted = False
        RecordingAlpacaAdapter.instances.append(self)

    def get_account_snapshot(self, account_id):
        self.calls.append("get_account_snapshot")
        return BrokerAccountSnapshot(
            account_id=account_id,
            provider="alpaca",
            mode=self.mode,
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


class FailingAdapter(RecordingAlpacaAdapter):
    def get_account_snapshot(self, account_id):
        self.calls.append("get_account_snapshot")
        raise RuntimeError("invalid alpaca credentials")


class WrongModeAdapter(RecordingAlpacaAdapter):
    def get_account_snapshot(self, account_id):
        snapshot = super().get_account_snapshot(account_id)
        # Force the snapshot to disagree with the operator-claimed mode.
        flipped = TradingMode.BROKER_LIVE if self.mode == TradingMode.BROKER_PAPER else TradingMode.BROKER_PAPER
        return snapshot.model_copy(update={"mode": flipped})


def _make_service(
    tmp_path: Path,
    *,
    adapter_factory=RecordingAlpacaAdapter,
    order_ledger=None,
) -> tuple[BrokerAccountService, SQLiteRuntimeStore]:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(
        runtime_store=store,
        credential_store=_make_credential_store(tmp_path),
        adapter_factory=adapter_factory,
        order_ledger=order_ledger,
    )
    return service, store


@pytest.mark.parametrize("mode", [TradingMode.BROKER_PAPER, TradingMode.BROKER_LIVE])
def test_create_account_persists_valid_account_and_syncs_broker_truth(tmp_path: Path, mode: TradingMode) -> None:
    RecordingAlpacaAdapter.instances = []
    service, store = _make_service(tmp_path)

    result = service.create_account(
        display_name=f"Account ({mode.value})",
        provider="alpaca",
        mode=mode,
        api_key="key",
        api_secret="secretvalue",
    )
    account = result.account

    assert result.already_exists is False
    adapter = RecordingAlpacaAdapter.instances[0]
    assert adapter.mode == mode
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
    assert account.mode == mode
    assert account.external_account_id == "alpaca-account-1"
    assert account.validation_status == BrokerAccountValidationStatus.VALID
    assert account.credentials_ref.startswith(f"alpaca-{mode.value.lower()}:{account.id}:")
    assert account.needs_credentials is False
    assert "secretvalue" not in account.model_dump_json()
    assert store.load_broker_account(account.id) == account
    assert store.load_broker_account_snapshot(account.id).provider == "alpaca"
    assert store.load_broker_sync_freshness(account.id).is_stale is False
    assert len(store.list_broker_position_snapshots(account.id)) == 1
    assert len(store.list_broker_open_order_snapshots(account.id)) == 1
    # Secret roundtrips through the encrypted store.
    assert service.get_credentials(account.id) == ("key", "secretvalue")


@pytest.mark.parametrize("mode", [TradingMode.BROKER_PAPER, TradingMode.BROKER_LIVE])
def test_create_same_account_twice_returns_same_account(tmp_path: Path, mode: TradingMode) -> None:
    RecordingAlpacaAdapter.instances = []
    service, store = _make_service(tmp_path)

    first = service.create_account(
        display_name="Account",
        provider="alpaca",
        mode=mode,
        api_key="key",
        api_secret="secretvalue",
    )
    second = service.create_account(
        display_name="Duplicate",
        provider="alpaca",
        mode=mode,
        api_key="key",
        api_secret="secretvalue",
    )

    assert first.account.id == second.account.id
    assert first.already_exists is False
    assert second.already_exists is True
    assert len(store.list_broker_accounts()) == 1


def test_invalid_credentials_fail_without_persisting_account(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path, adapter_factory=FailingAdapter)

    with pytest.raises(BrokerAccountCreationError, match="invalid alpaca credentials"):
        service.create_account(
            display_name="Bad",
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            api_key="bad",
            api_secret="badbadbad",
        )

    assert store.list_broker_accounts() == ()


def test_unsupported_provider_is_rejected(tmp_path: Path) -> None:
    service, _ = _make_service(tmp_path)
    with pytest.raises(BrokerAccountCreationError, match="unsupported provider"):
        service.create_account(
            display_name="x",
            provider="future-broker",
            mode=TradingMode.BROKER_PAPER,
            api_key="K",
            api_secret="S1234567",
        )


@pytest.mark.parametrize("mode", [TradingMode.BROKER_PAPER, TradingMode.BROKER_LIVE])
def test_replace_credentials_marks_sync_stale_and_updates_secrets(tmp_path: Path, mode: TradingMode) -> None:
    service, store = _make_service(tmp_path)
    account = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=mode,
        api_key="K1",
        api_secret="S1secret",
    ).account

    response = service.replace_credentials(
        account_id=account.id,
        api_key="K2",
        api_secret="S2secret",
    )

    assert response.validation_status == BrokerAccountCredentialValidationStatus.VALID
    updated = store.load_broker_account(account.id)
    assert updated.validation_status == BrokerAccountValidationStatus.VALID
    assert updated.credentials_ref != account.credentials_ref
    assert updated.needs_credentials is False
    assert "S2secret" not in updated.model_dump_json()
    assert store.load_broker_sync_freshness(account.id).is_stale is True
    assert store.load_broker_sync_freshness(account.id).stale_reason == "credentials_replaced_requires_broker_sync"
    # New secret persisted to the credential store.
    assert service.get_credentials(account.id) == ("K2", "S2secret")


def test_masked_credentials_rejected_on_replace(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="Ssample12",
    ).account

    response = service.replace_credentials(
        account_id=account.id, api_key="********", api_secret="xxxxxxxx"
    )

    assert response.validation_status == BrokerAccountCredentialValidationStatus.MISSING_CREDENTIALS
    assert store.load_broker_account(account.id).credentials_ref == account.credentials_ref


def test_invalid_replacement_credentials_mark_account_invalid(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="Ssample12",
    ).account

    failing_service = BrokerAccountService(
        runtime_store=store,
        credential_store=_make_credential_store(tmp_path),
        adapter_factory=FailingAdapter,
    )
    response = failing_service.replace_credentials(
        account_id=account.id, api_key="bad", api_secret="badpadding"
    )

    assert response.validation_status == BrokerAccountCredentialValidationStatus.INVALID
    assert store.load_broker_account(account.id).validation_status == BrokerAccountValidationStatus.INVALID


def test_mode_mismatch_replacement_is_rejected(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="Ssample12",
    ).account

    wrong_mode_service = BrokerAccountService(
        runtime_store=store,
        credential_store=_make_credential_store(tmp_path),
        adapter_factory=WrongModeAdapter,
    )
    response = wrong_mode_service.replace_credentials(
        account_id=account.id, api_key="K2", api_secret="S2sample"
    )

    assert response.validation_status == BrokerAccountCredentialValidationStatus.MODE_MISMATCH
    assert store.load_broker_account(account.id).validation_status == BrokerAccountValidationStatus.INVALID


def test_active_runtime_account_cannot_silently_replace_credentials(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="Ssample12",
    ).account
    deployment_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    store.save_deployment_runtime_state(RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.RUNNING))
    order = make_signal_plan_order(OrderManager(), account_id=account.id, deployment_id=deployment_id)
    store.save_order(order)

    with pytest.raises(BrokerAccountCreationError, match="must be paused"):
        service.replace_credentials(
            account_id=account.id, api_key="K2", api_secret="S2sample"
        )


def test_paused_active_runtime_account_can_replace_credentials(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="Ssample12",
    ).account
    deployment_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    store.save_deployment_runtime_state(RuntimeState(deployment_id=deployment_id, status=RuntimeStatus.RUNNING))
    store.save_order(make_signal_plan_order(OrderManager(), account_id=account.id, deployment_id=deployment_id))
    ControlPlane(state_store=store).pause_account(account.id)

    response = service.replace_credentials(
        account_id=account.id, api_key="K2", api_secret="S2sample"
    )

    assert response.validation_status == BrokerAccountCredentialValidationStatus.VALID


def test_created_account_appears_in_operations_overview_and_detail(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    result = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="Ssample12",
    )
    account = result.account

    operations = OperationsCenterService(control_plane=ControlPlane(state_store=store), runtime_store=store)
    overview = operations.get_runtime_overview()
    detail = operations.get_account_operations(account.id)

    assert [summary.account_id for summary in overview.broker_accounts] == [account.id]
    assert overview.open_positions_count == 1
    assert detail.broker_account_snapshot is not None


def test_account_with_running_deployment_cannot_be_deleted(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="Ssample12",
    ).account
    order = make_signal_plan_order(
        OrderManager(),
        account_id=account.id,
        deployment_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
    )
    order = order.model_copy(update={"status": InternalOrderStatus.FILLED})
    store.save_order(order)
    store.save_deployment_runtime_state(RuntimeState(deployment_id=order.deployment_id, status=RuntimeStatus.RUNNING))

    response = service.delete_or_archive_account(
        account_id=account.id, confirm_display_name="acct", confirm_mode=TradingMode.BROKER_PAPER
    )

    assert response.status == BrokerAccountDeletionStatus.BLOCKED
    assert any(blocker.startswith("deployment_not_stopped") for blocker in response.blockers)


def test_account_with_open_orders_or_positions_cannot_be_deleted(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = service.create_account(
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="Ssample12",
    ).account

    response = service.delete_or_archive_account(
        account_id=account.id, confirm_display_name="acct", confirm_mode=TradingMode.BROKER_PAPER
    )

    assert response.status == BrokerAccountDeletionStatus.BLOCKED
    assert "open_broker_orders" in response.blockers
    assert "open_positions" in response.blockers


def test_archive_drops_credentials_from_store(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = BrokerAccount(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:test",
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    store.save_broker_account(account)
    store.save_broker_sync_freshness(BrokerSyncState(account_id=account.id, last_sync_at=datetime.now(timezone.utc), is_stale=False))
    order = make_signal_plan_order(
        OrderManager(),
        account_id=account.id,
        deployment_id=UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"),
    )
    order = order.model_copy(update={"status": InternalOrderStatus.FILLED})
    store.save_order(order)
    # Pre-seed credentials so we can prove they're removed on archive.
    service._credential_store.put(account.id, api_key="K", api_secret="Sarchived")

    response = service.delete_or_archive_account(
        account_id=account.id, confirm_display_name="acct", confirm_mode=TradingMode.BROKER_PAPER
    )

    assert response.status == BrokerAccountDeletionStatus.ARCHIVED
    assert not service._credential_store.has(account.id)


def test_list_accounts_marks_needs_credentials_when_store_has_no_entry(tmp_path: Path) -> None:
    """Migration path: a record persisted before the encrypted store
    existed has no entry; the service flips needs_credentials so the UI
    surfaces the re-enter prompt and the runtime gates trading.
    """
    service, store = _make_service(tmp_path)
    legacy = BrokerAccount(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        display_name="legacy",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:legacy",
        needs_credentials=False,  # disk record predates the store
        validation_status=BrokerAccountValidationStatus.VALID,
    )
    store.save_broker_account(legacy)

    accounts = service.list_broker_accounts()
    assert len(accounts) == 1
    assert accounts[0].needs_credentials is True


def test_list_accounts_projects_current_broker_sync_and_snapshot(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account = BrokerAccount(
        id=UUID("11111111-2222-3333-4444-555555555555"),
        display_name="acct",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        credentials_ref="alpaca-paper:test",
        validation_status=BrokerAccountValidationStatus.VALID,
        broker_sync_freshness=BrokerSyncState(
            account_id=UUID("11111111-2222-3333-4444-555555555555"),
            last_sync_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            is_stale=True,
            stale_reason="old_embedded_state",
        ),
    )
    store.save_broker_account(account)
    service._credential_store.put(account.id, api_key="K", api_secret="S")

    fresh_state = BrokerSyncState(
        account_id=account.id,
        last_sync_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        last_successful_sync_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        is_stale=False,
    )
    store.save_broker_sync_freshness(fresh_state)
    store.save_broker_account_snapshot(
        BrokerAccountSnapshot(
            account_id=account.id,
            timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
            provider="alpaca",
            mode=TradingMode.BROKER_PAPER,
            equity=12345.67,
            cash=10000.0,
            buying_power=20000.0,
        )
    )

    listed = service.list_broker_accounts()

    assert listed[0].needs_credentials is False
    assert listed[0].broker_sync_freshness == fresh_state
    assert listed[0].last_account_snapshot is not None
    assert listed[0].last_account_snapshot.equity == 12345.67


def test_update_account_details_renames_display_name(tmp_path: Path) -> None:
    service, _store = _make_service(tmp_path)
    result = service.create_account(
        display_name="Alpha",
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="K",
        api_secret="S",
    )
    account_id = result.account.id
    updated = service.update_account_details(account_id=account_id, display_name="  Beta  ")
    assert updated.display_name == "Beta"


def test_no_operations_demo_seed_paths_remain() -> None:
    root = Path(__file__).resolve().parents[3] / "app"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py") if "__pycache__" not in path.parts)
    for forbidden in ("operations_demo_seed", "demo_paper_account"):
        assert forbidden not in sources

"""M11 Guardian Assignment — service + persistence round-trip tests.

Covers:
- ``BrokerAccountService.set_guardian_deployment`` round-trips through
  the runtime store JSON payload.
- Clear (`None`) is a no-op of state but valid call.
- Defensive reject when operator passes the Account id by mistake.
- ``BrokerAccountService.set_allow_live`` toggles the M10 per-Account
  live opt-in flag.
"""

from __future__ import annotations

import base64
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.app.broker_accounts import (
    BrokerAccountCreationError,
    BrokerCredentialStore,
)
from backend.app.broker_accounts.service import BrokerAccountService
from backend.app.domain import TradingMode
from backend.app.persistence import SQLiteRuntimeStore


def _master_key() -> bytes:
    return base64.b64decode("0" * 43 + "=")


def _make_credential_store(tmp_path: Path) -> BrokerCredentialStore:
    return BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_master_key())


class _StubAdapter:
    instances: list["_StubAdapter"] = []
    external_account_id = "alpaca-account-1"

    def __init__(self, *, mode, api_key, secret_key) -> None:
        self.mode = mode
        self.api_key = api_key
        self.secret_key = secret_key
        _StubAdapter.instances.append(self)

    def get_account_snapshot(self, account_id):  # noqa: ARG002
        from backend.app.brokers import BrokerAccountSnapshot

        return BrokerAccountSnapshot(
            account_id=account_id,
            provider="alpaca",
            mode=self.mode,
            external_account_id=self.external_account_id,
            equity=10_000,
            cash=5_000,
            buying_power=7_500,
            account_status="ACTIVE",
        )

    def get_positions(self, account_id):  # noqa: ARG002
        return ()

    def list_open_orders(self, account_id):  # noqa: ARG002
        return ()


def _make_service(tmp_path: Path) -> tuple[BrokerAccountService, SQLiteRuntimeStore]:
    store = SQLiteRuntimeStore(tmp_path / "runtime.sqlite3")
    service = BrokerAccountService(
        runtime_store=store,
        credential_store=_make_credential_store(tmp_path),
        adapter_factory=_StubAdapter,
    )
    return service, store


def _create(service: BrokerAccountService, *, name: str = "Paper 2") -> UUID:
    _StubAdapter.instances = []
    result = service.create_account(
        display_name=name,
        provider="alpaca",
        mode=TradingMode.BROKER_PAPER,
        api_key="ak",
        api_secret="sk",
    )
    return result.account.id


def test_set_guardian_persists_id(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account_id = _create(service)
    deployment_id = uuid4()

    updated = service.set_guardian_deployment(
        account_id=account_id,
        guardian_deployment_id=deployment_id,
    )
    assert updated.guardian_deployment_id == deployment_id

    reloaded = store.load_broker_account(account_id)
    assert reloaded.guardian_deployment_id == deployment_id


def test_set_guardian_clears_when_passed_none(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account_id = _create(service)
    deployment_id = uuid4()

    service.set_guardian_deployment(account_id=account_id, guardian_deployment_id=deployment_id)
    cleared = service.set_guardian_deployment(account_id=account_id, guardian_deployment_id=None)
    assert cleared.guardian_deployment_id is None
    assert store.load_broker_account(account_id).guardian_deployment_id is None


def test_set_guardian_rejects_when_id_matches_account(tmp_path: Path) -> None:
    service, _store = _make_service(tmp_path)
    account_id = _create(service)
    with pytest.raises(BrokerAccountCreationError):
        service.set_guardian_deployment(
            account_id=account_id,
            guardian_deployment_id=account_id,
        )


def test_set_guardian_rejects_unknown_account(tmp_path: Path) -> None:
    service, _store = _make_service(tmp_path)
    with pytest.raises(BrokerAccountCreationError):
        service.set_guardian_deployment(
            account_id=uuid4(),
            guardian_deployment_id=uuid4(),
        )


def test_set_allow_live_toggles_flag(tmp_path: Path) -> None:
    service, store = _make_service(tmp_path)
    account_id = _create(service)
    assert store.load_broker_account(account_id).allow_live is False

    enabled = service.set_allow_live(account_id=account_id, allow_live=True)
    assert enabled.allow_live is True
    assert store.load_broker_account(account_id).allow_live is True

    disabled = service.set_allow_live(account_id=account_id, allow_live=False)
    assert disabled.allow_live is False
    assert store.load_broker_account(account_id).allow_live is False


def test_set_allow_live_unknown_account(tmp_path: Path) -> None:
    service, _store = _make_service(tmp_path)
    with pytest.raises(BrokerAccountCreationError):
        service.set_allow_live(account_id=uuid4(), allow_live=True)


def test_default_guardian_and_allow_live_after_create(tmp_path: Path) -> None:
    service, _store = _make_service(tmp_path)
    account_id = _create(service)
    accounts = list(service.list_broker_accounts())
    matching = [a for a in accounts if a.id == account_id]
    assert len(matching) == 1
    assert matching[0].guardian_deployment_id is None
    assert matching[0].allow_live is False

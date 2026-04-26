"""Pin contracts for the encrypted broker credential store.

Per the production-grade principles (no temporary paths, real persistence,
real concurrency safety): these tests assert AES-GCM correctness, atomic
file writes, schema-version enforcement, and the production fail-closed
master-key rule.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from uuid import uuid4

import pytest

from backend.app.broker_accounts.credential_store import (
    CREDENTIAL_KEY_ENV_VAR,
    CredentialStoreError,
    BrokerCredentialStore,
    ENVIRONMENT_ENV_VAR,
)


def _make_master_key() -> bytes:
    return base64.b64decode("0" * 43 + "=")  # 32 zero bytes (deterministic test key)


def test_roundtrip_put_get(tmp_path: Path) -> None:
    store = BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_make_master_key())
    aid = uuid4()
    store.put(aid, api_key="PKsample", api_secret="abcdefghijkl")
    assert store.has(aid)
    api_key, api_secret = store.get(aid)
    assert api_key == "PKsample"
    assert api_secret == "abcdefghijkl"


def test_get_unknown_account_raises(tmp_path: Path) -> None:
    store = BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_make_master_key())
    with pytest.raises(CredentialStoreError, match="no stored credentials"):
        store.get(uuid4())


def test_persistence_survives_reload(tmp_path: Path) -> None:
    path = tmp_path / "creds.enc"
    key = _make_master_key()
    aid = uuid4()
    BrokerCredentialStore(store_path=path, master_key=key).put(aid, api_key="K1", api_secret="S1secret")
    # New process, same file + key.
    reopened = BrokerCredentialStore(store_path=path, master_key=key)
    assert reopened.get(aid) == ("K1", "S1secret")


def test_wrong_master_key_fails_decryption(tmp_path: Path) -> None:
    path = tmp_path / "creds.enc"
    aid = uuid4()
    BrokerCredentialStore(store_path=path, master_key=_make_master_key()).put(
        aid, api_key="K1", api_secret="S1secret"
    )
    other_key = base64.b64decode("1" * 43 + "=")
    with pytest.raises(CredentialStoreError, match="wrong master key|tampering"):
        BrokerCredentialStore(store_path=path, master_key=other_key).get(aid)


def test_associated_data_binding_prevents_swap(tmp_path: Path) -> None:
    """Swapping ciphertexts between two account_ids must fail the AES-GCM tag."""
    store = BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_make_master_key())
    a, b = uuid4(), uuid4()
    store.put(a, api_key="Ka", api_secret="Sa1234567890")
    store.put(b, api_key="Kb", api_secret="Sb1234567890")
    # Reach into the on-disk file and swap the ciphertexts between a and b.
    import json
    raw = json.loads((tmp_path / "creds.enc").read_text(encoding="utf-8"))
    raw["credentials"][str(a)], raw["credentials"][str(b)] = (
        raw["credentials"][str(b)],
        raw["credentials"][str(a)],
    )
    (tmp_path / "creds.enc").write_text(json.dumps(raw), encoding="utf-8")
    swapped = BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_make_master_key())
    with pytest.raises(CredentialStoreError, match="wrong master key|tampering"):
        swapped.get(a)


def test_delete_removes_entry(tmp_path: Path) -> None:
    store = BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_make_master_key())
    aid = uuid4()
    store.put(aid, api_key="K", api_secret="Spadding")
    store.delete(aid)
    assert not store.has(aid)
    with pytest.raises(CredentialStoreError):
        store.get(aid)


def test_account_ids_lists_known_accounts(tmp_path: Path) -> None:
    store = BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_make_master_key())
    a, b = uuid4(), uuid4()
    store.put(a, api_key="Ka", api_secret="Sa1234567890")
    store.put(b, api_key="Kb", api_secret="Sb1234567890")
    ids = set(store.account_ids())
    assert {a, b} == ids


def test_put_rejects_empty_credentials(tmp_path: Path) -> None:
    store = BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_make_master_key())
    with pytest.raises(CredentialStoreError, match="non-empty"):
        store.put(uuid4(), api_key="", api_secret="x" * 12)
    with pytest.raises(CredentialStoreError, match="non-empty"):
        store.put(uuid4(), api_key="K", api_secret="")


def test_schema_version_too_new_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "creds.enc"
    path.write_text('{"schema_version": 999, "credentials": {}}', encoding="utf-8")
    with pytest.raises(CredentialStoreError, match="schema_version=999"):
        BrokerCredentialStore(store_path=path, master_key=_make_master_key())


def test_corrupt_json_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "creds.enc"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(CredentialStoreError, match="not valid JSON"):
        BrokerCredentialStore(store_path=path, master_key=_make_master_key())


def test_master_key_must_be_32_bytes(tmp_path: Path) -> None:
    with pytest.raises(CredentialStoreError, match="32 bytes"):
        BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=b"too short")


def test_production_requires_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "production")
    monkeypatch.delenv(CREDENTIAL_KEY_ENV_VAR, raising=False)
    with pytest.raises(CredentialStoreError, match="required in production"):
        BrokerCredentialStore(store_path=tmp_path / "creds.enc")


def test_production_with_invalid_env_var_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "prod")
    monkeypatch.setenv(CREDENTIAL_KEY_ENV_VAR, "not-base64!!!")
    with pytest.raises(CredentialStoreError, match="not valid base64"):
        BrokerCredentialStore(store_path=tmp_path / "creds.enc")


def test_production_with_wrong_length_env_var_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "live")
    monkeypatch.setenv(CREDENTIAL_KEY_ENV_VAR, base64.b64encode(b"too-short").decode("ascii"))
    with pytest.raises(CredentialStoreError, match="must decode to 32 bytes"):
        BrokerCredentialStore(store_path=tmp_path / "creds.enc")


def test_dev_creates_and_reuses_key_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CREDENTIAL_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "dev")
    store_path = tmp_path / "creds.enc"
    first = BrokerCredentialStore(store_path=store_path)
    aid = uuid4()
    first.put(aid, api_key="K1", api_secret="S1secretvalue")
    key_file = tmp_path / "utos.master.key"
    assert key_file.exists()
    # A second store using the same dir reuses the same key and decrypts.
    second = BrokerCredentialStore(store_path=store_path)
    assert second.get(aid) == ("K1", "S1secretvalue")


def test_dev_key_file_with_bad_contents_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CREDENTIAL_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(ENVIRONMENT_ENV_VAR, "dev")
    (tmp_path / "utos.master.key").write_text("not base64", encoding="utf-8")
    with pytest.raises(CredentialStoreError, match="not valid base64"):
        BrokerCredentialStore(store_path=tmp_path / "creds.enc")


def test_concurrent_puts_are_serialized(tmp_path: Path) -> None:
    """Hammer the store with concurrent writes; final state must be consistent
    (every account_id present, every entry decryptable)."""
    import threading

    store = BrokerCredentialStore(store_path=tmp_path / "creds.enc", master_key=_make_master_key())
    accounts = [uuid4() for _ in range(16)]

    def worker(account_id, key, secret):
        store.put(account_id, api_key=key, api_secret=secret)

    threads = [
        threading.Thread(target=worker, args=(aid, f"K{i}", f"S{i}padding"))
        for i, aid in enumerate(accounts)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i, aid in enumerate(accounts):
        api_key, api_secret = store.get(aid)
        assert api_key == f"K{i}"
        assert api_secret == f"S{i}padding"

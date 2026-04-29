"""Encrypted-at-rest store for broker credentials.

The system stores per-account ``api_key`` / ``api_secret`` so the runtime
can make broker calls for any registered account, not just the one whose
keys happen to be in process env. Secrets are AES-GCM authenticated-
encrypted with a master key resolved at startup.

Master key resolution (``_resolve_master_key``):
- ``UTOS_CREDENTIAL_KEY`` env var, base64-encoded 32 bytes — wins when set.
- In production (``UTOS_ENVIRONMENT`` ∈ {production, prod, live}) the env
  var is required; missing or malformed → ``CredentialStoreError`` at
  startup. No silent fallback.
- In dev/test, a per-install key is generated once at
  ``<runtime_db_dir>/utos.master.key`` (``0600`` on POSIX) and reused on
  subsequent boots. The key file is treated as a local secret.

File layout (``broker_credentials.enc``):
    {
      "schema_version": 1,
      "credentials": {
        "<account_uuid>": {
          "nonce_b64": "...",
          "ciphertext_b64": "...",   # encrypts a JSON blob {api_key, api_secret}
          "updated_at": "..."
        },
        ...
      }
    }

Atomic writes via ``write_text_atomic`` (tmp + os.replace). Each record's
nonce is freshly random so re-encrypting one account doesn't leak
ordering or reuse.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


CREDENTIAL_STORE_SCHEMA_VERSION = 1
_KEY_BYTES = 32  # AES-256-GCM
_NONCE_BYTES = 12
_PRODUCTION_ENVIRONMENTS = {"production", "prod", "live"}


class CredentialStoreError(RuntimeError):
    """Raised when the credential store cannot operate safely."""


class _CredentialEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    nonce_b64: str
    ciphertext_b64: str
    updated_at: datetime


class _CredentialFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    schema_version: int = CREDENTIAL_STORE_SCHEMA_VERSION
    credentials: dict[str, _CredentialEntry] = Field(default_factory=dict)


class BrokerCredentialStore:
    """Encrypted credential store keyed by ``account_id``.

    Designed for the operator's directive: per-account credentials persist
    across restarts so the shared runtime can make calls for any account
    without env-var fallback. Per the production-grade principles:
    ``schema_version`` carries the file's shape; atomic writes; no silent
    failure modes.
    """

    def __init__(
        self,
        *,
        store_path: str | Path,
        master_key: bytes | None = None,
    ) -> None:
        self._store_path = Path(store_path)
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        self._master_key = master_key if master_key is not None else _resolve_master_key(self._store_path.parent)
        if len(self._master_key) != _KEY_BYTES:
            raise CredentialStoreError(
                f"master key must be {_KEY_BYTES} bytes (got {len(self._master_key)})"
            )
        self._aesgcm = AESGCM(self._master_key)
        self._lock = threading.Lock()
        self._file = self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, account_id: UUID, *, api_key: str, api_secret: str) -> None:
        """Persist ``(api_key, api_secret)`` for ``account_id``.

        Replaces any existing entry. Generates a fresh random nonce so
        re-storing the same secrets doesn't reuse a nonce — required for
        AES-GCM safety.
        """
        if not api_key or not api_secret:
            raise CredentialStoreError("api_key and api_secret are required and must be non-empty")
        plaintext = json.dumps(
            {"api_key": api_key, "api_secret": api_secret},
            separators=(",", ":"),
        ).encode("utf-8")
        nonce = secrets.token_bytes(_NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext, _associated_data(account_id))
        entry = _CredentialEntry(
            nonce_b64=base64.b64encode(nonce).decode("ascii"),
            ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
            updated_at=datetime.now(timezone.utc),
        )
        with self._lock:
            credentials = dict(self._file.credentials)
            credentials[str(account_id)] = entry
            self._file = self._file.model_copy(update={"credentials": credentials})
            self._persist_locked()

    def get(self, account_id: UUID) -> tuple[str, str]:
        """Return ``(api_key, api_secret)`` for ``account_id``.

        Raises ``CredentialStoreError`` if no entry exists or decryption
        fails (corruption / wrong master key / tampering). The runtime
        treats this as a hard failure for the affected account; the
        operator must re-enter credentials through the unified
        replace-credentials surface.
        """
        with self._lock:
            entry = self._file.credentials.get(str(account_id))
        if entry is None:
            raise CredentialStoreError(f"no stored credentials for account {account_id}")
        nonce = base64.b64decode(entry.nonce_b64)
        ciphertext = base64.b64decode(entry.ciphertext_b64)
        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, _associated_data(account_id))
        except InvalidTag as exc:
            raise CredentialStoreError(
                f"credential decryption failed for account {account_id} — wrong master key or tampering"
            ) from exc
        try:
            payload = json.loads(plaintext.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise CredentialStoreError(
                f"credential blob for account {account_id} is corrupt"
            ) from exc
        api_key = payload.get("api_key")
        api_secret = payload.get("api_secret")
        if not api_key or not api_secret:
            raise CredentialStoreError(
                f"credential blob for account {account_id} missing api_key / api_secret"
            )
        return api_key, api_secret

    def has(self, account_id: UUID) -> bool:
        with self._lock:
            return str(account_id) in self._file.credentials

    def delete(self, account_id: UUID) -> None:
        with self._lock:
            credentials = dict(self._file.credentials)
            if str(account_id) not in credentials:
                return
            credentials.pop(str(account_id))
            self._file = self._file.model_copy(update={"credentials": credentials})
            self._persist_locked()

    def account_ids(self) -> tuple[UUID, ...]:
        with self._lock:
            return tuple(UUID(key) for key in self._file.credentials)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> _CredentialFile:
        if not self._store_path.exists():
            return _CredentialFile()
        raw = self._store_path.read_text(encoding="utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CredentialStoreError(
                f"credential store at {self._store_path} is not valid JSON: {exc}"
            ) from exc
        version = payload.get("schema_version", 0)
        if version > CREDENTIAL_STORE_SCHEMA_VERSION:
            raise CredentialStoreError(
                f"credential store on disk is schema_version={version}, but this binary "
                f"only understands up to {CREDENTIAL_STORE_SCHEMA_VERSION}"
            )
        try:
            return _CredentialFile.model_validate(payload)
        except Exception as exc:  # noqa: BLE001 - pydantic validation errors
            raise CredentialStoreError(
                f"credential store at {self._store_path} could not be parsed: {exc}"
            ) from exc

    def _persist_locked(self) -> None:
        from backend.app.persistence import write_text_atomic

        write_text_atomic(self._store_path, self._file.model_dump_json(indent=2))


def _associated_data(account_id: UUID) -> bytes:
    """Bind ciphertext to the account_id so swapping ciphertexts between
    accounts fails the AES-GCM tag check.
    """
    return f"utos.broker.credentials.v1:{account_id}".encode("utf-8")


# ---------------------------------------------------------------------------
# Master key resolution
# ---------------------------------------------------------------------------


CREDENTIAL_KEY_ENV_VAR = "UTOS_CREDENTIAL_KEY"
ENVIRONMENT_ENV_VAR = "UTOS_ENVIRONMENT"
DEV_KEY_FILENAME = "utos.master.key"


def _resolve_master_key(runtime_dir: Path) -> bytes:
    """Resolve the master key per the production-grade contract.

    Priority:
      1. ``UTOS_CREDENTIAL_KEY`` env var (base64). Always wins.
      2. In production (``UTOS_ENVIRONMENT`` ∈ {production, prod, live}),
         missing env is a hard error.
      3. In dev/test, generate-or-read a key file at
         ``<runtime_dir>/utos.master.key`` (``0600`` perms). Subsequent
         boots reuse it. The file is the local-install secret.
    """
    raw = os.getenv(CREDENTIAL_KEY_ENV_VAR)
    if raw:
        try:
            decoded = base64.b64decode(raw, validate=True)
        except Exception as exc:  # noqa: BLE001 - any decode error is fatal
            raise CredentialStoreError(
                f"{CREDENTIAL_KEY_ENV_VAR} is not valid base64: {exc}"
            ) from exc
        if len(decoded) != _KEY_BYTES:
            raise CredentialStoreError(
                f"{CREDENTIAL_KEY_ENV_VAR} must decode to {_KEY_BYTES} bytes "
                f"(got {len(decoded)})"
            )
        return decoded

    environment = (os.getenv(ENVIRONMENT_ENV_VAR) or "").strip().lower()
    if environment in _PRODUCTION_ENVIRONMENTS:
        raise CredentialStoreError(
            f"{CREDENTIAL_KEY_ENV_VAR} is required in production "
            f"(UTOS_ENVIRONMENT={environment!r})"
        )

    return _read_or_create_dev_key(runtime_dir / DEV_KEY_FILENAME)


def _read_or_create_dev_key(key_path: Path) -> bytes:
    if key_path.exists():
        raw = key_path.read_text(encoding="utf-8").strip()
        try:
            decoded = base64.b64decode(raw, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise CredentialStoreError(
                f"dev key file at {key_path} is not valid base64: {exc}. "
                "Delete it to regenerate (will invalidate stored credentials)."
            ) from exc
        if len(decoded) != _KEY_BYTES:
            raise CredentialStoreError(
                f"dev key file at {key_path} has wrong length {len(decoded)}; "
                "delete it to regenerate."
            )
        return decoded

    key = secrets.token_bytes(_KEY_BYTES)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(base64.b64encode(key).decode("ascii"), encoding="utf-8")
    try:
        os.chmod(key_path, 0o600)
    except (OSError, NotImplementedError):
        # Windows may reject chmod on certain filesystems; leave default ACL.
        logger.warning(
            "could not chmod %s to 0600; ensure filesystem ACL restricts access",
            key_path,
        )
    logger.warning(
        "generated dev master key at %s — keep this file private; rotating it invalidates stored credentials",
        key_path,
    )
    return key


def create_broker_credential_store_from_environment() -> BrokerCredentialStore:
    """Build the credential store using the configured runtime db dir."""
    from backend.app.config.runtime_paths import get_runtime_db_path

    runtime_dir = get_runtime_db_path().parent
    return BrokerCredentialStore(store_path=runtime_dir / "broker_credentials.enc")

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from sqlite3 import IntegrityError
from uuid import UUID
from uuid import uuid4

from backend.app.broker_accounts.models import BrokerAccount, BrokerAccountValidationStatus
from backend.app.brokers import AlpacaBrokerAdapter, BrokerSync
from backend.app.domain import TradingMode
from backend.app.domain._base import utc_now
from backend.app.orders import OrderLedger
from backend.app.persistence import SQLiteRuntimeStore


class BrokerAccountCreationError(RuntimeError):
    """Operator-readable broker account setup failure."""


@dataclass(frozen=True)
class BrokerAccountCreationResult:
    account: BrokerAccount
    already_exists: bool = False


@dataclass(frozen=True)
class CredentialReferenceStore:
    """Create a non-secret credential reference for a validated broker account."""

    def store_alpaca_paper_credentials(self, *, account_id, api_key: str, api_secret: str) -> str:
        _ = api_secret
        fingerprint = sha256(api_key.encode("utf-8")).hexdigest()[:12]
        return f"alpaca-paper:{account_id}:{fingerprint}"


class BrokerAccountService:
    def __init__(
        self,
        *,
        runtime_store: SQLiteRuntimeStore,
        adapter_factory=AlpacaBrokerAdapter,
        credential_store: CredentialReferenceStore | None = None,
        order_ledger: OrderLedger | None = None,
    ) -> None:
        self._runtime_store = runtime_store
        self._adapter_factory = adapter_factory
        self._credential_store = credential_store or CredentialReferenceStore()
        self._order_ledger = order_ledger or OrderLedger()

    def create_alpaca_paper_account(self, *, display_name: str, api_key: str, api_secret: str) -> BrokerAccountCreationResult:
        validation_account_id = uuid4()
        mode = TradingMode.BROKER_PAPER
        try:
            adapter = self._adapter_factory(mode=mode, api_key=api_key, secret_key=api_secret, load_env=False)
            validation_snapshot = adapter.get_account_snapshot(validation_account_id)
            external_account_id = _external_account_id_from_snapshot(validation_snapshot)
            existing = self._load_existing_alpaca_paper_account(external_account_id)
            account_id = existing.id if existing is not None else validation_account_id

            adapter.get_positions(account_id)
            adapter.list_open_orders(account_id)
            broker_sync = BrokerSync(
                ledger=self._order_ledger,
                adapter=adapter,
                runtime_store=self._runtime_store,
                provider="alpaca",
            )
            snapshot = broker_sync.sync_account(account_id)
            broker_sync.sync_positions(account_id)
            broker_sync.sync_open_orders(account_id)
            freshness = broker_sync.record_sync_freshness(snapshot)
            credentials_ref = self._credential_store.store_alpaca_paper_credentials(
                account_id=account_id,
                api_key=api_key,
                api_secret=api_secret,
            )
            if existing is not None:
                account = existing.model_copy(
                    update={
                        "credentials_ref": credentials_ref,
                        "validation_status": BrokerAccountValidationStatus.VALID,
                        "last_account_snapshot": snapshot,
                        "broker_sync_freshness": freshness,
                    }
                )
                return BrokerAccountCreationResult(
                    account=self._runtime_store.save_broker_account(account),
                    already_exists=True,
                )

            account = self._runtime_store.save_broker_account(
                BrokerAccount(
                    id=account_id,
                    display_name=display_name,
                    provider="alpaca",
                    mode=mode,
                    external_account_id=external_account_id,
                    credentials_ref=credentials_ref,
                    validation_status=BrokerAccountValidationStatus.VALID,
                    last_account_snapshot=snapshot,
                    broker_sync_freshness=freshness,
                    created_at=utc_now(),
                )
            )
            return BrokerAccountCreationResult(account=account, already_exists=False)
        except BrokerAccountCreationError:
            raise
        except IntegrityError as exc:
            raise BrokerAccountCreationError("Alpaca paper account is already registered") from exc
        except Exception as exc:  # noqa: BLE001 - keep route errors operator-readable.
            raise BrokerAccountCreationError(f"Unable to validate Alpaca paper account: {exc}") from exc

    def _load_existing_alpaca_paper_account(self, external_account_id: str) -> BrokerAccount | None:
        try:
            return self._runtime_store.load_broker_account_by_external_identity(
                provider="alpaca",
                mode=TradingMode.BROKER_PAPER.value,
                external_account_id=external_account_id,
            )
        except KeyError:
            return None


def _external_account_id_from_snapshot(snapshot: object) -> str:
    external_account_id = getattr(snapshot, "external_account_id", None)
    if external_account_id:
        return str(external_account_id)
    raw_account_id = getattr(snapshot, "account_id", None)
    if isinstance(raw_account_id, UUID):
        raise BrokerAccountCreationError("Alpaca account response did not include a stable external account id")
    if raw_account_id:
        return str(raw_account_id)
    raise BrokerAccountCreationError("Alpaca account response did not include an account id")

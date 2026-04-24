from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
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

    def create_alpaca_paper_account(self, *, display_name: str, api_key: str, api_secret: str) -> BrokerAccount:
        account_id = uuid4()
        mode = TradingMode.BROKER_PAPER
        try:
            adapter = self._adapter_factory(mode=mode, api_key=api_key, secret_key=api_secret, load_env=False)
            adapter.get_account_snapshot(account_id)
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
            account = BrokerAccount(
                id=account_id,
                display_name=display_name,
                provider="alpaca",
                mode=mode,
                credentials_ref=credentials_ref,
                validation_status=BrokerAccountValidationStatus.VALID,
                last_account_snapshot=snapshot,
                broker_sync_freshness=freshness,
                created_at=utc_now(),
            )
            return self._runtime_store.save_broker_account(account)
        except Exception as exc:  # noqa: BLE001 - keep route errors operator-readable.
            raise BrokerAccountCreationError(f"Unable to validate Alpaca paper account: {exc}") from exc

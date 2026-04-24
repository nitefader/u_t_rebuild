from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from sqlite3 import IntegrityError
from uuid import UUID
from uuid import uuid4

from backend.app.broker_accounts.models import (
    BrokerAccount,
    BrokerAccountCredentialUpdateResponse,
    BrokerAccountCredentialValidationStatus,
    BrokerAccountDeletionResponse,
    BrokerAccountDeletionStatus,
    BrokerAccountValidationStatus,
)
from backend.app.brokers import AlpacaBrokerAdapter, BrokerSync
from backend.app.brokers.models import BrokerSyncState
from backend.app.control_plane import ControlPlane
from backend.app.domain import TradingMode
from backend.app.domain._base import utc_now
from backend.app.orders import InternalOrderStatus
from backend.app.orders import OrderLedger
from backend.app.persistence import SQLiteRuntimeStore
from backend.app.runtime import RuntimeStatus


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

    def replace_alpaca_paper_credentials(
        self,
        *,
        account_id: UUID,
        api_key: str,
        api_secret: str,
        control_plane=None,
    ) -> BrokerAccountCredentialUpdateResponse:
        account = self._runtime_store.load_broker_account(account_id)
        if account.mode != TradingMode.BROKER_PAPER or account.provider != "alpaca":
            return BrokerAccountCredentialUpdateResponse(
                account=account,
                validation_status=BrokerAccountCredentialValidationStatus.MODE_MISMATCH,
                message="credential replacement is supported only for Alpaca paper accounts",
            )
        if _masked_or_missing(api_key) or _masked_or_missing(api_secret):
            return BrokerAccountCredentialUpdateResponse(
                account=account,
                validation_status=BrokerAccountCredentialValidationStatus.MISSING_CREDENTIALS,
                message="new unmasked API key and secret are required",
            )
        blockers = self._active_runtime_blockers(account_id=account_id, control_plane=control_plane)
        if blockers:
            raise BrokerAccountCreationError(f"Account must be paused before credential replacement: {', '.join(blockers)}")
        try:
            adapter = self._adapter_factory(mode=TradingMode.BROKER_PAPER, api_key=api_key, secret_key=api_secret, load_env=False)
            snapshot = adapter.get_account_snapshot(account_id)
        except ConnectionError:
            return self._mark_account_invalid(account, BrokerAccountCredentialValidationStatus.PROVIDER_UNREACHABLE, "provider unreachable")
        except Exception as exc:  # noqa: BLE001 - invalid credentials should be operator-readable.
            return self._mark_account_invalid(account, BrokerAccountCredentialValidationStatus.INVALID, f"invalid credentials: {exc}")
        if snapshot.mode is not None and snapshot.mode != TradingMode.BROKER_PAPER:
            return self._mark_account_invalid(account, BrokerAccountCredentialValidationStatus.MODE_MISMATCH, "credentials resolved to a non-paper account")
        external_account_id = _external_account_id_from_snapshot(snapshot)
        if account.external_account_id and external_account_id != account.external_account_id:
            return self._mark_account_invalid(account, BrokerAccountCredentialValidationStatus.MODE_MISMATCH, "credentials resolved to a different Alpaca account")

        credentials_ref = self._credential_store.store_alpaca_paper_credentials(
            account_id=account_id,
            api_key=api_key,
            api_secret=api_secret,
        )
        stale_sync = BrokerSyncState(
            account_id=account_id,
            last_sync_at=utc_now(),
            last_successful_sync_at=None,
            is_stale=True,
            stale_reason="credentials_replaced_requires_broker_sync",
        )
        updated = self._runtime_store.save_broker_account(
            account.model_copy(
                update={
                    "credentials_ref": credentials_ref,
                    "validation_status": BrokerAccountValidationStatus.VALID,
                    "external_account_id": external_account_id,
                    "last_account_snapshot": snapshot,
                    "broker_sync_freshness": stale_sync,
                }
            )
        )
        self._runtime_store.save_broker_sync_freshness(stale_sync)
        return BrokerAccountCredentialUpdateResponse(
            account=updated,
            validation_status=BrokerAccountCredentialValidationStatus.VALID,
            message="credentials validated; broker sync is stale until the next successful sync",
        )

    def delete_or_archive_account(
        self,
        *,
        account_id: UUID,
        confirm_display_name: str,
        confirm_mode: TradingMode,
    ) -> BrokerAccountDeletionResponse:
        account = self._runtime_store.load_broker_account(account_id)
        if confirm_display_name != account.display_name or confirm_mode != account.mode:
            return BrokerAccountDeletionResponse(
                account_id=account_id,
                status=BrokerAccountDeletionStatus.BLOCKED,
                message="confirmation did not match account display name and mode",
                blockers=("confirmation_mismatch",),
            )
        blockers = self._deletion_blockers(account)
        if blockers:
            return BrokerAccountDeletionResponse(
                account_id=account_id,
                status=BrokerAccountDeletionStatus.BLOCKED,
                message="broker account deletion is blocked",
                blockers=tuple(blockers),
            )
        if self._has_history(account_id):
            archived = self._runtime_store.save_broker_account(
                account.model_copy(
                    update={
                        "is_archived": True,
                        "archived_at": utc_now(),
                        "validation_status": BrokerAccountValidationStatus.PENDING,
                    }
                )
            )
            return BrokerAccountDeletionResponse(
                account_id=account_id,
                status=BrokerAccountDeletionStatus.ARCHIVED,
                message="broker account archived; historical references preserved",
                archived_account=archived,
            )
        self._runtime_store.delete_broker_account(account_id)
        return BrokerAccountDeletionResponse(
            account_id=account_id,
            status=BrokerAccountDeletionStatus.HARD_DELETED,
            message="broker account hard-deleted; no runtime history existed",
        )

    def _load_existing_alpaca_paper_account(self, external_account_id: str) -> BrokerAccount | None:
        try:
            return self._runtime_store.load_broker_account_by_external_identity(
                provider="alpaca",
                mode=TradingMode.BROKER_PAPER.value,
                external_account_id=external_account_id,
            )
        except KeyError:
            return None

    def _mark_account_invalid(
        self,
        account: BrokerAccount,
        status: BrokerAccountCredentialValidationStatus,
        message: str,
    ) -> BrokerAccountCredentialUpdateResponse:
        updated = self._runtime_store.save_broker_account(
            account.model_copy(update={"validation_status": BrokerAccountValidationStatus.INVALID})
        )
        return BrokerAccountCredentialUpdateResponse(account=updated, validation_status=status, message=message)

    def _active_runtime_blockers(self, *, account_id: UUID, control_plane=None) -> list[str]:
        if control_plane is None:
            control_plane = ControlPlane(state_store=self._runtime_store)
        if control_plane is not None and control_plane.is_account_paused(account_id):
            return []
        deployment_ids = {order.deployment_id for order in self._runtime_store.list_orders_by_account(account_id)}
        blockers = []
        for state in self._runtime_store.list_deployment_runtime_states():
            if state.deployment_id not in deployment_ids:
                continue
            if state.status in {RuntimeStatus.RUNNING, RuntimeStatus.DEGRADED}:
                blockers.append(f"deployment_active:{state.deployment_id}")
        return blockers

    def _deletion_blockers(self, account: BrokerAccount) -> list[str]:
        blockers: list[str] = []
        runtime_deployments = {order.deployment_id for order in self._runtime_store.list_orders_by_account(account.id)}
        for state in self._runtime_store.list_deployment_runtime_states():
            if state.deployment_id in runtime_deployments and state.status in {RuntimeStatus.RUNNING, RuntimeStatus.DEGRADED, RuntimeStatus.BLOCKED}:
                blockers.append(f"deployment_not_stopped:{state.deployment_id}")
        open_statuses = {
            InternalOrderStatus.CREATED,
            InternalOrderStatus.PENDING_SUBMISSION,
            InternalOrderStatus.SUBMITTED,
            InternalOrderStatus.ACCEPTED,
            InternalOrderStatus.PARTIALLY_FILLED,
        }
        if any(order.status in open_statuses for order in self._runtime_store.list_orders_by_account(account.id)):
            blockers.append("open_internal_orders")
        if self._runtime_store.list_broker_open_order_snapshots(account.id):
            blockers.append("open_broker_orders")
        if any(position.quantity != 0 for position in self._runtime_store.list_broker_position_snapshots(account.id)):
            blockers.append("open_positions")
        try:
            freshness = self._runtime_store.load_broker_sync_freshness(account.id)
            if freshness.is_stale:
                blockers.append("broker_sync_stale")
        except KeyError:
            blockers.append("broker_sync_unknown")
        return blockers

    def _has_history(self, account_id: UUID) -> bool:
        return any(
            (
                self._runtime_store.list_orders_by_account(account_id),
                tuple(trade for trade in self._runtime_store.list_trades() if getattr(trade, "account_id", None) == account_id),
                tuple(mapping for mapping in self._runtime_store.list_broker_order_mappings() if mapping.account_id == account_id),
            )
        )


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


def _masked_or_missing(value: str) -> bool:
    stripped = (value or "").strip()
    if not stripped:
        return True
    return set(stripped) <= {"*", "x", "X", "-", "_", " "}

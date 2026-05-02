"""Unified broker-account service.

Per the production-grade principles (no fork between paper and live, real
persisted credentials, no env fallback): one ``create_account`` method,
one ``replace_credentials`` method, both parametrized by ``mode``. The
adapter the service builds for validation is constructed with explicit
credentials passed by the operator; secrets are persisted through the
encrypted ``BrokerCredentialStore``.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import logging
from sqlite3 import IntegrityError
from typing import Callable
from uuid import UUID, uuid4

from backend.app.broker_accounts.credential_store import (
    BrokerCredentialStore,
    CredentialStoreError,
)
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


SUPPORTED_PROVIDERS = {"alpaca"}
logger = logging.getLogger(__name__)


class BrokerAccountCreationError(RuntimeError):
    """Operator-readable broker account setup failure."""


@dataclass(frozen=True)
class BrokerAccountCreationResult:
    account: BrokerAccount
    already_exists: bool = False


def _credential_fingerprint(provider: str, mode: TradingMode, account_id: UUID, api_key: str) -> str:
    """Build a stable, non-secret display reference for a credential.

    The reference is ``<provider>-<mode>:<account_id>:<fingerprint>`` where
    fingerprint is the first 12 hex of ``sha256(api_key)``. The actual
    secrets live in ``BrokerCredentialStore`` (AES-GCM); this string is
    only for human-readable identification on the account record.
    """
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()[:12]
    return f"{provider}-{mode.value.lower()}:{account_id}:{fingerprint}"


class BrokerAccountService:
    """Unified service for paper + live, all providers."""

    def __init__(
        self,
        *,
        runtime_store: SQLiteRuntimeStore,
        credential_store: BrokerCredentialStore,
        adapter_factory: Callable[..., AlpacaBrokerAdapter] = AlpacaBrokerAdapter,
        order_ledger: OrderLedger | None = None,
    ) -> None:
        self._runtime_store = runtime_store
        self._credential_store = credential_store
        self._adapter_factory = adapter_factory
        self._order_ledger = order_ledger or OrderLedger()

    # ------------------------------------------------------------------
    # Listing — exposed so routes can list accounts without extra plumbing
    # ------------------------------------------------------------------

    def list_broker_accounts(self) -> tuple[BrokerAccount, ...]:
        accounts = tuple(self._runtime_store.list_broker_accounts())
        # Reflect needs_credentials based on the live state of the
        # credential store. Records that pre-date the encrypted store
        # are flagged so the UI can prompt the operator to re-enter.
        return tuple(self._project_account_list_record(account) for account in accounts)

    def _project_account_list_record(self, account: BrokerAccount) -> BrokerAccount:
        update = {"needs_credentials": not self._credential_store.has(account.id)}
        try:
            update["last_account_snapshot"] = self._runtime_store.load_broker_account_snapshot(account.id)
        except KeyError:
            pass
        try:
            update["broker_sync_freshness"] = self._runtime_store.load_broker_sync_freshness(account.id)
        except KeyError:
            pass
        return account.model_copy(update=update)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create_account(
        self,
        *,
        display_name: str,
        provider: str,
        mode: TradingMode,
        api_key: str,
        api_secret: str,
    ) -> BrokerAccountCreationResult:
        if provider not in SUPPORTED_PROVIDERS:
            raise BrokerAccountCreationError(f"unsupported provider: {provider}")
        if mode not in (TradingMode.BROKER_PAPER, TradingMode.BROKER_LIVE):
            raise BrokerAccountCreationError(f"unsupported broker mode: {mode}")

        validation_account_id = uuid4()
        try:
            adapter = self._adapter_factory(mode=mode, api_key=api_key, secret_key=api_secret)
            validation_snapshot = adapter.get_account_snapshot(validation_account_id)
            external_account_id = _external_account_id_from_snapshot(validation_snapshot)
            existing = self._load_existing_account(provider=provider, mode=mode, external_account_id=external_account_id)
            account_id = existing.id if existing is not None else validation_account_id

            adapter.get_positions(account_id)
            adapter.list_open_orders(account_id)
            broker_sync = BrokerSync(
                ledger=self._order_ledger,
                adapter=adapter,
                runtime_store=self._runtime_store,
                provider=provider,
            )
            snapshot = broker_sync.sync_account(account_id)
            broker_sync.sync_positions(account_id)
            broker_sync.sync_open_orders(account_id)
            freshness = broker_sync.record_sync_freshness(snapshot)

            # Persist secrets BEFORE writing the account row so a power
            # failure between the two leaves the operator with stored
            # secrets and no account (recoverable on re-create) rather
            # than an account with no recoverable credentials.
            self._credential_store.put(account_id, api_key=api_key, api_secret=api_secret)
            credentials_ref = _credential_fingerprint(provider, mode, account_id, api_key)

            if existing is not None:
                account = existing.model_copy(
                    update={
                        "credentials_ref": credentials_ref,
                        "needs_credentials": False,
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
                    provider=provider,
                    mode=mode,
                    external_account_id=external_account_id,
                    credentials_ref=credentials_ref,
                    needs_credentials=False,
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
            raise BrokerAccountCreationError(
                f"{provider} {mode.value} account is already registered"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - keep route errors operator-readable.
            raise BrokerAccountCreationError(
                f"Unable to validate {provider} {mode.value} account: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Update operator-visible metadata
    # ------------------------------------------------------------------

    def update_account_details(self, *, account_id: UUID, display_name: str) -> BrokerAccount:
        try:
            account = self._runtime_store.load_broker_account(account_id)
        except KeyError as exc:
            raise BrokerAccountCreationError("unknown broker account") from exc
        new_name = display_name.strip()
        if not new_name:
            raise BrokerAccountCreationError("display_name cannot be empty")
        return self._runtime_store.save_broker_account(account.model_copy(update={"display_name": new_name}))

    def set_guardian_deployment(
        self,
        *,
        account_id: UUID,
        guardian_deployment_id: UUID | None,
    ) -> BrokerAccount:
        """Assign or clear an Account's Guardian Deployment (M11).

        Pre-authorizes one Deployment to adopt orphaned positions or
        positions whose owner Deployment is unhealthy AND unprotected.
        Adoption is one-way; clearing the Guardian does NOT release any
        positions already adopted (their lineage tags
        ``adopted_by_guardian`` until the operator explicitly transfers
        them back via Operations).
        """
        try:
            account = self._runtime_store.load_broker_account(account_id)
        except KeyError as exc:
            raise BrokerAccountCreationError("unknown broker account") from exc
        if guardian_deployment_id is not None and guardian_deployment_id == account.id:
            # Defensive — operator typed the Account id by mistake.
            raise BrokerAccountCreationError(
                "guardian_deployment_id must be a Deployment id, not an Account id"
            )
        return self._runtime_store.save_broker_account(
            account.model_copy(update={"guardian_deployment_id": guardian_deployment_id})
        )

    def set_allow_live(
        self,
        *,
        account_id: UUID,
        allow_live: bool,
    ) -> BrokerAccount:
        """Toggle the per-Account live-trading allow flag (M10).

        Combined with the env ``TRADING_LIVE_ENABLED=true`` gate at
        ``AlpacaBrokerCapabilities`` init time. Both must be true before
        a live broker adapter can construct.
        """
        try:
            account = self._runtime_store.load_broker_account(account_id)
        except KeyError as exc:
            raise BrokerAccountCreationError("unknown broker account") from exc
        return self._runtime_store.save_broker_account(
            account.model_copy(update={"allow_live": bool(allow_live)})
        )

    # ------------------------------------------------------------------
    # Replace credentials
    # ------------------------------------------------------------------

    def replace_credentials(
        self,
        *,
        account_id: UUID,
        api_key: str,
        api_secret: str,
        control_plane=None,
    ) -> BrokerAccountCredentialUpdateResponse:
        account = self._runtime_store.load_broker_account(account_id)
        if account.provider not in SUPPORTED_PROVIDERS:
            return BrokerAccountCredentialUpdateResponse(
                account=account,
                validation_status=BrokerAccountCredentialValidationStatus.MODE_MISMATCH,
                message=f"credential replacement not supported for provider {account.provider}",
            )
        if _masked_or_missing(api_key) or _masked_or_missing(api_secret):
            return BrokerAccountCredentialUpdateResponse(
                account=account,
                validation_status=BrokerAccountCredentialValidationStatus.MISSING_CREDENTIALS,
                message="new unmasked API key and secret are required",
            )
        blockers = self._active_runtime_blockers(account_id=account_id, control_plane=control_plane)
        if blockers:
            raise BrokerAccountCreationError(
                f"Account must be paused before credential replacement: {', '.join(blockers)}"
            )
        try:
            adapter = self._adapter_factory(mode=account.mode, api_key=api_key, secret_key=api_secret)
            snapshot = adapter.get_account_snapshot(account_id)
        except ConnectionError:
            return self._mark_account_invalid(
                account, BrokerAccountCredentialValidationStatus.PROVIDER_UNREACHABLE, "provider unreachable"
            )
        except Exception as exc:  # noqa: BLE001 - invalid credentials should be operator-readable.
            return self._mark_account_invalid(
                account, BrokerAccountCredentialValidationStatus.INVALID, f"invalid credentials: {exc}"
            )
        if snapshot.mode is not None and snapshot.mode != account.mode:
            return self._mark_account_invalid(
                account,
                BrokerAccountCredentialValidationStatus.MODE_MISMATCH,
                f"credentials resolved to mode {snapshot.mode.value} (expected {account.mode.value})",
            )
        external_account_id = _external_account_id_from_snapshot(snapshot)
        if account.external_account_id and external_account_id != account.external_account_id:
            return self._mark_account_invalid(
                account,
                BrokerAccountCredentialValidationStatus.MODE_MISMATCH,
                f"credentials resolved to a different {account.provider} account",
            )

        # Persist new secrets first; only then update the account row.
        self._credential_store.put(account_id, api_key=api_key, api_secret=api_secret)
        credentials_ref = _credential_fingerprint(account.provider, account.mode, account_id, api_key)
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
                    "needs_credentials": False,
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

    # ------------------------------------------------------------------
    # Credential resolution (used by composition root)
    # ------------------------------------------------------------------

    def get_credentials(self, account_id: UUID) -> tuple[str, str]:
        """Return ``(api_key, api_secret)`` for ``account_id``.

        Raises ``CredentialStoreError`` if the account has no stored
        credentials. Callers (composition root, manual-trade route)
        must surface that to the operator as "needs credentials" and
        block trading.
        """
        return self._credential_store.get(account_id)

    # ------------------------------------------------------------------
    # Delete / archive (unchanged from before)
    # ------------------------------------------------------------------

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
            # Hard-delete the secrets even on archive — archived accounts
            # cannot trade and shouldn't retain reusable credentials.
            try:
                self._credential_store.delete(account_id)
            except CredentialStoreError as exc:
                logger.warning("credential delete failed while archiving account %s: %s", account_id, exc, exc_info=True)
            return BrokerAccountDeletionResponse(
                account_id=account_id,
                status=BrokerAccountDeletionStatus.ARCHIVED,
                message="broker account archived; historical references preserved",
                archived_account=archived,
            )
        self._runtime_store.delete_broker_account(account_id)
        try:
            self._credential_store.delete(account_id)
        except CredentialStoreError as exc:
            logger.warning("credential delete failed while deleting account %s: %s", account_id, exc, exc_info=True)
        return BrokerAccountDeletionResponse(
            account_id=account_id,
            status=BrokerAccountDeletionStatus.HARD_DELETED,
            message="broker account hard-deleted; no runtime history existed",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _load_existing_account(self, *, provider: str, mode: TradingMode, external_account_id: str) -> BrokerAccount | None:
        try:
            return self._runtime_store.load_broker_account_by_external_identity(
                provider=provider,
                mode=mode.value,
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

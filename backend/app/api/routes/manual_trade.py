"""Operator-driven manual trade route.

Manual submit/cancel is nested under the BrokerAccount that owns broker
truth. The route composes OrderManager -> BrokerAdapter -> BrokerSync:
OrderManager creates internal orders, BrokerAdapter submits/cancels, and
BrokerSync writes broker truth back to the ledger.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import TYPE_CHECKING, Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from backend.app.broker_accounts.models import BrokerAccount
from backend.app.domain import CandidateSide, OrderType, TimeInForce, TradingMode
from backend.app.orders.models import (
    InternalOrder,
    InternalOrderIntent,
    InternalOrderStatus,
    OrderManagerError,
)

if TYPE_CHECKING:
    from backend.app.broker_accounts import BrokerAccountService
    from backend.app.runtime.runtime_context import ManualTradeRegistry


def get_broker_account_service() -> "BrokerAccountService":
    from backend.app.broker_accounts.runtime_service import (
        create_broker_account_service_from_environment,
    )

    return create_broker_account_service_from_environment()


def get_manual_trade_registry() -> "ManualTradeRegistry":
    from backend.app.runtime.runtime_context import manual_trade_registry

    return manual_trade_registry()


def get_runtime_store() -> Any:
    from backend.app.config.runtime_paths import get_runtime_db_path
    from backend.app.persistence import SQLiteRuntimeStore

    return SQLiteRuntimeStore(get_runtime_db_path())


def _dependency(default: object) -> object:
    return Depends(default)


router = APIRouter(prefix="/api/v1/broker-accounts", tags=["manual-trade"])

BrokerAccountServiceDependency = Annotated[Any, _dependency(get_broker_account_service)]
ManualTradeRegistryDependency = Annotated[Any, _dependency(get_manual_trade_registry)]
RuntimeStoreDependency = Annotated[Any, _dependency(get_runtime_store)]


class ManualOrderRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str = Field(min_length=1, max_length=20)
    side: CandidateSide
    qty: float = Field(gt=0, description="Order quantity in shares (must be > 0).")
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.DAY
    intent: str = Field(default="open", pattern=r"^(open|close|reduce)$")
    reason: str = Field(min_length=1, max_length=200)
    idempotency_key: str = Field(min_length=8, max_length=64)
    confirm_live: bool = False
    confirm_account_display_name: str | None = None


class ManualOrderResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    client_order_id: str
    account_id: UUID
    symbol: str
    side: CandidateSide
    quantity: float
    filled_quantity: float
    status: InternalOrderStatus
    intent: InternalOrderIntent
    submitted_at: str
    duplicate: bool = False


class CancelOrderResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: UUID
    status: InternalOrderStatus
    no_op: bool = False
    filled_quantity: float = 0.0
    message: str | None = None


class ManualOrderListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    orders: tuple[ManualOrderResponse, ...] = ()


class ManualTradeErrorDetail(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    recovery_hint: str
    fields: dict[str, object] | None = None


_ERRORS: dict[str, tuple[str, str]] = {
    "manual_trade_disabled": ("Manual trade is disabled.", "Enable manual trading before retrying."),
    "unknown_broker_account": ("Broker account was not found.", "Refresh broker accounts and pick an active account."),
    "manual_trade_blocked_live_account": ("Live account confirmation is required.", "Type the exact account display name to confirm."),
    "manual_trade_live_confirmation_name_mismatch": ("Live account confirmation did not match.", "Retry with the exact account display name."),
    "manual_trade_composition_root_not_initialized": ("Manual trade runtime is not ready.", "Verify credentials and restart or re-bootstrap broker runtime."),
    "manual_trade_broker_wiring_incomplete": ("Manual trade broker wiring is incomplete.", "Check broker credentials and runtime bootstrap logs."),
    "idempotency_key_in_flight": ("An identical order request is already in flight.", "Wait, then refresh recent orders before retrying."),
    "idempotency_key_conflict": ("Idempotency key was reused for a different request.", "Generate a new idempotency key for the changed order."),
    "broker_sync_stale": ("Broker sync is stale.", "Wait for broker sync to become fresh before opening a new order."),
    "unknown_order": ("Order was not found.", "Refresh recent orders for this account."),
    "order_account_mismatch": ("Order does not belong to this account.", "Refresh the selected account before retrying."),
    "order_already_filled": ("Order filled before it could be canceled.", "Refresh orders and positions; broker truth already shows the fill."),
    "operator_session_required": ("Operator session is required.", "Refresh the page so the client can attach its operator session id."),
    "manual_submit_failed": ("Manual submit failed.", "Review the failure and retry only after broker truth is clear."),
    "manual_cancel_failed": ("Manual cancel failed.", "Refresh recent orders and retry if the order remains cancelable."),
}


def _operator_error(
    code: str,
    *,
    status_code: int = 400,
    message: str | None = None,
    recovery_hint: str | None = None,
    fields: dict[str, object] | None = None,
) -> HTTPException:
    default_message, default_hint = _ERRORS.get(code, ("Manual trade request failed.", "Review the request and retry."))
    detail = ManualTradeErrorDetail(
        code=code,
        message=message or default_message,
        recovery_hint=recovery_hint or default_hint,
        fields=fields,
    )
    return HTTPException(status_code=status_code, detail=detail.model_dump())


def _operator_session_dependency():
    def _resolve(
        x_operator_session_id: str | None = Header(default=None, alias="X-Operator-Session-Id"),
        x_request_id: str | None = Header(default=None, alias="X-Request-Id"),
    ) -> str | None:
        return x_operator_session_id or x_request_id

    return _resolve


OperatorSessionDependency = Annotated[Any, _dependency(_operator_session_dependency())]


def _is_enabled() -> bool:
    raw = os.getenv("UTOS_MANUAL_TRADE_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _require_operator_session(operator_session_id: str | None) -> str:
    normalized = (operator_session_id or "").strip()
    if not normalized:
        raise _operator_error("operator_session_required", status_code=401)
    return normalized


def _resolve_account(account_id: UUID, service: Any) -> BrokerAccount:
    accounts: tuple[BrokerAccount, ...] = ()
    if hasattr(service, "list_broker_accounts"):
        accounts = tuple(service.list_broker_accounts())
    else:
        runtime_store = getattr(service, "_runtime_store", None)
        if runtime_store is not None and hasattr(runtime_store, "list_broker_accounts"):
            accounts = tuple(runtime_store.list_broker_accounts())
    for account in accounts:
        if account.id == account_id and not account.is_archived:
            return account
    raise _operator_error("unknown_broker_account", status_code=404, fields={"account_id": str(account_id)})


def _enforce_live_guard(account: BrokerAccount, request: ManualOrderRequest) -> None:
    if account.mode == TradingMode.BROKER_PAPER:
        return
    if not request.confirm_live:
        raise _operator_error("manual_trade_blocked_live_account", status_code=403)
    if request.confirm_account_display_name != account.display_name:
        raise _operator_error("manual_trade_live_confirmation_name_mismatch", status_code=403)


def _serialize(order: InternalOrder, *, duplicate: bool = False) -> ManualOrderResponse:
    return ManualOrderResponse(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        account_id=order.account_id,
        symbol=order.symbol,
        side=order.side,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        status=order.status,
        intent=order.intent,
        submitted_at=order.created_at.isoformat(),
        duplicate=duplicate,
    )


def _record_freshness(broker_sync_service: Any, account_id: UUID) -> None:
    record = getattr(broker_sync_service, "record_successful_poll", None)
    if record is None:
        return
    try:
        record(account_id)
    except Exception as exc:  # noqa: BLE001
        raise OrderManagerError(f"manual_trade_freshness_record_failed:{exc}") from exc


def _audit(runtime_store: Any, event_code: str, *, account_id: UUID, operator_session_id: str, **fields: object) -> None:
    order_id = fields.get("order_id")
    runtime_store.record_manual_trade_audit_event(
        event_code=event_code,
        account_id=account_id,
        operator_session_id=operator_session_id,
        order_id=order_id if isinstance(order_id, UUID) else None,
        client_order_id=str(fields["client_order_id"]) if fields.get("client_order_id") else None,
        idempotency_key=str(fields["idempotency_key"]) if fields.get("idempotency_key") else None,
        payload=fields,
    )


def _request_hash(request: ManualOrderRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"confirm_live", "confirm_account_display_name"})
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _runtime_store_from_entry(entry: dict[str, Any], fallback: Any) -> Any:
    return entry.get("runtime_store") or fallback or get_runtime_store()


@router.post("/{account_id}/orders", response_model=ManualOrderResponse)
def submit_manual_order(
    account_id: UUID,
    request: ManualOrderRequest,
    service: BrokerAccountServiceDependency,
    registry: ManualTradeRegistryDependency,
    runtime_store: RuntimeStoreDependency = None,
    operator_session_id: OperatorSessionDependency = None,
) -> ManualOrderResponse:
    operator_session_id = _require_operator_session(operator_session_id)
    if not _is_enabled():
        raise _operator_error("manual_trade_disabled", status_code=503)
    account = _resolve_account(account_id, service)
    _enforce_live_guard(account, request)

    entry = registry.get(account_id)
    if entry is None:
        raise _operator_error("manual_trade_composition_root_not_initialized", status_code=503)
    runtime_store = _runtime_store_from_entry(entry, runtime_store)
    order_manager = entry["order_manager"]
    broker_adapter = entry["broker_adapter"]
    broker_sync_service = entry["broker_sync_service"]
    broker_sync = getattr(order_manager, "_broker_sync", None)
    if broker_adapter is None or broker_sync is None:
        raise _operator_error("manual_trade_broker_wiring_incomplete", status_code=503)

    reservation = runtime_store.reserve_manual_idempotency_key(
        account_id=account_id,
        idempotency_key=request.idempotency_key,
        request_hash=_request_hash(request),
        operator_session_id=operator_session_id,
    )
    if isinstance(reservation, UUID):
        existing_order = order_manager.ledger.get(reservation)
        return _serialize(existing_order, duplicate=True)
    if reservation == "conflict":
        raise _operator_error("idempotency_key_conflict", status_code=409)
    if reservation == "in_flight":
        raise _operator_error("idempotency_key_in_flight", status_code=409)

    submitted: InternalOrder | None = None
    try:
        created = order_manager.create_manual_order(
            account_id=account_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.qty,
            intent=request.intent,
            order_type=request.order_type,
            time_in_force=request.time_in_force,
            reason=request.reason,
        )
        broker_result = broker_adapter.submit_order(created)
        submitted = broker_sync.apply_result(broker_result)
        _record_freshness(broker_sync_service, account_id)
    except OrderManagerError as exc:
        runtime_store.release_manual_idempotency_key(account_id=account_id, idempotency_key=request.idempotency_key)
        code = "broker_sync_stale" if "broker_sync_stale" in str(exc) else "manual_submit_failed"
        _audit(
            runtime_store,
            "manual_submit_failed",
            account_id=account_id,
            operator_session_id=operator_session_id,
            symbol=request.symbol,
            side=request.side.value,
            qty=request.qty,
            intent=request.intent,
            reason=str(exc),
            idempotency_key=request.idempotency_key,
        )
        raise _operator_error(code, status_code=409 if code == "broker_sync_stale" else 400, message=str(exc)) from exc
    except Exception:
        runtime_store.release_manual_idempotency_key(account_id=account_id, idempotency_key=request.idempotency_key)
        raise

    runtime_store.commit_manual_idempotency_key(
        account_id=account_id,
        idempotency_key=request.idempotency_key,
        order_id=submitted.order_id,
    )
    _audit(
        runtime_store,
        "manual_submit_succeeded",
        account_id=account_id,
        operator_session_id=operator_session_id,
        order_id=submitted.order_id,
        client_order_id=submitted.client_order_id,
        symbol=submitted.symbol,
        side=submitted.side.value,
        qty=submitted.quantity,
        intent=submitted.intent.value,
        reason=request.reason,
        idempotency_key=request.idempotency_key,
    )
    return _serialize(submitted)


@router.post("/{account_id}/orders/{order_id}/cancel", response_model=CancelOrderResponse)
def cancel_manual_order(
    account_id: UUID,
    order_id: UUID,
    service: BrokerAccountServiceDependency,
    registry: ManualTradeRegistryDependency,
    runtime_store: RuntimeStoreDependency = None,
    operator_session_id: OperatorSessionDependency = None,
) -> CancelOrderResponse:
    operator_session_id = _require_operator_session(operator_session_id)
    if not _is_enabled():
        raise _operator_error("manual_trade_disabled", status_code=503)
    _resolve_account(account_id, service)

    entry = registry.get(account_id)
    if entry is None:
        raise _operator_error("manual_trade_composition_root_not_initialized", status_code=503)
    runtime_store = _runtime_store_from_entry(entry, runtime_store)
    order_manager = entry["order_manager"]
    broker_adapter = entry["broker_adapter"]
    broker_sync_service = entry["broker_sync_service"]
    broker_sync = getattr(order_manager, "_broker_sync", None)
    if broker_adapter is None or broker_sync is None:
        raise _operator_error("manual_trade_broker_wiring_incomplete", status_code=503)

    try:
        existing = order_manager.ledger.get(order_id)
    except Exception as exc:
        raise _operator_error("unknown_order", status_code=404, fields={"order_id": str(order_id)}) from exc

    if existing.account_id != account_id:
        raise _operator_error("order_account_mismatch", status_code=404)
    if existing.status == InternalOrderStatus.CANCELED:
        return CancelOrderResponse(
            order_id=existing.order_id,
            status=existing.status,
            no_op=True,
            filled_quantity=existing.filled_quantity,
            message="already_canceled",
        )
    if existing.status in {InternalOrderStatus.REJECTED, InternalOrderStatus.FAILED}:
        return CancelOrderResponse(
            order_id=existing.order_id,
            status=existing.status,
            no_op=True,
            filled_quantity=existing.filled_quantity,
            message="terminal_no_op",
        )
    if existing.status == InternalOrderStatus.FILLED:
        raise _operator_error(
            "order_already_filled",
            status_code=409,
            fields={"filled_quantity": existing.filled_quantity},
        )

    try:
        broker_result = broker_adapter.cancel_order(existing)
        canceled = broker_sync.apply_result(broker_result)
        _record_freshness(broker_sync_service, account_id)
    except OrderManagerError as exc:
        truth = order_manager.ledger.get(order_id)
        _audit(
            runtime_store,
            "manual_cancel_failed",
            account_id=account_id,
            operator_session_id=operator_session_id,
            order_id=order_id,
            reason=str(exc),
            ledger_status=truth.status.value,
        )
        if truth.status == InternalOrderStatus.FILLED:
            raise _operator_error(
                "order_already_filled",
                status_code=409,
                fields={"filled_quantity": truth.filled_quantity},
            ) from exc
        raise _operator_error("manual_cancel_failed", status_code=400, message=str(exc)) from exc

    _audit(
        runtime_store,
        "manual_cancel_succeeded",
        account_id=account_id,
        operator_session_id=operator_session_id,
        order_id=order_id,
        client_order_id=canceled.client_order_id,
        ledger_status=canceled.status.value,
    )
    return CancelOrderResponse(
        order_id=canceled.order_id,
        status=canceled.status,
        no_op=False,
        filled_quantity=canceled.filled_quantity,
        message=None,
    )


@router.get("/{account_id}/orders", response_model=ManualOrderListResponse)
def list_manual_orders(
    account_id: UUID,
    service: BrokerAccountServiceDependency,
    registry: ManualTradeRegistryDependency,
) -> ManualOrderListResponse:
    if not _is_enabled():
        raise _operator_error("manual_trade_disabled", status_code=503)
    _resolve_account(account_id, service)
    order_manager = registry.order_manager(account_id)
    if order_manager is None:
        return ManualOrderListResponse(orders=())
    orders = order_manager.ledger.by_account(account_id)
    sorted_orders = sorted(orders, key=lambda order: order.created_at, reverse=True)[:100]
    return ManualOrderListResponse(orders=tuple(_serialize(order) for order in sorted_orders))


def _annotate_route_methods() -> None:
    for route in getattr(router, "routes", []):
        if hasattr(route, "method"):
            continue
        methods = sorted(getattr(route, "methods", []))
        if methods:
            route.method = methods[0]


_annotate_route_methods()


def reset_manual_trade_state_for_tests() -> None:
    """Compatibility seam retained for older tests; state is now durable."""
    return None

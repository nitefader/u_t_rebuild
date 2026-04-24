from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from backend.app.control_plane.service import CancellationScope, ControlPlane
from backend.app.domain import IntentType
from backend.app.domain._base import utc_now
from backend.app.control_plane.client_order_id import build_program_client_order_id

from .ledger import OrderLedger
from .models import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManagerError


class OrderManager:
    _TERMINAL_STATUSES = {
        InternalOrderStatus.FILLED,
        InternalOrderStatus.CANCELED,
        InternalOrderStatus.REJECTED,
        InternalOrderStatus.FAILED,
    }
    _PROTECTIVE_INTENTS = {
        InternalOrderIntent.CLOSE,
        InternalOrderIntent.TAKE_PROFIT,
        InternalOrderIntent.STOP_LOSS,
        InternalOrderIntent.SCALE,
    }
    _REPLACEABLE_FIELDS = {"quantity", "limit_price", "stop_price", "time_in_force", "extended_hours"}

    def __init__(
        self,
        *,
        ledger: OrderLedger | None = None,
        broker_adapter: Any | None = None,
        broker_sync: Any | None = None,
        control_plane: ControlPlane | None = None,
    ) -> None:
        self._ledger = ledger or OrderLedger()
        self._sequence_by_attribution: dict[tuple[UUID, UUID, UUID, InternalOrderIntent], int] = defaultdict(int)
        self._broker_adapter = broker_adapter
        self._broker_sync = broker_sync
        self._control_plane = control_plane or ControlPlane()

    @property
    def ledger(self) -> OrderLedger:
        return self._ledger

    def create_order(
        self,
        *,
        account_id: UUID,
        execution_intent,
        order_intent: InternalOrderIntent | str | None = None,
    ) -> InternalOrder:
        if not execution_intent.governor_approved:
            raise OrderManagerError("execution intent is not approved by Portfolio Governor")
        if self._control_plane.system_recovery_active:
            raise OrderManagerError("system recovery is active; new order creation is blocked")
        intent = self._resolve_order_intent(execution_intent, order_intent)
        sequence = self._next_sequence(
            account_id=account_id,
            deployment_id=execution_intent.deployment_id,
            program_id=execution_intent.program_version_id,
            intent=intent,
        )
        now = utc_now()
        order = InternalOrder(
            order_id=uuid4(),
            client_order_id=build_program_client_order_id(
                getattr(execution_intent, "program_name", "utos"),
                execution_intent.deployment_id,
                intent=intent,
            ),
            account_id=account_id,
            deployment_id=execution_intent.deployment_id,
            program_id=execution_intent.program_version_id,
            symbol=execution_intent.symbol.upper(),
            side=execution_intent.side,
            quantity=execution_intent.qty,
            order_type=execution_intent.order_type,
            time_in_force=execution_intent.time_in_force,
            intent=intent,
            status=InternalOrderStatus.CREATED,
            created_at=now,
            updated_at=now,
            signal_name=execution_intent.signal_name,
            reason=execution_intent.reason,
        )
        return self._ledger.add(order)

    def update_status(
        self,
        *,
        order_id: UUID,
        status: InternalOrderStatus | str,
        reason: str | None = None,
    ) -> InternalOrder:
        try:
            normalized_status = status if isinstance(status, InternalOrderStatus) else InternalOrderStatus(status)
        except ValueError as exc:
            raise OrderManagerError(f"invalid order status: {status}") from exc
        order = self._ledger.get(order_id)
        updated = order.model_copy(
            update={
                "status": normalized_status,
                "updated_at": utc_now(),
                "reason": reason if reason is not None else order.reason,
            }
        )
        return self._ledger.replace(updated)

    def request_cancel(self, order_id: UUID) -> InternalOrder:
        order = self._ledger.get(order_id)
        self._ensure_cancelable(order)
        if self._should_preserve_order(order):
            return order
        requested = self._mark_cancel_requested(order)
        if self._broker_adapter is None:
            return requested
        result = self._broker_adapter.cancel_order(requested)
        return self._apply_broker_result(result)

    def request_cancel_scope(
        self,
        *,
        account_id: UUID,
        deployment_id: UUID | None = None,
        scope: str = CancellationScope.ACCOUNT.value,
    ) -> tuple[InternalOrder, ...]:
        normalized_scope = self._normalize_scope(scope)
        candidates = self._cancel_scope_candidates(
            account_id=account_id,
            deployment_id=deployment_id,
            scope=normalized_scope,
        )
        canceled: list[InternalOrder] = []
        for order in candidates:
            if order.intent != InternalOrderIntent.OPEN or self._should_preserve_order(order):
                continue
            if order.status in self._TERMINAL_STATUSES:
                continue
            canceled.append(self.request_cancel(order.order_id))
        return tuple(canceled)

    def request_replace(
        self,
        order_id: UUID,
        new_params: Mapping[str, object],
        *,
        allow_protective: bool = False,
    ) -> InternalOrder:
        order = self._ledger.get(order_id)
        self._ensure_replaceable(order, allow_protective=allow_protective)
        updates = self._validated_replace_params(new_params)
        if self._broker_adapter is None:
            replaced = order.model_copy(update={**updates, "updated_at": utc_now()})
            return self._ledger.replace(replaced)
        result = self._broker_adapter.replace_order(order, updates)
        synced = self._apply_broker_result(result)
        replaced = synced.model_copy(update={**updates, "updated_at": utc_now()})
        return self._ledger.replace(replaced)

    def _resolve_order_intent(
        self,
        execution_intent,
        order_intent: InternalOrderIntent | str | None,
    ) -> InternalOrderIntent:
        if order_intent is not None:
            try:
                return order_intent if isinstance(order_intent, InternalOrderIntent) else InternalOrderIntent(order_intent)
            except ValueError as exc:
                raise OrderManagerError(f"invalid order intent: {order_intent}") from exc
        if execution_intent.intent_type == IntentType.ENTRY:
            return InternalOrderIntent.OPEN
        if execution_intent.intent_type == IntentType.EXIT:
            return InternalOrderIntent.CLOSE
        raise OrderManagerError(f"unsupported execution intent type: {execution_intent.intent_type}")

    def _next_sequence(
        self,
        *,
        account_id: UUID,
        deployment_id: UUID,
        program_id: UUID,
        intent: InternalOrderIntent,
    ) -> int:
        key = (account_id, deployment_id, program_id, intent)
        self._sequence_by_attribution[key] += 1
        return self._sequence_by_attribution[key]

    def _short(self, value: UUID) -> str:
        return value.hex[:8]

    def _ensure_cancelable(self, order: InternalOrder) -> None:
        if order.status == InternalOrderStatus.FILLED:
            raise OrderManagerError("cannot cancel filled orders")

    def _ensure_replaceable(self, order: InternalOrder, *, allow_protective: bool) -> None:
        if order.status in self._TERMINAL_STATUSES:
            raise OrderManagerError("cannot replace terminal orders")
        if order.filled_quantity > 0 or order.status == InternalOrderStatus.PARTIALLY_FILLED:
            raise OrderManagerError("cannot replace filled orders")
        if order.intent != InternalOrderIntent.OPEN:
            if allow_protective and order.intent in self._PROTECTIVE_INTENTS:
                return
            raise OrderManagerError("cannot replace protective orders without explicit override")

    def _mark_cancel_requested(self, order: InternalOrder) -> InternalOrder:
        if order.cancel_requested_at is not None:
            return order
        return self._ledger.replace(order.model_copy(update={"cancel_requested_at": utc_now(), "updated_at": utc_now()}))

    def _should_preserve_order(self, order: InternalOrder) -> bool:
        if order.intent in self._PROTECTIVE_INTENTS:
            return True
        if order.intent != InternalOrderIntent.OPEN:
            return True
        return self._has_backing_position(order)

    def _has_backing_position(self, order: InternalOrder) -> bool:
        if self._broker_adapter is None:
            return False
        positions = self._broker_adapter.get_positions(order.account_id)
        return any(position.symbol.upper() == order.symbol.upper() and position.quantity != 0 for position in positions)

    def _normalize_scope(self, scope: str) -> str:
        try:
            return CancellationScope(scope).value
        except ValueError as exc:
            raise OrderManagerError(f"unsupported cancellation scope: {scope}") from exc

    def _cancel_scope_candidates(
        self,
        *,
        account_id: UUID,
        deployment_id: UUID | None,
        scope: str,
    ) -> tuple[InternalOrder, ...]:
        if scope == CancellationScope.GLOBAL.value:
            return self._ledger.all()
        if scope == CancellationScope.ACCOUNT.value:
            return self._ledger.by_account(account_id)
        if deployment_id is None:
            raise OrderManagerError("deployment scope requires deployment_id")
        return tuple(order for order in self._ledger.all() if order.deployment_id == deployment_id)

    def _validated_replace_params(self, new_params: Mapping[str, object]) -> dict[str, object]:
        unsupported = set(new_params) - self._REPLACEABLE_FIELDS
        if unsupported:
            raise OrderManagerError(f"unsupported replace params: {sorted(unsupported)}")
        return dict(new_params)

    def _apply_broker_result(self, result) -> InternalOrder:
        if self._broker_sync is None:
            raise OrderManagerError("broker lifecycle operation requires BrokerSync")
        return self._broker_sync.apply_result(result)

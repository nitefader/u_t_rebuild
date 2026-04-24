from __future__ import annotations

from collections import defaultdict
from uuid import UUID, uuid4

from backend.app.domain import IntentType
from backend.app.domain._base import utc_now

from .ledger import OrderLedger
from .models import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManagerError


class OrderManager:
    def __init__(self, *, ledger: OrderLedger | None = None) -> None:
        self._ledger = ledger or OrderLedger()
        self._sequence_by_attribution: dict[tuple[UUID, UUID, UUID, InternalOrderIntent], int] = defaultdict(int)

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
            client_order_id=self._client_order_id(
                account_id=account_id,
                deployment_id=execution_intent.deployment_id,
                program_id=execution_intent.program_version_id,
                intent=intent,
                sequence=sequence,
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

    def _client_order_id(
        self,
        *,
        account_id: UUID,
        deployment_id: UUID,
        program_id: UUID,
        intent: InternalOrderIntent,
        sequence: int,
    ) -> str:
        return (
            f"utos-{self._short(account_id)}-{self._short(deployment_id)}-"
            f"{self._short(program_id)}-{intent.value}-{sequence:06d}"
        )

    def _short(self, value: UUID) -> str:
        return value.hex[:8]

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from backend.app.control_plane.service import CancellationScope, ControlPlane
from backend.app.domain import CandidateSide, IntentType, OrderType, TimeInForce
from backend.app.domain._base import utc_now
from backend.app.control_plane.client_order_id import (
    build_manual_client_order_id,
    build_program_client_order_id,
    build_signal_plan_client_order_id,
)
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountSignalPlanEvaluation,
    GovernorDecisionTrace,
    RiskResolverResult,
    SignalPlan,
    SignalPlanIntent,
    SignalPlanSide,
)

from .ledger import OrderLedger
from .models import InternalOrder, InternalOrderIntent, InternalOrderStatus, OrderManagerError, OrderOrigin


class OrderManager:
    _TERMINAL_STATUSES = {
        InternalOrderStatus.FILLED,
        InternalOrderStatus.CANCELED,
        InternalOrderStatus.REJECTED,
        InternalOrderStatus.FAILED,
    }
    _PROTECTIVE_INTENTS = {
        InternalOrderIntent.CLOSE,
        InternalOrderIntent.REDUCE,
        InternalOrderIntent.TARGET,
        InternalOrderIntent.STOP,
        InternalOrderIntent.TRAIL,
        InternalOrderIntent.BREAKEVEN,
        InternalOrderIntent.RUNNER,
        InternalOrderIntent.LOGICAL_EXIT,
        InternalOrderIntent.TAKE_PROFIT,
        InternalOrderIntent.STOP_LOSS,
        InternalOrderIntent.SCALE,
    }
    _POSITION_MANAGEMENT_PRIORITY = {
        InternalOrderIntent.CLOSE: 100,
        InternalOrderIntent.LOGICAL_EXIT: 100,
        InternalOrderIntent.STOP: 80,
        InternalOrderIntent.STOP_LOSS: 80,
        InternalOrderIntent.TRAIL: 80,
        InternalOrderIntent.BREAKEVEN: 80,
        InternalOrderIntent.TARGET: 60,
        InternalOrderIntent.TAKE_PROFIT: 60,
        InternalOrderIntent.REDUCE: 60,
        InternalOrderIntent.SCALE: 60,
        InternalOrderIntent.RUNNER: 40,
    }
    _REPLACEABLE_FIELDS = {"quantity", "limit_price", "stop_price", "time_in_force", "extended_hours"}

    def __init__(
        self,
        *,
        ledger: OrderLedger | None = None,
        broker_adapter: Any | None = None,
        broker_sync: Any | None = None,
        broker_sync_service: Any | None = None,
        control_plane: ControlPlane | None = None,
    ) -> None:
        self._ledger = ledger or OrderLedger()
        self._sequence_by_attribution: dict[tuple[UUID, UUID, UUID, InternalOrderIntent], int] = defaultdict(int)
        self._broker_adapter = broker_adapter
        self._broker_sync = broker_sync
        self._broker_sync_service = broker_sync_service
        self._control_plane = control_plane or ControlPlane()

    @property
    def ledger(self) -> OrderLedger:
        return self._ledger

    def attach_broker_sync_service(self, service: Any) -> None:
        """Bind a BrokerSyncService after construction.

        The runtime orchestrator owns both the OrderManager and the
        BrokerSyncService, but the service depends on the OrderManager's
        ledger — so the service can only be built after the OrderManager
        exists. This setter completes the wiring without forcing callers
        to thread construction order through their composition root.
        """
        self._broker_sync_service = service

    def attach_broker_adapter(self, adapter: Any) -> None:
        self._broker_adapter = adapter

    def attach_broker_sync(self, broker_sync: Any) -> None:
        self._broker_sync = broker_sync

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
        self._enforce_broker_sync_freshness(account_id=account_id, intent=intent)
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
            origin=OrderOrigin.PROGRAM,
            deployment_id=execution_intent.deployment_id,
            program_id=execution_intent.program_version_id,
            symbol=execution_intent.symbol.upper(),
            side=self._side_for_execution_intent(execution_intent=execution_intent, intent=intent),
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

    def create_manual_order(
        self,
        *,
        account_id: UUID,
        symbol: str,
        side: CandidateSide | str,
        quantity: float,
        intent: InternalOrderIntent | str = InternalOrderIntent.OPEN,
        order_type: OrderType | str = OrderType.MARKET,
        time_in_force: TimeInForce | str = TimeInForce.DAY,
        reason: str | None = None,
        signal_name: str | None = "manual",
    ) -> InternalOrder:
        """Operator-driven order creation outside of any Program/Deployment.

        Bypasses the Portfolio Governor approval check (manual orders are
        the operator's authority by design) but still:
          - flows through ``OrderLedger`` so reconcile + cancel-scope find them,
          - honors the staleness gate for OPEN orders,
          - honors the system-recovery kill-switch.

        Manual orders carry ``origin=manual_operator`` and nullable
        deployment/program lineage so deployment-scoped queries cannot
        accidentally treat operator action as strategy action.
        """
        if self._control_plane.system_recovery_active:
            raise OrderManagerError("system recovery is active; new order creation is blocked")
        normalized_intent = self._coerce_manual_intent(intent)
        ledger_intent = self._intent_for_manual(normalized_intent)
        normalized_side = side if isinstance(side, CandidateSide) else CandidateSide(side)
        normalized_order_type = order_type if isinstance(order_type, OrderType) else OrderType(order_type)
        normalized_tif = time_in_force if isinstance(time_in_force, TimeInForce) else TimeInForce(time_in_force)
        if quantity <= 0:
            raise OrderManagerError("manual order quantity must be positive")
        self._enforce_broker_sync_freshness(account_id=account_id, intent=ledger_intent)
        now = utc_now()
        order = InternalOrder(
            order_id=uuid4(),
            client_order_id=build_manual_client_order_id(account_id, intent=normalized_intent),
            account_id=account_id,
            origin=OrderOrigin.MANUAL_OPERATOR,
            deployment_id=None,
            program_id=None,
            symbol=symbol.upper(),
            side=normalized_side,
            quantity=quantity,
            order_type=normalized_order_type,
            time_in_force=normalized_tif,
            intent=ledger_intent,
            status=InternalOrderStatus.CREATED,
            created_at=now,
            updated_at=now,
            signal_name=signal_name,
            reason=reason,
        )
        return self._ledger.add(order)

    def create_signal_plan_order(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        account_evaluation: AccountSignalPlanEvaluation,
        risk_result: RiskResolverResult,
        governor_decision: GovernorDecisionTrace,
        order_intent: InternalOrderIntent | str | None = None,
        position_lineage_id: UUID | None = None,
        position_side: CandidateSide | SignalPlanSide | str | None = None,
        opening_signal_plan_id: UUID | None = None,
        leg_label: str | None = None,
    ) -> InternalOrder:
        if account_evaluation.account_id != account_id:
            raise OrderManagerError("account evaluation does not belong to account")
        if account_evaluation.signal_plan_id != signal_plan.signal_plan_id:
            raise OrderManagerError("account evaluation does not match SignalPlan")
        if account_evaluation.status != AccountEvaluationStatus.ACCEPTED:
            raise OrderManagerError("account evaluation is not accepted")
        if risk_result.account_id != account_id or risk_result.signal_plan_id != signal_plan.signal_plan_id:
            raise OrderManagerError("risk result does not match SignalPlan/account")
        if not risk_result.allowed:
            raise OrderManagerError("risk result is not allowed")
        if risk_result.resolved_quantity is None:
            raise OrderManagerError("signal plan order requires resolved_quantity")
        if governor_decision.account_id != account_id or governor_decision.signal_plan_id != signal_plan.signal_plan_id:
            raise OrderManagerError("governor decision does not match SignalPlan/account")
        if not governor_decision.approved:
            raise OrderManagerError("SignalPlan is not approved by Governor")
        if self._control_plane.system_recovery_active:
            raise OrderManagerError("system recovery is active; new order creation is blocked")

        intent = self._resolve_signal_plan_order_intent(signal_plan.intent, order_intent)
        lineage_id = self._resolve_position_lineage_id(signal_plan=signal_plan, position_lineage_id=position_lineage_id)
        opening_lineage_id = self._resolve_opening_signal_plan_id(
            signal_plan=signal_plan,
            opening_signal_plan_id=opening_signal_plan_id,
        )
        client_order_id = build_signal_plan_client_order_id(
            account_id,
            signal_plan.deployment_id,
            signal_plan.signal_plan_id,
            intent=intent,
            position_lineage_id=lineage_id,
            leg_label=leg_label,
        )
        existing = self._ledger.by_client_order_id(client_order_id)
        if existing is not None:
            if existing.account_id != account_id:
                raise OrderManagerError("idempotency key collision across accounts")
            return existing
        self._enforce_broker_sync_freshness(account_id=account_id, intent=intent)
        now = utc_now()
        order = InternalOrder(
            order_id=uuid4(),
            client_order_id=client_order_id,
            account_id=account_id,
            origin=OrderOrigin.SIGNAL_PLAN,
            deployment_id=signal_plan.deployment_id,
            program_id=None,
            strategy_id=signal_plan.strategy_id,
            strategy_version_id=signal_plan.strategy_version_id,
            signal_plan_id=signal_plan.signal_plan_id,
            opening_signal_plan_id=opening_lineage_id,
            current_signal_plan_id=signal_plan.signal_plan_id,
            position_lineage_id=lineage_id,
            account_evaluation_id=account_evaluation.evaluation_id,
            governor_decision_id=governor_decision.governor_decision_id,
            leg_label=leg_label,
            lifecycle_intent=intent.value,
            symbol=signal_plan.symbol.upper(),
            side=self._side_for_signal_plan(
                signal_plan=signal_plan,
                order_intent=intent,
                position_side=position_side,
            ),
            quantity=risk_result.resolved_quantity,
            order_type=self._order_type_for_signal_plan(signal_plan),
            time_in_force=self._time_in_force_for_signal_plan(signal_plan),
            intent=intent,
            status=InternalOrderStatus.CREATED,
            created_at=now,
            updated_at=now,
            signal_name=signal_plan.reason,
            reason=signal_plan.reason,
        )
        return self._ledger.add(order)

    def create_signal_plan_leg_orders(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        account_evaluation: AccountSignalPlanEvaluation,
        risk_result: RiskResolverResult,
        governor_decision: GovernorDecisionTrace,
        position_lineage_id: UUID | None = None,
        position_side: CandidateSide | SignalPlanSide | str | None = None,
        opening_signal_plan_id: UUID | None = None,
    ) -> tuple[InternalOrder, ...]:
        if not risk_result.leg_allocations:
            return (
                self.create_signal_plan_order(
                    account_id=account_id,
                    signal_plan=signal_plan,
                    account_evaluation=account_evaluation,
                    risk_result=risk_result,
                    governor_decision=governor_decision,
                    position_lineage_id=position_lineage_id,
                    position_side=position_side,
                    opening_signal_plan_id=opening_signal_plan_id,
                ),
            )
        orders: list[InternalOrder] = []
        lineage_id = position_lineage_id or signal_plan.related_position_lineage_id or signal_plan.signal_plan_id
        opening_id = opening_signal_plan_id or signal_plan.opening_signal_plan_id or signal_plan.signal_plan_id
        for allocation in risk_result.leg_allocations:
            leg_risk_result = risk_result.model_copy(update={"resolved_quantity": allocation.resolved_quantity})
            orders.append(
                self.create_signal_plan_order(
                    account_id=account_id,
                    signal_plan=signal_plan,
                    account_evaluation=account_evaluation,
                    risk_result=leg_risk_result,
                    governor_decision=governor_decision,
                    order_intent=InternalOrderIntent(allocation.lifecycle_intent.value),
                    position_lineage_id=lineage_id,
                    position_side=position_side or signal_plan.side,
                    opening_signal_plan_id=opening_id,
                    leg_label=allocation.leg_label,
                )
            )
        return tuple(orders)

    @staticmethod
    def _coerce_manual_intent(intent: InternalOrderIntent | str) -> str:
        if isinstance(intent, InternalOrderIntent):
            value = intent.value
        else:
            value = str(intent)
        if value not in {"open", "close", "reduce"}:
            raise OrderManagerError(f"unsupported manual order intent: {intent}")
        return value

    @staticmethod
    def _intent_for_manual(manual_intent: str) -> InternalOrderIntent:
        # ``reduce`` maps onto CLOSE in the ledger — it's a partial close,
        # which is still a CLOSE for ledger / reconcile purposes. The
        # client_order_id keeps the operator's original ``reduce`` label.
        if manual_intent == "open":
            return InternalOrderIntent.OPEN
        return InternalOrderIntent.CLOSE

    @staticmethod
    def _resolve_signal_plan_order_intent(
        signal_plan_intent: SignalPlanIntent,
        override: InternalOrderIntent | str | None,
    ) -> InternalOrderIntent:
        if override is not None:
            try:
                return override if isinstance(override, InternalOrderIntent) else InternalOrderIntent(str(override))
            except ValueError as exc:
                raise OrderManagerError(f"unsupported signal plan order intent: {override}") from exc
        try:
            return InternalOrderIntent(signal_plan_intent.value)
        except ValueError as exc:
            raise OrderManagerError(f"unsupported SignalPlan intent: {signal_plan_intent}") from exc

    @staticmethod
    def _resolve_position_lineage_id(
        *,
        signal_plan: SignalPlan,
        position_lineage_id: UUID | None,
    ) -> UUID:
        if position_lineage_id is not None:
            return position_lineage_id
        if signal_plan.related_position_lineage_id is not None:
            return signal_plan.related_position_lineage_id
        if signal_plan.intent == SignalPlanIntent.OPEN:
            return signal_plan.signal_plan_id
        raise OrderManagerError("position-management SignalPlan order requires position_lineage_id")

    @staticmethod
    def _resolve_opening_signal_plan_id(
        *,
        signal_plan: SignalPlan,
        opening_signal_plan_id: UUID | None,
    ) -> UUID:
        if signal_plan.intent == SignalPlanIntent.OPEN:
            return signal_plan.signal_plan_id
        if opening_signal_plan_id is not None:
            return opening_signal_plan_id
        if signal_plan.opening_signal_plan_id is not None:
            return signal_plan.opening_signal_plan_id
        raise OrderManagerError("position-management SignalPlan order requires opening_signal_plan_id")

    @staticmethod
    def _side_for_signal_plan(
        *,
        signal_plan: SignalPlan,
        order_intent: InternalOrderIntent,
        position_side: CandidateSide | SignalPlanSide | str | None = None,
    ) -> CandidateSide:
        if signal_plan.side == SignalPlanSide.FLAT:
            raise OrderManagerError("flat SignalPlan side cannot create an order")
        if order_intent == InternalOrderIntent.OPEN:
            return CandidateSide(signal_plan.side.value)

        side = signal_plan.side
        if position_side is not None:
            normalized = position_side.value if isinstance(position_side, CandidateSide | SignalPlanSide) else str(position_side)
            side = SignalPlanSide(normalized)
        if side == SignalPlanSide.LONG:
            return CandidateSide.SHORT
        if side == SignalPlanSide.SHORT:
            return CandidateSide.LONG
        raise OrderManagerError("flat position side cannot create a position-management order")

    @staticmethod
    def _order_type_for_signal_plan(signal_plan: SignalPlan) -> OrderType:
        if signal_plan.entry is not None:
            return signal_plan.entry.order_type
        return OrderType.MARKET

    @staticmethod
    def _time_in_force_for_signal_plan(signal_plan: SignalPlan) -> TimeInForce:
        if signal_plan.entry is not None and signal_plan.entry.time_in_force_preference is not None:
            return signal_plan.entry.time_in_force_preference
        return TimeInForce.DAY

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
        return self._request_cancel(order, preserve_protective=True)

    def request_superseded_position_management_cancels(
        self,
        *,
        account_id: UUID,
        position_lineage_id: UUID,
        incoming_intent: InternalOrderIntent,
        exclude_order_id: UUID | None = None,
    ) -> tuple[InternalOrder, ...]:
        return tuple(
            self._request_cancel(order, preserve_protective=False)
            for order in self.superseded_position_management_orders(
                account_id=account_id,
                position_lineage_id=position_lineage_id,
                incoming_intent=incoming_intent,
            )
            if order.order_id != exclude_order_id
        )

    def _request_cancel(self, order: InternalOrder, *, preserve_protective: bool) -> InternalOrder:
        self._ensure_cancelable(order)
        if preserve_protective and self._should_preserve_order(order):
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

    def pending_position_management_orders(
        self,
        *,
        account_id: UUID,
        position_lineage_id: UUID,
    ) -> tuple[InternalOrder, ...]:
        return tuple(
            order
            for order in self._ledger.by_account(account_id)
            if order.position_lineage_id == position_lineage_id
            and order.intent != InternalOrderIntent.OPEN
            and order.status not in self._TERMINAL_STATUSES
            and order.cancel_requested_at is None
        )

    def superseded_position_management_orders(
        self,
        *,
        account_id: UUID,
        position_lineage_id: UUID,
        incoming_intent: InternalOrderIntent,
    ) -> tuple[InternalOrder, ...]:
        incoming_priority = self._position_management_priority(incoming_intent)
        if incoming_priority <= 0:
            return ()
        return tuple(
            order
            for order in self.pending_position_management_orders(
                account_id=account_id,
                position_lineage_id=position_lineage_id,
            )
            if incoming_priority > self._position_management_priority(order.intent)
            or incoming_intent in {InternalOrderIntent.CLOSE, InternalOrderIntent.LOGICAL_EXIT}
        )

    def _enforce_broker_sync_freshness(
        self,
        *,
        account_id: UUID,
        intent: InternalOrderIntent,
    ) -> None:
        if self._broker_sync_service is None:
            return
        if intent != InternalOrderIntent.OPEN:
            return
        state = self._broker_sync_service.current_sync_state(account_id)
        if not state.is_stale:
            return
        reason = state.stale_reason or "broker_sync_stale"
        raise OrderManagerError(f"broker_sync_stale:{reason}")

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

    def _position_management_priority(self, intent: InternalOrderIntent) -> int:
        return self._POSITION_MANAGEMENT_PRIORITY.get(intent, 0)

    @staticmethod
    def _side_for_execution_intent(
        *,
        execution_intent,
        intent: InternalOrderIntent,
    ) -> CandidateSide:
        side = execution_intent.side
        if intent == InternalOrderIntent.OPEN:
            return side
        if side == CandidateSide.LONG:
            return CandidateSide.SHORT
        if side == CandidateSide.SHORT:
            return CandidateSide.LONG
        raise OrderManagerError(f"unsupported execution side: {side}")

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

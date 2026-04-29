from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from backend.app.brokers.models import BrokerFillUpdateEvent
from backend.app.domain import (
    AccountEvaluationStatus,
    AccountParticipationDecision,
    AccountSignalPlanEvaluation,
    GovernorDecisionStatus,
    GovernorDecisionTrace,
)
from backend.app.governor.models import GovernorDecision, GovernorPolicy
from backend.app.orders.ledger import OrderLedger
from backend.app.orders.models import InternalOrder
from backend.app.pipeline.models import PipelineEvent
from backend.app.runtime.models import DeploymentContext, RuntimeEvent, RuntimeEventType, RuntimeState, RuntimeStatus

from .models import (
    AccountOperations,
    AccountSummary,
    DeploymentOperations,
    DeploymentSummary,
    FlattenRequestResponse,
    InternalOrderLedgerSummary,
    OrderDetail,
    OPEN_ORDER_STATUSES,
    ResearchEvidenceSummary,
    RuntimeOverview,
    TERMINAL_ORDER_STATUSES,
)

if TYPE_CHECKING:
    from backend.app.control_plane.service import ControlPlane


class OperationsCenterService:
    """Read/control orchestration for Account runtime operations.

    This service does not fetch from broker adapters, create orders, reconcile
    broker truth, or evaluate policy. It only projects already-owned runtime
    facts and delegates control commands to ControlPlane.
    """

    def __init__(
        self,
        *,
        control_plane: "ControlPlane",
        runtime_store: object | None = None,
        order_ledger: OrderLedger | None = None,
        broker_sync_reader: object | None = None,
        trade_ledger: object | None = None,
        deployment_reader: object | None = None,
        deployments: Iterable[DeploymentContext] = (),
        latest_pipeline_events: Iterable[PipelineEvent | RuntimeEvent] = (),
        latest_governor_decisions: Iterable[GovernorDecision] = (),
        governor_state: GovernorPolicy | None = None,
        governor_id: str = "portfolio-governor",
    ) -> None:
        self._control_plane = control_plane
        self._runtime_store = runtime_store
        self._order_ledger = order_ledger
        self._broker_sync_reader = broker_sync_reader
        self._trade_ledger = trade_ledger
        self._deployment_reader = deployment_reader
        self._deployments = tuple(deployments)
        self._latest_pipeline_events = tuple(latest_pipeline_events)
        self._latest_governor_decisions = tuple(latest_governor_decisions)
        self._governor_state = governor_state if governor_state is not None else self._load_governor_state(governor_id)
        self._governor_id = governor_id

    def get_runtime_overview(self) -> RuntimeOverview:
        control_state = self._control_plane.snapshot()
        sync_states = self._list_broker_sync_freshness()
        stale_sync_accounts = tuple(state for state in sync_states if state.is_stale)
        positions = self._all_positions()
        broker_accounts = tuple(
            AccountSummary(
                account_id=account_id,
                snapshot=self._broker_account_snapshot(account_id),
                sync_state=self._broker_sync_freshness(account_id),
                open_orders_count=len(self._open_broker_orders(account_id)),
                positions_count=len(self._positions(account_id)),
                is_paused=self._control_plane.is_account_paused(account_id),
                is_killed=control_state.global_kill_active,
            )
            for account_id in sorted(self._account_ids(), key=str)
        )
        deployments = tuple(self._deployment_summary(deployment_id) for deployment_id in sorted(self._deployment_ids(), key=str))
        return RuntimeOverview(
            system_recovery_active=control_state.system_recovery_active,
            global_kill_active=control_state.global_kill_active,
            control_state=control_state,
            broker_accounts=broker_accounts,
            deployments=deployments,
            stale_sync_accounts=stale_sync_accounts,
            blocked_deployments=tuple(summary for summary in deployments if summary.status == RuntimeStatus.BLOCKED_RECOVERY),
            open_orders_count=sum(account.open_orders_count for account in broker_accounts),
            open_positions_count=sum(1 for position in positions if position.quantity != 0),
            latest_governor_decisions=self._latest_governor_decisions,
            latest_broker_sync_timestamp=self._latest_broker_sync_timestamp(sync_states),
            latest_runtime_event_timestamp=self._latest_event_timestamp(self._latest_pipeline_events),
            research_evidence_summary=self._research_evidence_summary(),
        )

    def get_account_operations(self, account_id: UUID) -> AccountOperations:
        orders = self._orders_by_account(account_id)
        # Manual operator orders carry no deployment_id; filter None out of
        # the deployment-id set so we never pass None into DeploymentSummary
        # (Pydantic UUID validation rejects None and the route surfaces a
        # 503 to the operator). See coordination note 2026-04-27 in
        # Operations_Production_Readiness/OPERATION_STATUS.md.
        deployment_ids = {order.deployment_id for order in orders if order.deployment_id is not None}
        deployment_ids |= self._deployment_ids_for_account(account_id)
        return AccountOperations(
            account_id=account_id,
            broker_account_snapshot=self._broker_account_snapshot(account_id),
            broker_sync_freshness=self._broker_sync_freshness(account_id),
            open_broker_orders=self._open_broker_orders(account_id),
            internal_order_ledger_summary=self._order_summary(orders),
            positions=self._positions(account_id),
            deployments=tuple(
                self._deployment_summary(deployment_id)
                for deployment_id in sorted(deployment_ids, key=str)
            ),
            is_paused=self._control_plane.is_account_paused(account_id),
            is_killed=self._control_plane.global_kill_active,
        )

    def get_deployment_operations(self, deployment_id: UUID) -> DeploymentOperations:
        orders = self._orders_by_deployment(deployment_id)
        runtime_state = self._runtime_state(deployment_id)
        deployment_context = self._deployment_context(deployment_id)
        deployment_record = self._deployment_record(deployment_id)
        events = tuple(event for event in self._latest_pipeline_events if event.deployment_id == deployment_id)
        decisions = self._decisions_for_deployment(deployment_id)
        account_id = self._deployment_account_id(deployment_id, orders, deployment_record)
        return DeploymentOperations(
            deployment_id=deployment_id,
            runtime_status=runtime_state.status if runtime_state is not None else deployment_context.status if deployment_context is not None else None,
            strategy_version_id=self._deployment_strategy_version_id(deployment_context, orders, deployment_record),
            strategy_version=deployment_context.strategy_version if deployment_context is not None else None,
            broker_account_id=account_id,
            governor_id=self._governor_id,
            governor_state=self._governor_state,
            last_market_data_timestamp=self._last_market_data_timestamp(runtime_state, events),
            last_broker_sync_timestamp=(
                runtime_state.last_broker_sync_timestamp
                if runtime_state is not None and runtime_state.last_broker_sync_timestamp is not None
                else self._last_broker_sync_timestamp_for_deployment(account_id)
            ),
            last_decision_timestamp=self._last_decision_timestamp(events),
            runtime_loop_state=runtime_state.status if runtime_state is not None else None,
            last_signal_timestamp=runtime_state.last_signal_timestamp if runtime_state is not None else None,
            last_governor_decision=runtime_state.last_governor_decision if runtime_state is not None else None,
            last_order_id=runtime_state.last_order_id if runtime_state is not None else None,
            last_runtime_error=runtime_state.last_error if runtime_state is not None else None,
            open_orders=tuple(order for order in orders if order.status in OPEN_ORDER_STATUSES),
            trades=self._trades_by_deployment(deployment_id),
            fills=tuple(fill for fill in self._fills() if self._fill_belongs_to_deployment(fill, orders)),
            latest_pipeline_events=events,
            latest_governor_decisions=decisions,
        )

    def get_order_detail(self, order_id: UUID) -> OrderDetail:
        order = self._order_by_id(order_id)
        mapping = self._broker_mapping(order_id)
        return self._order_detail(order=order, mapping=mapping)

    def get_order_detail_by_broker_order_id(self, broker_order_id: str) -> OrderDetail:
        mapping = self._broker_mapping_by_broker_order_id(broker_order_id)
        order = self._order_by_id(mapping.order_id)
        return self._order_detail(order=order, mapping=mapping)

    def list_account_signal_plan_evaluations(
        self,
        *,
        account_id: UUID | None = None,
        deployment_id: UUID | None = None,
        signal_plan_id: UUID | None = None,
        limit: int = 100,
    ) -> tuple[AccountSignalPlanEvaluation, ...]:
        bounded_limit = max(1, min(limit, 500))
        evaluations_by_id: dict[UUID, AccountSignalPlanEvaluation] = {}
        for order in self._all_orders():
            if order.signal_plan_id is None:
                continue
            if account_id is not None and order.account_id != account_id:
                continue
            if deployment_id is not None and order.deployment_id != deployment_id:
                continue
            if signal_plan_id is not None and order.signal_plan_id != signal_plan_id:
                continue
            evaluation = self._evaluation_from_order(order)
            if evaluation is None:
                continue
            existing = evaluations_by_id.get(evaluation.evaluation_id)
            if existing is None or evaluation.created_at > existing.created_at:
                evaluations_by_id[evaluation.evaluation_id] = evaluation
        return tuple(
            sorted(
                evaluations_by_id.values(),
                key=lambda evaluation: evaluation.evaluated_at or evaluation.created_at,
                reverse=True,
            )[:bounded_limit]
        )

    def _order_detail(self, *, order: InternalOrder, mapping) -> OrderDetail:
        freshness = self._broker_sync_freshness(order.account_id)
        broker_status = "unknown_stale"
        if mapping is not None:
            for snapshot in self._list_broker_open_order_snapshots(order.account_id):
                if snapshot.client_order_id == order.client_order_id or snapshot.broker_order_id == mapping.broker_order_id:
                    broker_status = snapshot.status.value
                    break
            else:
                broker_status = order.status.value
        fills = tuple(fill for fill in self._fills_for_order(order))
        return OrderDetail(
            internal_order=order,
            broker_mapping=mapping,
            broker_account_id=order.account_id,
            deployment_id=order.deployment_id,
            strategy_version_id=order.strategy_version_id,
            broker_order_id=mapping.broker_order_id if mapping is not None else None,
            broker_status=broker_status,
            broker_sync_timestamp=self._last_broker_sync_timestamp_for_deployment(order.account_id) if freshness is not None else None,
            fills=fills,
            trade_summary={
                "fill_count": len(fills),
                "filled_quantity": sum(fill.qty for fill in fills),
                "last_fill_at": max((fill.event_at for fill in fills), default=None),
            },
        )

    def list_research_evidence(
        self,
        *,
        strategy_id: UUID | None = None,
        strategy_version_id: UUID | None = None,
        evidence_type: str | None = None,
    ) -> tuple[object, ...]:
        if self._runtime_store is None or not hasattr(self._runtime_store, "list_research_evidence"):
            return ()
        return tuple(
            self._runtime_store.list_research_evidence(
                strategy_id=strategy_id,
                strategy_version_id=strategy_version_id,
                evidence_type=evidence_type,
            )
        )

    def get_research_evidence(self, evidence_id: UUID) -> object:
        if self._runtime_store is None or not hasattr(self._runtime_store, "load_research_evidence"):
            raise KeyError(f"unknown research evidence: {evidence_id}")
        return self._runtime_store.load_research_evidence(evidence_id)

    def pause_deployment(self, deployment_id: UUID, reason: str) -> None:
        _ = reason
        self._control_plane.pause_deployment(deployment_id)

    def resume_deployment(self, deployment_id: UUID, reason: str) -> None:
        _ = reason
        self._control_plane.resume_deployment(deployment_id)

    def pause_account(self, account_id: UUID, reason: str) -> None:
        _ = reason
        self._control_plane.pause_account(account_id)

    def resume_account(self, account_id: UUID, reason: str) -> None:
        _ = reason
        self._control_plane.resume_account(account_id)

    def global_kill(self, reason: str) -> None:
        _ = reason
        self._control_plane.activate_global_kill()

    def global_resume(self, reason: str) -> None:
        _ = reason
        self._control_plane.clear_global_kill()

    def request_flatten_account(self, account_id: UUID, reason: str) -> FlattenRequestResponse:
        return self._delegate_flatten("account", account_id, reason)

    def request_flatten_deployment(self, deployment_id: UUID, reason: str) -> FlattenRequestResponse:
        return self._delegate_flatten("deployment", deployment_id, reason)

    def _delegate_flatten(self, scope: str, target_id: UUID, reason: str) -> FlattenRequestResponse:
        method_name = f"request_flatten_{scope}"
        if hasattr(self._control_plane, method_name):
            result = getattr(self._control_plane, method_name)(target_id, reason)
            return FlattenRequestResponse(
                accepted=True,
                status="delegated",
                reason=reason,
                scope=scope,
                target_id=target_id,
                result=result,
            )
        return FlattenRequestResponse(
            accepted=False,
            status="unsupported_not_ready",
            reason="flatten_not_implemented_in_control_plane",
            scope=scope,
            target_id=target_id,
        )

    def _deployment_summary(self, deployment_id: UUID) -> DeploymentSummary:
        state = self._runtime_state(deployment_id)
        context = self._deployment_context(deployment_id)
        record = self._deployment_record(deployment_id)
        orders = self._orders_by_deployment(deployment_id)
        status = state.status if state is not None else context.status if context is not None else RuntimeStatus.READY
        return DeploymentSummary(
            deployment_id=deployment_id,
            status=status,
            is_running=status == RuntimeStatus.RUNNING,
            account_id=self._deployment_account_id(deployment_id, orders, record),
            strategy_version_id=self._deployment_strategy_version_id(context, orders, record),
            strategy_version=context.strategy_version if context is not None else None,
        )

    def _evaluation_from_order(self, order: InternalOrder) -> AccountSignalPlanEvaluation | None:
        if order.deployment_id is None or order.strategy_id is None or order.signal_plan_id is None:
            return None
        warnings = ()
        if order.account_evaluation_id is None:
            warnings = ("legacy_order_missing_account_evaluation_id",)
        governor_decision = None
        if order.governor_decision_id is not None:
            governor_decision = GovernorDecisionTrace(
                governor_decision_id=order.governor_decision_id,
                account_id=order.account_id,
                signal_plan_id=order.signal_plan_id,
                status=GovernorDecisionStatus.APPROVED,
                approved=True,
                reasons=("order_created",),
                evaluated_at=order.created_at,
            )
        return AccountSignalPlanEvaluation(
            evaluation_id=order.account_evaluation_id or order.order_id,
            account_id=order.account_id,
            signal_plan_id=order.signal_plan_id,
            deployment_id=order.deployment_id,
            strategy_id=order.strategy_id,
            status=AccountEvaluationStatus.ACCEPTED,
            participation_decision=AccountParticipationDecision.PARTICIPATE,
            governor_decision=governor_decision,
            created_at=order.created_at,
            evaluated_at=order.created_at,
            warnings=warnings,
        )

    def _order_summary(self, orders: tuple[InternalOrder, ...]) -> InternalOrderLedgerSummary:
        by_status: dict[str, int] = {}
        by_intent: dict[str, int] = {}
        for order in orders:
            by_status[order.status.value] = by_status.get(order.status.value, 0) + 1
            by_intent[order.intent.value] = by_intent.get(order.intent.value, 0) + 1
        return InternalOrderLedgerSummary(
            total_count=len(orders),
            open_count=sum(1 for order in orders if order.status in OPEN_ORDER_STATUSES),
            terminal_count=sum(1 for order in orders if order.status in TERMINAL_ORDER_STATUSES),
            by_status=by_status,
            by_intent=by_intent,
        )

    def _account_ids(self) -> set[UUID]:
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_broker_accounts"):
            return {account.id for account in self._runtime_store.list_broker_accounts()}
        account_ids = {order.account_id for order in self._all_orders()}
        account_ids.update(snapshot.account_id for snapshot in self._list_broker_account_snapshots())
        account_ids.update(state.account_id for state in self._list_broker_sync_freshness())
        account_ids.update(order.account_id for order in self._list_broker_open_order_snapshots())
        account_ids.update(position.account_id for position in self._list_all_broker_position_snapshots())
        return account_ids - self._archived_account_ids()

    def _archived_account_ids(self) -> set[UUID]:
        if self._runtime_store is None or not hasattr(self._runtime_store, "list_broker_accounts"):
            return set()
        try:
            return {
                account.id
                for account in self._runtime_store.list_broker_accounts(include_archived=True)
                if getattr(account, "is_archived", False)
            }
        except TypeError:
            return set()

    def _deployment_ids(self) -> set[UUID]:
        deployment_ids = {deployment.deployment_id for deployment in self._list_deployment_records()}
        deployment_ids.update(state.deployment_id for state in self._list_runtime_states())
        deployment_ids.update(context.deployment_id for context in self._deployments)
        return {deployment_id for deployment_id in deployment_ids if deployment_id is not None}

    def _deployment_ids_for_account(self, account_id: UUID) -> set[UUID]:
        return {order.deployment_id for order in self._orders_by_account(account_id) if order.deployment_id is not None}

    def _all_orders(self) -> tuple[InternalOrder, ...]:
        if self._order_ledger is not None:
            return tuple(self._order_ledger.all())
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_orders"):
            return tuple(self._runtime_store.list_orders())
        return ()

    def _order_by_id(self, order_id: UUID) -> InternalOrder:
        if self._runtime_store is not None and hasattr(self._runtime_store, "load_order"):
            return self._runtime_store.load_order(order_id)
        for order in self._all_orders():
            if order.order_id == order_id:
                return order
        raise KeyError(f"unknown order: {order_id}")

    def _broker_mapping(self, order_id: UUID):
        if self._runtime_store is None or not hasattr(self._runtime_store, "lookup_broker_mapping_by_internal_order_id"):
            return None
        try:
            return self._runtime_store.lookup_broker_mapping_by_internal_order_id(order_id)
        except KeyError:
            return None

    def _broker_mapping_by_broker_order_id(self, broker_order_id: str):
        if self._runtime_store is None or not hasattr(self._runtime_store, "lookup_broker_mapping_by_broker_order_id"):
            raise KeyError(f"unknown broker order mapping: {broker_order_id}")
        return self._runtime_store.lookup_broker_mapping_by_broker_order_id(broker_order_id, provider="alpaca")

    def _orders_by_account(self, account_id: UUID) -> tuple[InternalOrder, ...]:
        if self._order_ledger is not None:
            return tuple(self._order_ledger.by_account(account_id))
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_orders_by_account"):
            return tuple(self._runtime_store.list_orders_by_account(account_id))
        return tuple(order for order in self._all_orders() if order.account_id == account_id)

    def _orders_by_deployment(self, deployment_id: UUID) -> tuple[InternalOrder, ...]:
        if self._order_ledger is not None:
            return tuple(self._order_ledger.by_deployment(deployment_id))
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_orders_by_deployment"):
            return tuple(self._runtime_store.list_orders_by_deployment(deployment_id))
        return tuple(order for order in self._all_orders() if order.deployment_id == deployment_id)

    def _broker_account_snapshot(self, account_id: UUID):
        if self._broker_sync_reader is not None and hasattr(self._broker_sync_reader, "latest_account_snapshot"):
            snapshot = self._broker_sync_reader.latest_account_snapshot(account_id)
            if snapshot is not None:
                return snapshot
        if self._runtime_store is not None and hasattr(self._runtime_store, "load_broker_account_snapshot"):
            try:
                return self._runtime_store.load_broker_account_snapshot(account_id)
            except KeyError:
                return None
        return None

    def _broker_sync_freshness(self, account_id: UUID):
        if self._runtime_store is not None and hasattr(self._runtime_store, "load_broker_sync_freshness"):
            try:
                return self._runtime_store.load_broker_sync_freshness(account_id)
            except KeyError:
                return None
        return None

    def _open_broker_orders(self, account_id: UUID):
        return tuple(order for order in self._list_broker_open_order_snapshots(account_id) if not _broker_order_terminal(order.status.value))

    def _positions(self, account_id: UUID):
        if self._broker_sync_reader is not None and hasattr(self._broker_sync_reader, "latest_positions"):
            return tuple(self._broker_sync_reader.latest_positions(account_id))
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_broker_position_snapshots"):
            return tuple(self._runtime_store.list_broker_position_snapshots(account_id))
        return ()

    def _all_positions(self):
        positions = []
        live_reader_account_ids = set(self._account_ids_from_broker_sync_reader())
        account_ids = set(live_reader_account_ids)
        account_ids.update(order.account_id for order in self._all_orders())
        account_ids.update(snapshot.account_id for snapshot in self._list_broker_account_snapshots())
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_all_broker_position_snapshots"):
            for position in self._runtime_store.list_all_broker_position_snapshots():
                if position.account_id not in live_reader_account_ids:
                    positions.append(position)
                    account_ids.discard(position.account_id)
        for account_id in account_ids:
            positions.extend(self._positions(account_id))
        return tuple(positions)

    def _fills(self):
        if self._broker_sync_reader is not None and hasattr(self._broker_sync_reader, "fills"):
            return tuple(self._broker_sync_reader.fills())
        return ()

    def _fills_for_order(self, order: InternalOrder):
        fills = list(self._fills())
        fills.extend(
            trade
            for trade in self._trades_by_deployment(order.deployment_id)
            if isinstance(trade, BrokerFillUpdateEvent)
        )
        return tuple(fill for fill in fills if fill.client_order_id == order.client_order_id)

    def _fill_belongs_to_deployment(self, fill, orders: tuple[InternalOrder, ...]) -> bool:
        return any(order.client_order_id == fill.client_order_id for order in orders)

    def _runtime_state(self, deployment_id: UUID) -> RuntimeState | None:
        if self._runtime_store is not None and hasattr(self._runtime_store, "load_deployment_runtime_state"):
            try:
                return self._runtime_store.load_deployment_runtime_state(deployment_id)
            except KeyError:
                return None
        return next((state for state in self._list_runtime_states() if state.deployment_id == deployment_id), None)

    def _deployment_context(self, deployment_id: UUID) -> DeploymentContext | None:
        return next((deployment for deployment in self._deployments if deployment.deployment_id == deployment_id), None)

    def _deployment_account_id(self, deployment_id: UUID, orders: tuple[InternalOrder, ...], record: object | None = None) -> UUID | None:
        _ = deployment_id
        if orders:
            return orders[0].account_id
        account_ids = getattr(record, "subscribed_account_ids", ())
        return account_ids[0] if len(account_ids) == 1 else None

    def _deployment_strategy_version_id(
        self,
        context: DeploymentContext | None,
        orders: tuple[InternalOrder, ...],
        record: object | None = None,
    ) -> UUID | None:
        if context is not None and context.strategy_version_id is not None:
            return context.strategy_version_id
        record_strategy_version_id = getattr(record, "strategy_version_id", None)
        if record_strategy_version_id is not None:
            return record_strategy_version_id
        return orders[0].strategy_version_id if orders else None

    def _last_market_data_timestamp(self, runtime_state: RuntimeState | None, events: tuple[PipelineEvent | RuntimeEvent, ...]) -> datetime | None:
        timestamps = []
        if runtime_state is not None:
            timestamps.extend(runtime_state.last_bar_timestamp_by_symbol_timeframe.values())
        timestamps.extend(
            event.timestamp
            for event in events
            if isinstance(event, RuntimeEvent) and event.event_type == RuntimeEventType.BAR_RECEIVED
        )
        return max(timestamps, default=None)

    def _last_broker_sync_timestamp_for_deployment(self, account_id: UUID | None) -> datetime | None:
        if account_id is None:
            return None
        sync_state = self._broker_sync_freshness(account_id)
        if sync_state is None:
            return None
        return max(
            (
                timestamp
                for timestamp in (
                    sync_state.last_event_at,
                    sync_state.last_poll_sync_at,
                    sync_state.last_successful_sync_at,
                    sync_state.last_sync_at,
                )
                if timestamp is not None
            ),
            default=None,
        )

    def _last_decision_timestamp(self, events: tuple[PipelineEvent | RuntimeEvent, ...]) -> datetime | None:
        return max((event.timestamp for event in events if "decision" in event.event_type.value), default=None)

    def _decisions_for_deployment(self, deployment_id: UUID) -> tuple[GovernorDecision, ...]:
        matched: list[GovernorDecision] = []
        for decision in self._latest_governor_decisions:
            projected_state = decision.projected_state or {}
            if projected_state.get("deployment_id") == str(deployment_id):
                matched.append(decision)
        return tuple(matched or self._latest_governor_decisions)

    def _trades_by_deployment(self, deployment_id: UUID) -> tuple[object, ...]:
        if self._trade_ledger is not None and hasattr(self._trade_ledger, "by_deployment"):
            return tuple(self._trade_ledger.by_deployment(deployment_id))
        if self._runtime_store is not None and hasattr(self._runtime_store, "load_trades_by_deployment"):
            return tuple(self._runtime_store.load_trades_by_deployment(deployment_id))
        return ()

    def _list_runtime_states(self) -> tuple[RuntimeState, ...]:
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_deployment_runtime_states"):
            return tuple(self._runtime_store.list_deployment_runtime_states())
        return ()

    def _list_deployment_records(self) -> tuple[object, ...]:
        if self._deployment_reader is not None and hasattr(self._deployment_reader, "list_deployments"):
            return tuple(self._deployment_reader.list_deployments())
        return ()

    def _deployment_record(self, deployment_id: UUID) -> object | None:
        for deployment in self._list_deployment_records():
            if getattr(deployment, "deployment_id", None) == deployment_id:
                return deployment
        return None

    def _research_evidence_summary(self) -> tuple[ResearchEvidenceSummary, ...]:
        if self._runtime_store is None or not hasattr(self._runtime_store, "list_research_evidence"):
            return ()
        grouped: dict[str, dict[str, object]] = {}
        for evidence in self._runtime_store.list_research_evidence():
            evidence_type = _research_evidence_type_name(evidence)
            created_at = getattr(evidence, "created_at", None)
            current = grouped.setdefault(evidence_type, {"count": 0, "latest_created_at": None})
            current["count"] = int(current["count"]) + 1
            if isinstance(created_at, datetime) and (
                current["latest_created_at"] is None or created_at > current["latest_created_at"]
            ):
                current["latest_created_at"] = created_at
        return tuple(
            ResearchEvidenceSummary(
                evidence_type=evidence_type,
                count=int(payload["count"]),
                latest_created_at=payload["latest_created_at"] if isinstance(payload["latest_created_at"], datetime) else None,
            )
            for evidence_type, payload in sorted(grouped.items())
        )

    def _list_broker_account_snapshots(self):
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_broker_account_snapshots"):
            return tuple(self._runtime_store.list_broker_account_snapshots())
        return ()

    def _list_broker_sync_freshness(self):
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_broker_sync_freshness"):
            return tuple(self._runtime_store.list_broker_sync_freshness())
        return ()

    def _list_broker_open_order_snapshots(self, account_id: UUID | None = None):
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_broker_open_order_snapshots"):
            return tuple(self._runtime_store.list_broker_open_order_snapshots(account_id))
        return ()

    def _list_all_broker_position_snapshots(self):
        if self._runtime_store is not None and hasattr(self._runtime_store, "list_all_broker_position_snapshots"):
            return tuple(self._runtime_store.list_all_broker_position_snapshots())
        return ()

    def _account_ids_from_broker_sync_reader(self) -> set[UUID]:
        return {snapshot.account_id for snapshot in self._list_broker_account_snapshots()}

    def _latest_broker_sync_timestamp(self, sync_states) -> datetime | None:
        timestamps = []
        for state in sync_states:
            timestamps.extend(
                timestamp
                for timestamp in (
                    state.last_event_at,
                    state.last_poll_sync_at,
                    state.last_successful_sync_at,
                    state.last_sync_at,
                )
                if timestamp is not None
            )
        return max(timestamps, default=None)

    def _latest_event_timestamp(self, events: tuple[PipelineEvent | RuntimeEvent, ...]) -> datetime | None:
        return max((event.timestamp for event in events), default=None)

    def _load_governor_state(self, governor_id: str) -> GovernorPolicy | None:
        if self._runtime_store is None or not hasattr(self._runtime_store, "load_portfolio_governor_state"):
            return None
        try:
            return self._runtime_store.load_portfolio_governor_state(governor_id)
        except KeyError:
            return None


def _broker_order_terminal(status: str) -> bool:
    return status in {"filled", "canceled", "rejected", "expired"}


def _research_evidence_type_name(evidence: object) -> str:
    name = type(evidence).__name__
    return {
        "ChartLabPreviewEvidence": "chart_lab_preview",
        "BacktestRun": "backtest_run",
        "SimulationRunEvidence": "simulation_run",
        "OptimizationRun": "optimization_run",
        "WalkForwardRun": "walk_forward_run",
        "PromotionEvidenceBundle": "promotion_bundle",
    }.get(name, name)

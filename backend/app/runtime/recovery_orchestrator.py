from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from backend.app.brokers import BrokerAdapterError, BrokerOpenOrderSnapshot, BrokerOrderStatus
from backend.app.control_plane import ControlPlaneState
from backend.app.orders import InternalOrder, InternalOrderStatus

from .models import RuntimeState, RuntimeStatus


class RecoveryResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    recovered_accounts: int
    recovered_deployments: int
    blocked_deployments: int
    reconciliation_issues: list[str]


class RuntimeRecoveryOrchestrator:
    def __init__(
        self,
        persistence_store,
        broker_adapter,
        broker_sync,
        governor_service,
        control_plane,
        runtime_state_store,
    ) -> None:
        self._persistence_store = persistence_store
        self._broker_adapter = broker_adapter
        self._broker_sync = broker_sync
        self._governor_service = governor_service
        self._control_plane = control_plane
        self._runtime_state_store = runtime_state_store

    def run_startup_recovery(self) -> RecoveryResult:
        """Run idempotent startup recovery without starting execution."""

        issues: list[str] = []
        recovered_accounts: set[UUID] = set()
        blocked_deployments: set[UUID] = set()
        recovered_deployments: set[UUID] = set()
        loaded = _LoadedRuntimeState()

        self._control_plane.set_system_recovery_active(True)
        try:
            loaded = self._load_persisted_state()
            self._rehydrate_control_plane(loaded.control_plane_state)
            account_ids = self._account_ids(loaded)
            deployment_ids = self._deployment_ids(loaded)

            for account_id in sorted(account_ids, key=str):
                try:
                    account_issues = self._recover_account(account_id, loaded)
                    issues.extend(account_issues)
                    recovered_accounts.add(account_id)
                except Exception as exc:  # noqa: BLE001 - startup recovery must fail closed.
                    issues.append(f"{account_id}: recovery_failed:{exc}")
                    blocked_deployments.update(self._deployments_for_account(account_id, loaded.orders))

            for deployment_id in sorted(deployment_ids, key=str):
                deployment_issues = self._safety_issues_for_deployment(deployment_id, loaded)
                if deployment_issues:
                    issues.extend(deployment_issues)
                    blocked_deployments.add(deployment_id)
                    self._save_runtime_state(deployment_id, RuntimeStatus.BLOCKED_RECOVERY)
                    continue
                recovered_deployments.add(deployment_id)
                self._save_runtime_state(deployment_id, RuntimeStatus.RECOVERED_READY)
        except Exception as exc:  # noqa: BLE001 - fail closed, return diagnosable result.
            issues.append(f"startup_recovery_failed:{exc}")
            for deployment_id in self._deployment_ids(loaded):
                blocked_deployments.add(deployment_id)
                self._save_runtime_state(deployment_id, RuntimeStatus.BLOCKED_RECOVERY)
        finally:
            self._control_plane.set_system_recovery_active(False)

        return RecoveryResult(
            recovered_accounts=len(recovered_accounts),
            recovered_deployments=len(recovered_deployments),
            blocked_deployments=len(blocked_deployments),
            reconciliation_issues=sorted(set(issues)),
        )

    def _load_persisted_state(self) -> "_LoadedRuntimeState":
        return _LoadedRuntimeState(
            deployments=_call_tuple(self._persistence_store, "list_deployment_runtime_states"),
            orders=_call_tuple(self._persistence_store, "list_orders"),
            trades=_call_tuple(self._persistence_store, "list_trades"),
            broker_mappings=_call_tuple(self._persistence_store, "list_broker_order_mappings"),
            account_snapshots=_call_tuple(self._persistence_store, "list_broker_account_snapshots"),
            broker_freshness=_call_tuple(self._persistence_store, "list_broker_sync_freshness"),
            governor_state=self._load_governor_state(),
            control_plane_state=self._load_control_plane_state(),
        )

    def _rehydrate_control_plane(self, state: ControlPlaneState | None) -> None:
        if state is None:
            return
        self._control_plane.apply_state(state, preserve_recovery_mode=True)

    def _recover_account(self, account_id: UUID, loaded: "_LoadedRuntimeState") -> list[str]:
        issues: list[str] = []
        account_snapshot = self._broker_sync.sync_account(account_id)
        positions = self._broker_sync.sync_positions(account_id)
        synced_orders = self._broker_sync.sync_open_orders(account_id)
        open_orders = self._broker_adapter.list_open_orders(account_id)
        freshness = self._broker_sync.record_sync_freshness(account_snapshot)

        local_by_client_order_id = {
            order.client_order_id: order
            for order in self._refresh_orders_by_account(account_id, loaded.orders)
        }
        open_by_client_order_id = {order.client_order_id: order for order in open_orders}
        synced_client_order_ids = {order.client_order_id for order in synced_orders}

        for order in local_by_client_order_id.values():
            if order.status in _TERMINAL_ORDER_STATUSES:
                continue
            if order.client_order_id in open_by_client_order_id or order.client_order_id in synced_client_order_ids:
                continue
            try:
                self._broker_adapter.get_order(order)
            except BrokerAdapterError:
                self._broker_sync.mark_missing_broker_order(order)
                issues.append(f"{account_id}: missing_broker_order:{order.client_order_id}")

        for broker_order in open_orders:
            if broker_order.client_order_id in local_by_client_order_id:
                continue
            self._broker_sync.record_external_open_order(broker_order)
            issues.append(f"{account_id}: unknown_broker_order_ingested:{broker_order.broker_order_id}")

        if freshness.is_stale:
            issues.append(f"{account_id}: trading_blocked_reason=broker_sync_stale")

        tracked_symbols = {
            order.symbol.upper()
            for order in self._refresh_orders_by_account(account_id, loaded.orders)
            if order.status in {InternalOrderStatus.PARTIALLY_FILLED, InternalOrderStatus.FILLED}
            or order.filled_quantity > 0
        }
        for position in positions:
            if position.quantity == 0 or position.symbol.upper() in tracked_symbols:
                continue
            issues.append(f"{account_id}: orphaned_open_position:{position.symbol.upper()}")

        return issues

    def _safety_issues_for_deployment(self, deployment_id: UUID, loaded: "_LoadedRuntimeState") -> list[str]:
        issues: list[str] = []
        orders = self._refresh_orders_by_deployment(deployment_id, loaded.orders)
        account_ids = {order.account_id for order in orders}

        if self._control_plane.global_kill_active:
            issues.append(f"{deployment_id}: control_plane_global_kill_active")
        if self._control_plane.is_deployment_paused(deployment_id):
            issues.append(f"{deployment_id}: control_plane_deployment_paused")

        for account_id in sorted(account_ids, key=str):
            if self._control_plane.is_account_paused(account_id):
                issues.append(f"{deployment_id}: account_paused:{account_id}")
            try:
                snapshot = self._persistence_store.load_broker_account_snapshot(account_id)
            except KeyError:
                issues.append(f"{deployment_id}: missing_broker_account_snapshot:{account_id}")
                continue
            try:
                freshness = self._persistence_store.load_broker_sync_freshness(account_id)
            except KeyError:
                issues.append(f"{deployment_id}: missing_broker_sync_freshness:{account_id}")
                continue
            if snapshot.account_id != account_id:
                issues.append(f"{deployment_id}: inconsistent_account_snapshot:{account_id}")
            if freshness.is_stale:
                issues.append(f"{deployment_id}: broker_sync_stale:{account_id}")

        broker_mappings = self._refresh_broker_mappings(loaded.broker_mappings)
        mapped_order_ids = {mapping.order_id for mapping in broker_mappings}
        order_ids = {order.order_id for order in orders}
        for mapping in broker_mappings:
            if mapping.order_id not in {order.order_id for order in loaded.orders}:
                issues.append(f"{deployment_id}: inconsistent_order_mapping:{mapping.broker_order_id}")
            if mapping.order_id in order_ids and mapping.account_id not in account_ids:
                issues.append(f"{deployment_id}: inconsistent_order_mapping:{mapping.broker_order_id}")
        for order in orders:
            if order.status in _TERMINAL_ORDER_STATUSES or order.client_order_id.startswith("external-"):
                continue
            if order.status in {InternalOrderStatus.ACCEPTED, InternalOrderStatus.PARTIALLY_FILLED} and order.order_id not in mapped_order_ids:
                issues.append(f"{deployment_id}: inconsistent_order_mapping:{order.client_order_id}")

        if self._governor_service is None or getattr(self._governor_service, "policy", None) is None:
            issues.append(f"{deployment_id}: governor_state_invalid")

        for issue in self._reloaded_reconciliation_issues():
            if str(deployment_id) in issue or any(str(order.account_id) in issue for order in orders):
                issues.append(f"{deployment_id}: {issue}")

        return sorted(set(issues))

    def _save_runtime_state(self, deployment_id: UUID, status: RuntimeStatus) -> None:
        state = self._load_runtime_state(deployment_id)
        updated = state.model_copy(update={"status": status})
        target = self._runtime_state_store or self._persistence_store
        if hasattr(target, "save_deployment_runtime_state"):
            target.save_deployment_runtime_state(updated)
        elif hasattr(target, "save_runtime_state"):
            target.save_runtime_state(updated)
        else:
            self._persistence_store.save_deployment_runtime_state(updated)

    def _load_runtime_state(self, deployment_id: UUID) -> RuntimeState:
        target = self._runtime_state_store or self._persistence_store
        try:
            if hasattr(target, "load_deployment_runtime_state"):
                return target.load_deployment_runtime_state(deployment_id)
            if hasattr(target, "load_runtime_state"):
                return target.load_runtime_state(deployment_id)
        except KeyError:
            pass
        return RuntimeState(deployment_id=deployment_id)

    def _load_governor_state(self) -> object | None:
        try:
            if hasattr(self._persistence_store, "load_portfolio_governor_state"):
                return self._persistence_store.load_portfolio_governor_state("portfolio-governor")
        except KeyError:
            return None
        return None

    def _load_control_plane_state(self) -> ControlPlaneState | None:
        try:
            if hasattr(self._persistence_store, "load_control_plane_state"):
                return self._persistence_store.load_control_plane_state("default")
        except KeyError:
            return None
        return None

    def _account_ids(self, loaded: "_LoadedRuntimeState") -> set[UUID]:
        account_ids = {order.account_id for order in loaded.orders}
        account_ids.update(mapping.account_id for mapping in loaded.broker_mappings)
        account_ids.update(snapshot.account_id for snapshot in loaded.account_snapshots)
        account_ids.update(freshness.account_id for freshness in loaded.broker_freshness)
        return account_ids

    def _deployment_ids(self, loaded: "_LoadedRuntimeState") -> set[UUID]:
        deployment_ids = {state.deployment_id for state in loaded.deployments}
        deployment_ids.update(order.deployment_id for order in loaded.orders)
        return deployment_ids

    def _deployments_for_account(self, account_id: UUID, orders: tuple[InternalOrder, ...]) -> set[UUID]:
        return {order.deployment_id for order in orders if order.account_id == account_id}

    def _refresh_orders_by_account(self, account_id: UUID, fallback: tuple[InternalOrder, ...]) -> tuple[InternalOrder, ...]:
        if hasattr(self._persistence_store, "list_orders_by_account"):
            return self._persistence_store.list_orders_by_account(account_id)
        return tuple(order for order in fallback if order.account_id == account_id)

    def _refresh_orders_by_deployment(self, deployment_id: UUID, fallback: tuple[InternalOrder, ...]) -> tuple[InternalOrder, ...]:
        if hasattr(self._persistence_store, "list_orders_by_deployment"):
            return self._persistence_store.list_orders_by_deployment(deployment_id)
        return tuple(order for order in fallback if order.deployment_id == deployment_id)

    def _refresh_broker_mappings(self, fallback: tuple[object, ...]) -> tuple[object, ...]:
        if hasattr(self._persistence_store, "list_broker_order_mappings"):
            return self._persistence_store.list_broker_order_mappings()
        return fallback

    def _reloaded_reconciliation_issues(self) -> tuple[str, ...]:
        return ()


class _LoadedRuntimeState:
    def __init__(
        self,
        *,
        deployments: tuple[RuntimeState, ...] = (),
        orders: tuple[InternalOrder, ...] = (),
        trades: tuple[object, ...] = (),
        broker_mappings: tuple[object, ...] = (),
        account_snapshots: tuple[object, ...] = (),
        broker_freshness: tuple[object, ...] = (),
        governor_state: object | None = None,
        control_plane_state: ControlPlaneState | None = None,
    ) -> None:
        self.deployments = deployments
        self.orders = orders
        self.trades = trades
        self.broker_mappings = broker_mappings
        self.account_snapshots = account_snapshots
        self.broker_freshness = broker_freshness
        self.governor_state = governor_state
        self.control_plane_state = control_plane_state


def _call_tuple(target: object, method_name: str) -> tuple[object, ...]:
    if not hasattr(target, method_name):
        return ()
    return tuple(getattr(target, method_name)())


_TERMINAL_ORDER_STATUSES = {
    InternalOrderStatus.FILLED,
    InternalOrderStatus.CANCELED,
    InternalOrderStatus.REJECTED,
    InternalOrderStatus.FAILED,
}

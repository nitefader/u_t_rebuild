from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.brokers.models import BrokerOrderResult, BrokerPositionSnapshot
from backend.app.domain._base import utc_now
from backend.app.orders.ledger import OrderLedger

from .client_order_id import parse_order_deployment_id, parse_order_intent


class ControlGateDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    reason: str
    rule_id: str


class CancellationScope(StrEnum):
    GLOBAL = "global"
    ACCOUNT = "account"
    DEPLOYMENT = "deployment"


class CancellationSweepResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    canceled: tuple[str, ...] = ()
    skipped_protective: tuple[str, ...] = ()
    skipped_has_position: tuple[str, ...] = ()
    skipped_unknown: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    dry_run: bool
    scope: str


class KillSwitchEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    active: bool
    created_at: datetime = Field(default_factory=utc_now)


class AccountControlState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    account_id: UUID
    is_killed: bool = False


class DeploymentControlState(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    deployment_id: UUID
    status: str = "ready"


class ControlPlane:
    def __init__(
        self,
        *,
        global_kill_active: bool = False,
        paused_account_ids: set[UUID] | frozenset[UUID] | None = None,
        paused_deployment_ids: set[UUID] | frozenset[UUID] | None = None,
    ) -> None:
        self._global_kill_active = global_kill_active
        self._paused_account_ids = set(paused_account_ids or set())
        self._paused_deployment_ids = set(paused_deployment_ids or set())

    @property
    def global_kill_active(self) -> bool:
        return self._global_kill_active

    def activate_global_kill(self) -> None:
        self._global_kill_active = True

    def clear_global_kill(self) -> None:
        self._global_kill_active = False

    def pause_account(self, account_id: UUID) -> None:
        self._paused_account_ids.add(account_id)

    def resume_account(self, account_id: UUID) -> None:
        self._paused_account_ids.discard(account_id)

    def is_account_paused(self, account_id: UUID) -> bool:
        return account_id in self._paused_account_ids

    def pause_deployment(self, deployment_id: UUID) -> None:
        self._paused_deployment_ids.add(deployment_id)

    def resume_deployment(self, deployment_id: UUID) -> None:
        self._paused_deployment_ids.discard(deployment_id)

    def is_deployment_paused(self, deployment_id: UUID) -> bool:
        return deployment_id in self._paused_deployment_ids

    def can_open_new_position(
        self,
        *,
        account_id: UUID,
        deployment_id: UUID,
        symbol: str,
        side: str,
    ) -> ControlGateDecision:
        _ = symbol, side
        if self._global_kill_active:
            return ControlGateDecision(allowed=False, reason="global_kill_active", rule_id="global_kill_blocks_open")
        if account_id in self._paused_account_ids:
            return ControlGateDecision(allowed=False, reason="account_pause_active", rule_id="account_pause_blocks_open")
        if deployment_id in self._paused_deployment_ids:
            return ControlGateDecision(allowed=False, reason="deployment_pause_active", rule_id="deployment_pause_blocks_open")
        return ControlGateDecision(allowed=True, reason="allowed", rule_id="allow_open")

    def can_trade(self, *, account_id: UUID, deployment_id: UUID, symbol: str, side: str) -> ControlGateDecision:
        return self.can_open_new_position(
            account_id=account_id,
            deployment_id=deployment_id,
            symbol=symbol,
            side=side,
        )

    def cancel_resting_open_orders_without_positions(
        self,
        *,
        account_id: UUID,
        broker_adapter,
        order_ledger: OrderLedger,
        scope: str = CancellationScope.ACCOUNT.value,
        deployment_id: UUID | None = None,
        dry_run: bool = True,
    ) -> CancellationSweepResult:
        open_orders = broker_adapter.list_open_orders(account_id)
        positions = broker_adapter.get_positions(account_id)
        symbols_with_positions = {position.symbol.upper() for position in positions if position.quantity != 0}
        local_orders_by_client_id = {order.client_order_id: order for order in order_ledger.by_account(account_id)}
        canceled: list[str] = []
        skipped_protective: list[str] = []
        skipped_has_position: list[str] = []
        skipped_unknown: list[str] = []
        errors: list[str] = []

        for broker_order in open_orders:
            if not self._in_scope(broker_order, scope=scope, deployment_id=deployment_id):
                continue
            intent = parse_order_intent(broker_order.client_order_id)
            if intent == "unknown":
                skipped_unknown.append(broker_order.client_order_id)
                continue
            if intent in {"sl", "tp", "close", "scale"}:
                skipped_protective.append(broker_order.client_order_id)
                continue
            local_order = local_orders_by_client_id.get(broker_order.client_order_id)
            if local_order is None:
                skipped_unknown.append(broker_order.client_order_id)
                continue
            if local_order.symbol.upper() in symbols_with_positions:
                skipped_has_position.append(broker_order.client_order_id)
                continue
            if not dry_run:
                try:
                    broker_adapter.cancel_order(broker_order.client_order_id)
                except Exception as exc:  # noqa: BLE001 - cancellation boundary should return errors, not explode.
                    errors.append(f"{broker_order.client_order_id}: {exc}")
                    continue
            canceled.append(broker_order.client_order_id)

        return CancellationSweepResult(
            canceled=tuple(canceled),
            skipped_protective=tuple(skipped_protective),
            skipped_has_position=tuple(skipped_has_position),
            skipped_unknown=tuple(skipped_unknown),
            errors=tuple(errors),
            dry_run=dry_run,
            scope=scope,
        )

    def _in_scope(self, broker_order: BrokerOrderResult, *, scope: str, deployment_id: UUID | None) -> bool:
        if scope in {CancellationScope.GLOBAL.value, CancellationScope.ACCOUNT.value}:
            return True
        if scope != CancellationScope.DEPLOYMENT.value:
            raise ValueError(f"unsupported cancellation scope: {scope}")
        if deployment_id is None:
            raise ValueError("deployment scope requires deployment_id")
        return parse_order_deployment_id(broker_order.client_order_id) == deployment_id.hex[:8]


def hydrate_control_plane(
    *,
    kill_switch_events: tuple[KillSwitchEvent, ...] = (),
    accounts: tuple[AccountControlState, ...] = (),
    deployments: tuple[DeploymentControlState, ...] = (),
) -> ControlPlane:
    latest_kill = max(kill_switch_events, key=lambda event: event.created_at).active if kill_switch_events else False
    return ControlPlane(
        global_kill_active=latest_kill,
        paused_account_ids={account.account_id for account in accounts if account.is_killed},
        paused_deployment_ids={
            deployment.deployment_id for deployment in deployments if deployment.status == "paused"
        },
    )

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from backend.app.brokers import (
    BrokerAccountSnapshot,
    BrokerOrderResult,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)
from backend.app.control_plane import (
    AccountControlState,
    ControlPlane,
    DeploymentControlState,
    KillSwitchEvent,
    hydrate_control_plane,
    parse_order_deployment_id,
    parse_order_intent,
)
from backend.app.control_plane.client_order_id import build_signal_plan_client_order_id
from backend.app.domain import TradingMode
from backend.app.orders import InternalOrder, InternalOrderIntent, OrderLedger, OrderManager
from backend.tests.fixtures.modern_order import make_signal_plan_order


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_A = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
DEPLOYMENT_B = UUID("bbbbbbbb-cccc-dddd-eeee-ffffffffffff")


class CancellableBroker:
    def __init__(
        self,
        *,
        open_orders: tuple[BrokerOrderResult, ...],
        positions: tuple[BrokerPositionSnapshot, ...] = (),
    ) -> None:
        self.open_orders = open_orders
        self.positions = positions
        self.canceled: list[str] = []

    def submit_order(self, order: InternalOrder) -> BrokerOrderResult:
        raise AssertionError("control-plane sweep must not submit orders")

    def get_order(self, order: InternalOrder) -> BrokerOrderResult:
        raise AssertionError("control-plane sweep must not fetch individual orders")

    def list_open_orders(self, account_id: UUID) -> tuple[BrokerOrderResult, ...]:
        assert account_id == ACCOUNT_ID
        return self.open_orders

    def get_account_snapshot(self, account_id: UUID) -> BrokerAccountSnapshot:
        return BrokerAccountSnapshot(
            account_id=account_id,
            provider="fake",
            mode=TradingMode.BROKER_PAPER,
            buying_power=100_000,
            cash=100_000,
            equity=100_000,
        )

    def get_positions(self, account_id: UUID) -> tuple[BrokerPositionSnapshot, ...]:
        assert account_id == ACCOUNT_ID
        return self.positions

    def cancel_order(self, client_order_id: str) -> None:
        self.canceled.append(client_order_id)


def _order(
    ledger: OrderLedger,
    *,
    deployment_id: UUID = DEPLOYMENT_A,
    symbol: str = "SPY",
    order_intent: InternalOrderIntent | None = None,
) -> InternalOrder:
    return make_signal_plan_order(
        OrderManager(ledger=ledger),
        account_id=ACCOUNT_ID,
        deployment_id=deployment_id,
        symbol=symbol,
        order_intent=order_intent,
    )


def _broker_result(order: InternalOrder) -> BrokerOrderResult:
    return BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=BrokerOrderStatus.ACCEPTED,
        broker_order_id=f"broker-{order.client_order_id}",
        broker_status="new",
        raw_status="new",
    )


def test_signal_plan_client_order_id_intent_encoding_and_parsing() -> None:
    signal_plan_id = UUID("12345678-1111-2222-3333-444444444444")
    client_order_id = build_signal_plan_client_order_id(ACCOUNT_ID, DEPLOYMENT_A, signal_plan_id, intent="target")

    assert client_order_id.startswith(f"sigplan-{ACCOUNT_ID.hex[:8]}-{signal_plan_id.hex[:8]}-target-")
    assert parse_order_intent(client_order_id) == "target"
    assert parse_order_deployment_id(client_order_id) is None

    breakeven_id = build_signal_plan_client_order_id(ACCOUNT_ID, DEPLOYMENT_A, signal_plan_id, intent="breakeven")
    logical_exit_id = build_signal_plan_client_order_id(ACCOUNT_ID, DEPLOYMENT_A, signal_plan_id, intent="logical_exit")
    assert parse_order_intent(breakeven_id) == "breakeven"
    assert parse_order_intent(logical_exit_id) == "logical_exit"


def test_legacy_client_order_id_parses_as_unknown() -> None:
    assert parse_order_intent("utos-11111111-aaaaaaaa-99999999-open-000001") == "unknown"
    assert parse_order_deployment_id("utos-11111111-aaaaaaaa-99999999-open-000001") is None


def test_global_kill_survives_restart() -> None:
    control_plane = hydrate_control_plane(
        kill_switch_events=(
            KillSwitchEvent(active=False, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
            KillSwitchEvent(active=True, created_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        )
    )

    assert control_plane.global_kill_active is True


def test_account_pause_survives_restart() -> None:
    control_plane = hydrate_control_plane(accounts=(AccountControlState(account_id=ACCOUNT_ID, is_killed=True),))

    assert control_plane.is_account_paused(ACCOUNT_ID) is True


def test_deployment_pause_survives_restart() -> None:
    control_plane = hydrate_control_plane(deployments=(DeploymentControlState(deployment_id=DEPLOYMENT_A, status="paused"),))

    assert control_plane.is_deployment_paused(DEPLOYMENT_A) is True


def test_can_open_new_position_blocks_by_precedence() -> None:
    control_plane = ControlPlane(
        global_kill_active=True,
        paused_account_ids={ACCOUNT_ID},
        paused_deployment_ids={DEPLOYMENT_A},
    )

    first = control_plane.can_open_new_position(account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_A, symbol="SPY", side="long")
    assert first.reason == "global_kill_active"
    control_plane.clear_global_kill()
    second = control_plane.can_open_new_position(account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_A, symbol="SPY", side="long")
    assert second.reason == "account_pause_active"
    control_plane.resume_account(ACCOUNT_ID)
    third = control_plane.can_open_new_position(account_id=ACCOUNT_ID, deployment_id=DEPLOYMENT_A, symbol="SPY", side="long")
    assert third.reason == "deployment_pause_active"


def test_pausing_deployment_a_does_not_pause_deployment_b_using_same_strategy() -> None:
    control_plane = ControlPlane()
    control_plane.pause_deployment(DEPLOYMENT_A)

    assert control_plane.is_deployment_paused(DEPLOYMENT_A) is True
    assert control_plane.is_deployment_paused(DEPLOYMENT_B) is False


def test_open_intent_order_with_no_position_is_canceled() -> None:
    ledger = OrderLedger()
    order = _order(ledger)
    broker = CancellableBroker(open_orders=(_broker_result(order),))

    result = ControlPlane().cancel_resting_open_orders_without_positions(
        account_id=ACCOUNT_ID,
        broker_adapter=broker,
        order_ledger=ledger,
        dry_run=False,
    )

    assert result.canceled == (order.client_order_id,)
    assert broker.canceled == [order.client_order_id]


def test_open_intent_order_with_existing_position_is_skipped() -> None:
    ledger = OrderLedger()
    order = _order(ledger, symbol="SPY")
    broker = CancellableBroker(
        open_orders=(_broker_result(order),),
        positions=(
            BrokerPositionSnapshot(
                account_id=ACCOUNT_ID,
                symbol="SPY",
                quantity=10,
                market_value=1000,
                avg_entry_price=100,
                side=BrokerPositionSide.LONG,
            ),
        ),
    )

    result = ControlPlane().cancel_resting_open_orders_without_positions(
        account_id=ACCOUNT_ID,
        broker_adapter=broker,
        order_ledger=ledger,
        dry_run=False,
    )

    assert result.skipped_has_position == (order.client_order_id,)
    assert broker.canceled == []


def test_protective_and_scale_orders_are_never_canceled() -> None:
    ledger = OrderLedger()
    orders = (
        _order(ledger, order_intent=InternalOrderIntent.STOP_LOSS),
        _order(ledger, order_intent=InternalOrderIntent.TAKE_PROFIT),
        _order(ledger, order_intent=InternalOrderIntent.CLOSE),
        _order(ledger, order_intent=InternalOrderIntent.SCALE),
    )
    broker = CancellableBroker(open_orders=tuple(_broker_result(order) for order in orders))

    result = ControlPlane().cancel_resting_open_orders_without_positions(
        account_id=ACCOUNT_ID,
        broker_adapter=broker,
        order_ledger=ledger,
        dry_run=False,
    )

    assert result.skipped_protective == tuple(order.client_order_id for order in orders)
    assert broker.canceled == []


def test_unknown_intent_orders_are_skipped_and_flagged() -> None:
    ledger = OrderLedger()
    broker_order = BrokerOrderResult(
        order_id=UUID(int=1),
        client_order_id="legacy-order-id",
        status=BrokerOrderStatus.ACCEPTED,
        raw_status="new",
    )
    broker = CancellableBroker(open_orders=(broker_order,))

    result = ControlPlane().cancel_resting_open_orders_without_positions(
        account_id=ACCOUNT_ID,
        broker_adapter=broker,
        order_ledger=ledger,
        dry_run=False,
    )

    assert result.skipped_unknown == ("legacy-order-id",)
    assert broker.canceled == []


def test_deployment_scoped_cancellation_does_not_touch_other_deployments() -> None:
    ledger = OrderLedger()
    order_a = _order(ledger, deployment_id=DEPLOYMENT_A)
    order_b = _order(ledger, deployment_id=DEPLOYMENT_B)
    broker = CancellableBroker(open_orders=(_broker_result(order_a), _broker_result(order_b)))

    result = ControlPlane().cancel_resting_open_orders_without_positions(
        account_id=ACCOUNT_ID,
        broker_adapter=broker,
        order_ledger=ledger,
        scope="deployment",
        deployment_id=DEPLOYMENT_A,
        dry_run=False,
    )

    assert result.canceled == (order_a.client_order_id,)
    assert broker.canceled == [order_a.client_order_id]


def test_dry_run_returns_results_but_does_not_cancel() -> None:
    ledger = OrderLedger()
    order = _order(ledger)
    broker = CancellableBroker(open_orders=(_broker_result(order),))

    result = ControlPlane().cancel_resting_open_orders_without_positions(
        account_id=ACCOUNT_ID,
        broker_adapter=broker,
        order_ledger=ledger,
        dry_run=True,
    )

    assert result.dry_run is True
    assert result.canceled == (order.client_order_id,)
    assert broker.canceled == []

"""P0-3 safety net: BrokerSync.apply_result must cancel OCO sibling on full fill.

Until the AlpacaBrokerAdapter learns native OCO submission, the post-fill
bracket pair is two unlinked broker orders. Without this cancel, a target fill
leaves the stop live; the next stop trigger inverts the position from
long-protected to silently short.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.brokers import BrokerOrderResult, BrokerOrderStatus, BrokerSync
from backend.app.domain import CandidateSide, OrderType, TimeInForce
from backend.app.orders import (
    InternalOrder,
    InternalOrderIntent,
    InternalOrderStatus,
)
from backend.app.orders.ledger import OrderLedger
from backend.app.orders.models import OrderOrigin


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
STRATEGY_ID = UUID("22222222-3333-4444-5555-666666666666")
STRATEGY_VERSION_ID = UUID("33333333-4444-5555-6666-777777777777")
SIGNAL_PLAN_ID = UUID("44444444-5555-6666-7777-888888888888")
POSITION_LINEAGE_ID = UUID("55555555-6666-7777-8888-999999999999")
ACCOUNT_EVAL_ID = UUID("66666666-7777-8888-9999-aaaaaaaaaaaa")
GOVERNOR_DECISION_ID = UUID("77777777-8888-9999-aaaa-bbbbbbbbbbbb")

NOW = datetime(2026, 4, 30, 14, 30, tzinfo=timezone.utc)


def _signal_plan_child(
    *,
    leg_label: str,
    intent: InternalOrderIntent,
    order_type: OrderType,
    side: CandidateSide,
    parent_order_id: UUID,
    order_class: str = "oco",
    limit_price: float | None = None,
    stop_price: float | None = None,
) -> InternalOrder:
    """Build a SignalPlan-origin child order matching post-fill bracket shape."""
    client_order_id = f"sp-{leg_label}-{uuid4().hex[:8]}"
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=client_order_id,
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=STRATEGY_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        signal_plan_id=SIGNAL_PLAN_ID,
        opening_signal_plan_id=SIGNAL_PLAN_ID,
        current_signal_plan_id=SIGNAL_PLAN_ID,
        position_lineage_id=POSITION_LINEAGE_ID,
        account_evaluation_id=ACCOUNT_EVAL_ID,
        governor_decision_id=GOVERNOR_DECISION_ID,
        parent_order_id=parent_order_id,
        order_class=order_class,
        leg_label=leg_label,
        symbol="SPY",
        side=side,
        quantity=10,
        order_type=order_type,
        time_in_force=TimeInForce.DAY,
        limit_price=limit_price,
        stop_price=stop_price,
        intent=intent,
        status=InternalOrderStatus.ACCEPTED,
        created_at=NOW,
        updated_at=NOW,
    )


def _fill_result(order: InternalOrder) -> BrokerOrderResult:
    return BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=BrokerOrderStatus.FILLED,
        broker_order_id=f"broker-{order.client_order_id}",
        broker_status="filled",
        filled_quantity=order.quantity,
        filled_avg_price=110.0,
        remaining_quantity=0,
        raw_status="filled",
    )


def _cancel_result(order: InternalOrder) -> BrokerOrderResult:
    return BrokerOrderResult(
        order_id=order.order_id,
        client_order_id=order.client_order_id,
        status=BrokerOrderStatus.CANCELED,
        broker_order_id=f"broker-{order.client_order_id}",
        broker_status="canceled",
        filled_quantity=0,
        remaining_quantity=order.quantity,
        canceled_at=NOW,
        raw_status="canceled",
    )


class _RecordingAdapter:
    def __init__(self) -> None:
        self.cancel_calls: list[InternalOrder] = []

    def cancel_order(self, order: InternalOrder) -> BrokerOrderResult:
        self.cancel_calls.append(order)
        return _cancel_result(order)

    # Other adapter methods aren't exercised by these tests.
    def submit_order(self, order):  # pragma: no cover
        raise NotImplementedError

    def get_order(self, order):  # pragma: no cover
        raise NotImplementedError

    def cancel_orders(self, account_id, scope):  # pragma: no cover
        raise NotImplementedError

    def replace_order(self, order, new_params):  # pragma: no cover
        raise NotImplementedError

    def list_open_orders(self, account_id):  # pragma: no cover
        return ()

    def get_account_snapshot(self, account_id):  # pragma: no cover
        raise NotImplementedError

    def get_positions(self, account_id):  # pragma: no cover
        return ()


def _seed_oco_pair(
    ledger: OrderLedger,
    *,
    parent_order_id: UUID,
    slice_suffix: str = "@10",
) -> tuple[InternalOrder, InternalOrder]:
    target = _signal_plan_child(
        leg_label=f"target{slice_suffix}",
        intent=InternalOrderIntent.TAKE_PROFIT,
        order_type=OrderType.LIMIT,
        side=CandidateSide.SHORT,
        parent_order_id=parent_order_id,
        limit_price=110.0,
    )
    stop = _signal_plan_child(
        leg_label=f"stop{slice_suffix}",
        intent=InternalOrderIntent.STOP_LOSS,
        order_type=OrderType.STOP,
        side=CandidateSide.SHORT,
        parent_order_id=parent_order_id,
        stop_price=90.0,
    )
    ledger.add(target)
    ledger.add(stop)
    return target, stop


# ── Tests ──────────────────────────────────────────────────────────────────


def test_target_fill_cancels_stop_sibling() -> None:
    ledger = OrderLedger()
    parent = uuid4()
    target, stop = _seed_oco_pair(ledger, parent_order_id=parent)
    adapter = _RecordingAdapter()
    sync = BrokerSync(ledger=ledger, adapter=adapter)

    persisted = sync.apply_result(_fill_result(target))

    assert persisted.status == InternalOrderStatus.FILLED
    assert len(adapter.cancel_calls) == 1
    assert adapter.cancel_calls[0].order_id == stop.order_id
    # Stop's local status now reflects the broker cancel.
    assert ledger.get(stop.order_id).status == InternalOrderStatus.CANCELED


def test_stop_fill_cancels_target_sibling() -> None:
    ledger = OrderLedger()
    parent = uuid4()
    target, stop = _seed_oco_pair(ledger, parent_order_id=parent)
    adapter = _RecordingAdapter()
    sync = BrokerSync(ledger=ledger, adapter=adapter)

    sync.apply_result(_fill_result(stop))

    assert len(adapter.cancel_calls) == 1
    assert adapter.cancel_calls[0].order_id == target.order_id
    assert ledger.get(target.order_id).status == InternalOrderStatus.CANCELED


def test_only_same_slice_sibling_canceled() -> None:
    """Multiple slice pairs may exist on the same parent (incremental
    partial-fill placement). Only the leg sharing the slice suffix is canceled."""
    ledger = OrderLedger()
    parent = uuid4()
    slice_a_target, slice_a_stop = _seed_oco_pair(ledger, parent_order_id=parent, slice_suffix="@5")
    slice_b_target, slice_b_stop = _seed_oco_pair(ledger, parent_order_id=parent, slice_suffix="@10")
    adapter = _RecordingAdapter()
    sync = BrokerSync(ledger=ledger, adapter=adapter)

    sync.apply_result(_fill_result(slice_a_target))

    # Only slice_a_stop is canceled — slice_b pair stays live.
    canceled_ids = {o.order_id for o in adapter.cancel_calls}
    assert canceled_ids == {slice_a_stop.order_id}
    assert ledger.get(slice_b_target.order_id).status == InternalOrderStatus.ACCEPTED
    assert ledger.get(slice_b_stop.order_id).status == InternalOrderStatus.ACCEPTED


def test_partial_fill_does_not_cancel_sibling() -> None:
    ledger = OrderLedger()
    parent = uuid4()
    target, stop = _seed_oco_pair(ledger, parent_order_id=parent)
    adapter = _RecordingAdapter()
    sync = BrokerSync(ledger=ledger, adapter=adapter)

    partial = BrokerOrderResult(
        order_id=target.order_id,
        client_order_id=target.client_order_id,
        status=BrokerOrderStatus.PARTIAL_FILL,
        broker_order_id=f"broker-{target.client_order_id}",
        broker_status="partial_fill",
        filled_quantity=4,
        filled_avg_price=110.0,
        remaining_quantity=6,
        raw_status="partial_fill",
    )

    sync.apply_result(partial)

    # Partial fills do not yet trigger sibling cancel — sibling-resize is a
    # separate concern (P1). Stop remains live until target fully fills.
    assert adapter.cancel_calls == []
    assert ledger.get(stop.order_id).status == InternalOrderStatus.ACCEPTED


def test_re_observation_of_filled_status_does_not_recancel() -> None:
    """Idempotency: if the same FILLED result is replayed (e.g. stream + poll),
    the sibling cancel must fire only once."""
    ledger = OrderLedger()
    parent = uuid4()
    target, stop = _seed_oco_pair(ledger, parent_order_id=parent)
    adapter = _RecordingAdapter()
    sync = BrokerSync(ledger=ledger, adapter=adapter)

    sync.apply_result(_fill_result(target))
    sync.apply_result(_fill_result(target))  # replay

    assert len(adapter.cancel_calls) == 1


def test_no_cancel_when_adapter_unavailable() -> None:
    """Test path with no broker adapter: BrokerSync remains the only writer
    and does not speculatively mutate sibling state."""
    ledger = OrderLedger()
    parent = uuid4()
    target, stop = _seed_oco_pair(ledger, parent_order_id=parent)
    sync = BrokerSync(ledger=ledger, adapter=None)

    sync.apply_result(_fill_result(target))

    # Stop unchanged — no adapter to send cancel to.
    assert ledger.get(stop.order_id).status == InternalOrderStatus.ACCEPTED


def test_non_oco_fill_does_not_touch_other_orders() -> None:
    """Filling a non-OCO order (e.g. the entry parent) must not trigger any
    cancel sweep across the account."""
    ledger = OrderLedger()
    parent = uuid4()
    # Seed an OCO pair, then build an unrelated non-OCO order and fill it.
    _seed_oco_pair(ledger, parent_order_id=parent)
    standalone = _signal_plan_child(
        leg_label=None,  # entry, no leg label
        intent=InternalOrderIntent.OPEN,
        order_type=OrderType.MARKET,
        side=CandidateSide.LONG,
        parent_order_id=parent,
        order_class=None,
    )
    ledger.add(standalone)
    adapter = _RecordingAdapter()
    sync = BrokerSync(ledger=ledger, adapter=adapter)

    sync.apply_result(_fill_result(standalone))

    assert adapter.cancel_calls == []


def test_already_canceled_sibling_skipped() -> None:
    """If the sibling was already canceled (e.g. operator preemptively canceled),
    the fill-driven cancel must not double-cancel."""
    ledger = OrderLedger()
    parent = uuid4()
    target, stop = _seed_oco_pair(ledger, parent_order_id=parent)
    # Operator canceled the stop earlier.
    ledger.replace(stop.model_copy(update={"status": InternalOrderStatus.CANCELED}))
    adapter = _RecordingAdapter()
    sync = BrokerSync(ledger=ledger, adapter=adapter)

    sync.apply_result(_fill_result(target))

    assert adapter.cancel_calls == []

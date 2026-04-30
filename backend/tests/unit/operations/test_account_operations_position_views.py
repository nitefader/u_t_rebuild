"""T-5 (Bracket Program) — Operations protection_status column.

Validates that ``OperationsCenterService.get_account_operations`` ships
``position_views`` with operator-visible ``protection_status`` derived
from the orders ledger:

- ``protected``           — at least one ACCEPTED stop child for the lineage
- ``pending_protection``  — entry filled, stop child only in CREATED state
- ``naked``               — entry filled, no stop children at all
- ``unknown``              — position has no opening_signal_plan_id, or qty=0
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.brokers.models import (
    BrokerPositionSide,
    BrokerPositionSnapshot,
)
from backend.app.operations.service import OperationsCenterService
from backend.app.orders import InternalOrder, OrderManager
from backend.app.orders.ledger import OrderLedger
from backend.app.orders.models import (
    InternalOrderIntent,
    InternalOrderStatus,
    OrderOrigin,
)
from backend.app.domain import (
    CandidateSide,
    OrderType,
    TimeInForce,
)


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
DEPLOYMENT_ID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
STRATEGY_ID = UUID("22222222-3333-4444-5555-666666666666")
STRATEGY_VERSION_ID = UUID("33333333-4444-5555-6666-777777777777")
NOW = datetime(2026, 4, 30, 14, 30, tzinfo=timezone.utc)


def _entry_order(*, status: InternalOrderStatus, opening_signal_plan_id: UUID, position_lineage_id: UUID) -> InternalOrder:
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=f"entry-{uuid4()}",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=STRATEGY_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        signal_plan_id=opening_signal_plan_id,
        opening_signal_plan_id=opening_signal_plan_id,
        current_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        lifecycle_intent="open",
        symbol="SPY",
        side=CandidateSide.LONG,
        quantity=10,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _stop_child(*, parent_order_id: UUID, opening_signal_plan_id: UUID, position_lineage_id: UUID, status: InternalOrderStatus) -> InternalOrder:
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=f"stop-{uuid4()}",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=STRATEGY_ID,
        strategy_version_id=STRATEGY_VERSION_ID,
        signal_plan_id=opening_signal_plan_id,
        opening_signal_plan_id=opening_signal_plan_id,
        current_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        parent_order_id=parent_order_id,
        order_class="oco",
        leg_label="stop@10",
        lifecycle_intent="stop_loss",
        symbol="SPY",
        side=CandidateSide.SHORT,
        quantity=10,
        order_type=OrderType.STOP,
        stop_price=95.0,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.STOP_LOSS,
        status=status,
        created_at=NOW,
        updated_at=NOW,
    )


def _position(*, opening_signal_plan_id: UUID | None, position_lineage_id: UUID | None, qty: float = 10) -> BrokerPositionSnapshot:
    return BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=qty,
        side=BrokerPositionSide.LONG,
        avg_entry_price=100,
        market_value=qty * 100,
        timestamp=NOW,
        deployment_id=DEPLOYMENT_ID,
        strategy_id=STRATEGY_ID,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
    )


def test_position_view_marks_protected_when_active_stop_child_exists() -> None:
    opening = uuid4()
    lineage = uuid4()
    entry = _entry_order(status=InternalOrderStatus.FILLED, opening_signal_plan_id=opening, position_lineage_id=lineage)
    stop = _stop_child(parent_order_id=entry.order_id, opening_signal_plan_id=opening, position_lineage_id=lineage, status=InternalOrderStatus.ACCEPTED)
    position = _position(opening_signal_plan_id=opening, position_lineage_id=lineage)

    views = OperationsCenterService._position_views(positions=(position,), orders=(entry, stop))

    assert len(views) == 1
    view = views[0]
    assert view.protection_status == "protected"
    assert view.protective_order_count == 1
    assert view.snapshot is position


def test_position_view_marks_naked_when_entry_filled_and_no_stop_children() -> None:
    opening = uuid4()
    lineage = uuid4()
    entry = _entry_order(status=InternalOrderStatus.FILLED, opening_signal_plan_id=opening, position_lineage_id=lineage)
    position = _position(opening_signal_plan_id=opening, position_lineage_id=lineage)

    views = OperationsCenterService._position_views(positions=(position,), orders=(entry,))

    assert len(views) == 1
    assert views[0].protection_status == "naked"
    assert views[0].protective_order_count == 0


def test_position_view_marks_pending_when_stop_child_only_created() -> None:
    opening = uuid4()
    lineage = uuid4()
    entry = _entry_order(status=InternalOrderStatus.FILLED, opening_signal_plan_id=opening, position_lineage_id=lineage)
    stop = _stop_child(parent_order_id=entry.order_id, opening_signal_plan_id=opening, position_lineage_id=lineage, status=InternalOrderStatus.CREATED)
    position = _position(opening_signal_plan_id=opening, position_lineage_id=lineage)

    views = OperationsCenterService._position_views(positions=(position,), orders=(entry, stop))

    assert views[0].protection_status == "pending_protection"
    assert views[0].protective_order_count == 0


def test_position_view_marks_unknown_when_position_has_no_lineage() -> None:
    position = _position(opening_signal_plan_id=None, position_lineage_id=None)

    views = OperationsCenterService._position_views(positions=(position,), orders=())

    assert views[0].protection_status == "unknown"
    assert views[0].protective_order_count == 0


def test_position_view_marks_unknown_when_position_qty_is_zero() -> None:
    opening = uuid4()
    lineage = uuid4()
    position = _position(opening_signal_plan_id=opening, position_lineage_id=lineage, qty=0)

    views = OperationsCenterService._position_views(positions=(position,), orders=())

    assert views[0].protection_status == "unknown"


def test_position_view_marks_unknown_when_entry_not_filled() -> None:
    opening = uuid4()
    lineage = uuid4()
    entry = _entry_order(status=InternalOrderStatus.ACCEPTED, opening_signal_plan_id=opening, position_lineage_id=lineage)
    position = _position(opening_signal_plan_id=opening, position_lineage_id=lineage)

    views = OperationsCenterService._position_views(positions=(position,), orders=(entry,))

    # Entry hasn't filled yet, but position exists with qty>0 — broker
    # truth says we hold shares, ledger says entry not filled. This is
    # a stale-state mismatch (BrokerSync race window). Treat as unknown
    # rather than naked so the operator doesn't see a false alarm during
    # the BrokerSync refresh window.
    assert views[0].protection_status == "unknown"

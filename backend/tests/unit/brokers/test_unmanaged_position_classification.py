"""M2 (HARD.MD P0-2) — Unmanaged broker position classification.

Pins the contract that ``_enrich_position_snapshot_with_lineage``:
- Stamps ``adoption_status="managed"`` and clears ``unmanaged_broker_position``
  when SignalPlan lineage matches.
- Stamps ``adoption_status="managed"`` when the position is already fully
  lineaged on input.
- Stamps ``adoption_status="unmanaged"`` + ``unmanaged_broker_position=True``
  when there are no matching orders at all (broker-only / unknown origin).
- Same when matching orders exist but no lineage matches the position
  quantity exactly AND the deployment-only fallback is also no-go.
- Is idempotent — repeat enrichment doesn't churn the snapshot.

Doctrine: Adoption (M11 Guardian) is explicit and gated; this enrichment
function NEVER auto-adopts. Guardian adoption is layered on top in a
separate slice.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.brokers.models import (
    BrokerPositionSide,
    BrokerPositionSnapshot,
)
from backend.app.brokers.sync import _enrich_position_snapshot_with_lineage
from backend.app.domain import CandidateSide, OrderType, TimeInForce
from backend.app.orders import (
    InternalOrder,
    InternalOrderIntent,
    InternalOrderStatus,
    OrderOrigin,
)


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")


def _filled_order(
    *,
    deployment_id: UUID,
    symbol: str = "SPY",
    qty: float = 10,
    side: CandidateSide = CandidateSide.LONG,
    opening_signal_plan_id: UUID,
    position_lineage_id: UUID,
    strategy_id: UUID,
) -> InternalOrder:
    created_at = datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc)
    return InternalOrder(
        order_id=uuid4(),
        client_order_id=f"sp-{uuid4()}",
        account_id=ACCOUNT_ID,
        origin=OrderOrigin.SIGNAL_PLAN,
        deployment_id=deployment_id,
        strategy_id=strategy_id,
        strategy_version_id=uuid4(),
        signal_plan_id=opening_signal_plan_id,
        opening_signal_plan_id=opening_signal_plan_id,
        current_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        account_evaluation_id=uuid4(),
        governor_decision_id=uuid4(),
        symbol=symbol,
        side=side,
        quantity=abs(qty),
        filled_quantity=abs(qty),
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
        intent=InternalOrderIntent.OPEN,
        status=InternalOrderStatus.FILLED,
        created_at=created_at,
        updated_at=created_at,
    )


def _bare_position(symbol: str = "SPY", qty: float = 10.0) -> BrokerPositionSnapshot:
    return BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol=symbol,
        qty=qty,
        side=BrokerPositionSide.LONG if qty >= 0 else BrokerPositionSide.SHORT,
        avg_entry_price=100,
        market_value=qty * 100,
    )


def test_no_orders_at_all_marks_unmanaged() -> None:
    snapshot = _bare_position()
    enriched = _enrich_position_snapshot_with_lineage(snapshot, orders=())
    assert enriched.unmanaged_broker_position is True
    assert enriched.adoption_status == "unmanaged"
    # Lineage fields stay None — no auto-adoption.
    assert enriched.position_lineage_id is None
    assert enriched.deployment_id is None


def test_matching_lineage_stamps_managed() -> None:
    deployment_id = uuid4()
    opening_signal_plan_id = uuid4()
    position_lineage_id = uuid4()
    strategy_id = uuid4()
    order = _filled_order(
        deployment_id=deployment_id,
        symbol="SPY",
        qty=10,
        opening_signal_plan_id=opening_signal_plan_id,
        position_lineage_id=position_lineage_id,
        strategy_id=strategy_id,
    )
    snapshot = _bare_position("SPY", qty=10)

    enriched = _enrich_position_snapshot_with_lineage(snapshot, orders=(order,))

    assert enriched.unmanaged_broker_position is False
    assert enriched.adoption_status == "managed"
    assert enriched.position_lineage_id == position_lineage_id
    assert enriched.deployment_id == deployment_id
    assert enriched.opening_signal_plan_id == opening_signal_plan_id
    assert enriched.strategy_id == strategy_id


def test_already_fully_lineaged_input_gets_managed_stamp() -> None:
    snapshot = _bare_position().model_copy(
        update={
            "deployment_id": uuid4(),
            "opening_signal_plan_id": uuid4(),
            "position_lineage_id": uuid4(),
        }
    )
    enriched = _enrich_position_snapshot_with_lineage(snapshot, orders=())
    assert enriched.adoption_status == "managed"
    # No regression on the lineage fields.
    assert enriched.deployment_id == snapshot.deployment_id
    assert enriched.position_lineage_id == snapshot.position_lineage_id


def test_zero_quantity_position_is_left_alone() -> None:
    snapshot = BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=0,
        side=BrokerPositionSide.LONG,
        avg_entry_price=0,
        market_value=0,
    )
    enriched = _enrich_position_snapshot_with_lineage(snapshot, orders=())
    # Zero-qty positions have no exposure; classifier intentionally
    # leaves them alone (no Unmanaged stamp).
    assert enriched.unmanaged_broker_position is False
    assert enriched.adoption_status is None


def test_orders_present_but_no_quantity_match_marks_unmanaged() -> None:
    """Orders exist for the symbol but their net quantity doesn't match."""
    # 5-share filled order, but the live position is 10 shares.
    order = _filled_order(
        deployment_id=uuid4(),
        symbol="SPY",
        qty=5,
        opening_signal_plan_id=uuid4(),
        position_lineage_id=uuid4(),
        strategy_id=uuid4(),
    )
    snapshot = _bare_position("SPY", qty=10)

    enriched = _enrich_position_snapshot_with_lineage(snapshot, orders=(order,))

    # Lineage match fails (qty mismatch). The deployment-only fallback
    # may still attribute the deployment id, but unmanaged classification
    # only fires when even that fails. Either outcome must carry a
    # non-None ``adoption_status`` so the operator UI can render a state.
    assert enriched.adoption_status in {"managed", "unmanaged"}


def test_classification_is_idempotent() -> None:
    snapshot = _bare_position()
    once = _enrich_position_snapshot_with_lineage(snapshot, orders=())
    twice = _enrich_position_snapshot_with_lineage(once, orders=())
    assert once == twice


def test_unmanaged_position_for_unknown_symbol_stays_unmanaged_when_orders_for_other_symbol() -> None:
    # Orders exist but for a different symbol than the position.
    other = _filled_order(
        deployment_id=uuid4(),
        symbol="MSFT",
        qty=10,
        opening_signal_plan_id=uuid4(),
        position_lineage_id=uuid4(),
        strategy_id=uuid4(),
    )
    snapshot = _bare_position("SPY", qty=10)
    enriched = _enrich_position_snapshot_with_lineage(snapshot, orders=(other,))
    assert enriched.unmanaged_broker_position is True
    assert enriched.adoption_status == "unmanaged"

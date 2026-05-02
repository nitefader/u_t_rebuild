"""M11 Guardian adoption pathway — pure unit tests.

Pins the four-case logic from plan FR11.4 + the
``position_has_active_protective_orders`` helper:

  Case 1: Healthy owner → no change.
  Case 2: Orphan (no lineage) + healthy Guardian → adopt with owner_unknown.
  Case 3: Owner unhealthy + position UNPROTECTED + healthy Guardian distinct
          from owner → adopt with owner_deployment_down_unprotected.
  Case 4: Owner unhealthy + position SELF-PROTECTED → do NOT adopt; surface
          owner_deployment_healthy=False + owner_self_protected=True.

Invariant: a position already adopted by Guardian never auto-reverts
(FR11.5 one-way).

The functions under test are PURE — all inputs are explicit. The caller
resolves Guardian/owner health from `deployments/health.py` and passes
open_orders from the BrokerSync cache.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from backend.app.brokers.models import (
    BrokerOpenOrderSnapshot,
    BrokerOrderStatus,
    BrokerPositionSide,
    BrokerPositionSnapshot,
)
from backend.app.brokers.sync import (
    apply_guardian_adoption,
    position_has_active_protective_orders,
)


ACCOUNT_ID = UUID("11111111-2222-3333-4444-555555555555")
OWNER_DEPLOYMENT_ID = UUID("aaaaaaaa-1111-2222-3333-444444444444")
GUARDIAN_DEPLOYMENT_ID = UUID("bbbbbbbb-1111-2222-3333-444444444444")


def _position(
    *,
    qty: float = 10.0,
    deployment_id: UUID | None = None,
    deployment_name: str | None = None,
    position_lineage_id: UUID | None = None,
    adoption_status: str | None = None,
    unmanaged: bool = False,
) -> BrokerPositionSnapshot:
    return BrokerPositionSnapshot(
        account_id=ACCOUNT_ID,
        symbol="SPY",
        qty=qty,
        side=BrokerPositionSide.LONG if qty >= 0 else BrokerPositionSide.SHORT,
        avg_entry_price=100.0,
        market_value=qty * 100,
        deployment_id=deployment_id,
        deployment_name=deployment_name,
        position_lineage_id=position_lineage_id,
        adoption_status=adoption_status,  # type: ignore[arg-type]
        unmanaged_broker_position=unmanaged,
    )


def _stop_order(
    *,
    side: str = "sell",
    qty: float = 10,
    filled_qty: float = 0,
    order_type: str = "stop",
    symbol: str = "SPY",
) -> BrokerOpenOrderSnapshot:
    return BrokerOpenOrderSnapshot(
        account_id=ACCOUNT_ID,
        broker_order_id=f"bo-{uuid4()}",
        client_order_id=f"sp-{uuid4()}",
        symbol=symbol,
        side=side,
        qty=qty,
        filled_qty=filled_qty,
        status=BrokerOrderStatus.ACCEPTED,
        order_type=order_type,
        timestamp=datetime(2026, 5, 2, 14, 30, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# position_has_active_protective_orders
# ---------------------------------------------------------------------------


def test_self_protected_long_with_full_qty_sell_stop_returns_true() -> None:
    pos = _position(qty=10)
    orders = (_stop_order(side="sell", qty=10, order_type="stop"),)
    assert position_has_active_protective_orders(pos, orders) is True


def test_self_protected_long_with_partial_sell_stop_returns_false() -> None:
    pos = _position(qty=10)
    orders = (_stop_order(side="sell", qty=5, order_type="stop"),)
    assert position_has_active_protective_orders(pos, orders) is False


def test_self_protected_long_with_buy_stop_does_not_count() -> None:
    pos = _position(qty=10)
    orders = (_stop_order(side="buy", qty=10, order_type="stop"),)
    assert position_has_active_protective_orders(pos, orders) is False


def test_self_protected_short_with_full_qty_buy_stop_limit_returns_true() -> None:
    pos = _position(qty=-10)
    orders = (_stop_order(side="buy", qty=10, order_type="stop_limit"),)
    assert position_has_active_protective_orders(pos, orders) is True


def test_self_protected_long_with_sell_limit_target_does_not_count() -> None:
    pos = _position(qty=10)
    orders = (_stop_order(side="sell", qty=10, order_type="limit"),)
    assert position_has_active_protective_orders(pos, orders) is False


def test_self_protected_long_with_trailing_stop_returns_true() -> None:
    pos = _position(qty=10)
    orders = (_stop_order(side="sell", qty=10, order_type="trailing_stop"),)
    assert position_has_active_protective_orders(pos, orders) is True


def test_self_protected_no_open_orders_returns_false() -> None:
    pos = _position(qty=10)
    assert position_has_active_protective_orders(pos, ()) is False


def test_self_protected_zero_qty_position_returns_false() -> None:
    pos = _position(qty=0)
    orders = (_stop_order(side="sell", qty=10, order_type="stop"),)
    assert position_has_active_protective_orders(pos, orders) is False


def test_self_protected_other_symbol_orders_ignored() -> None:
    pos = _position(qty=10)
    orders = (_stop_order(side="sell", qty=10, order_type="stop", symbol="MSFT"),)
    assert position_has_active_protective_orders(pos, orders) is False


def test_self_protected_remaining_qty_used_not_full_qty() -> None:
    pos = _position(qty=10)
    # 12-share stop already partially filled by 5 → only 7 shares of cover.
    orders = (_stop_order(side="sell", qty=12, filled_qty=5, order_type="stop"),)
    assert position_has_active_protective_orders(pos, orders) is False


# ---------------------------------------------------------------------------
# apply_guardian_adoption — Case 1: Healthy owner
# ---------------------------------------------------------------------------


def test_case1_healthy_owner_no_change() -> None:
    pos = _position(
        qty=10,
        deployment_id=OWNER_DEPLOYMENT_ID,
        deployment_name="Owner Strat",
        position_lineage_id=uuid4(),
        adoption_status="managed",
    )
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=GUARDIAN_DEPLOYMENT_ID,
        guardian_deployment_name="Guardian C",
        is_guardian_healthy=True,
        is_owner_healthy=True,
        open_orders=(),
    )
    assert enriched == pos


# ---------------------------------------------------------------------------
# apply_guardian_adoption — Case 2: Orphan + healthy Guardian → adopt
# ---------------------------------------------------------------------------


def test_case2_orphan_with_healthy_guardian_is_adopted_owner_unknown() -> None:
    pos = _position(qty=10, unmanaged=True, adoption_status="unmanaged")
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=GUARDIAN_DEPLOYMENT_ID,
        guardian_deployment_name="Guardian C",
        is_guardian_healthy=True,
        is_owner_healthy=None,  # no owner to be healthy
        open_orders=(),
    )
    assert enriched.adoption_status == "adopted_by_guardian"
    assert enriched.adoption_reason == "owner_unknown"
    assert enriched.deployment_id == GUARDIAN_DEPLOYMENT_ID
    assert enriched.deployment_name == "Guardian C"
    assert enriched.original_owner_deployment_id is None
    assert enriched.unmanaged_broker_position is False


def test_case2_orphan_with_unhealthy_guardian_stays_unmanaged() -> None:
    pos = _position(qty=10, unmanaged=True, adoption_status="unmanaged")
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=GUARDIAN_DEPLOYMENT_ID,
        guardian_deployment_name="Guardian C",
        is_guardian_healthy=False,
        is_owner_healthy=None,
        open_orders=(),
    )
    assert enriched == pos


def test_case2_no_guardian_set_stays_unmanaged() -> None:
    pos = _position(qty=10, unmanaged=True, adoption_status="unmanaged")
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=None,
        guardian_deployment_name=None,
        is_guardian_healthy=False,
        is_owner_healthy=None,
        open_orders=(),
    )
    assert enriched == pos


# ---------------------------------------------------------------------------
# apply_guardian_adoption — Case 3: Owner down + UNPROTECTED → adopt
# ---------------------------------------------------------------------------


def test_case3_owner_down_unprotected_adopted_with_lineage_preserved() -> None:
    lineage = uuid4()
    pos = _position(
        qty=10,
        deployment_id=OWNER_DEPLOYMENT_ID,
        deployment_name="Owner Strat",
        position_lineage_id=lineage,
        adoption_status="managed",
    )
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=GUARDIAN_DEPLOYMENT_ID,
        guardian_deployment_name="Guardian C",
        is_guardian_healthy=True,
        is_owner_healthy=False,
        open_orders=(),  # no protective orders
    )
    assert enriched.adoption_status == "adopted_by_guardian"
    assert enriched.adoption_reason == "owner_deployment_down_unprotected"
    assert enriched.deployment_id == GUARDIAN_DEPLOYMENT_ID
    assert enriched.deployment_name == "Guardian C"
    assert enriched.original_owner_deployment_id == OWNER_DEPLOYMENT_ID
    assert enriched.original_owner_deployment_name == "Owner Strat"
    assert enriched.owner_deployment_healthy is False
    assert enriched.owner_self_protected is False
    assert enriched.position_lineage_id == lineage  # lineage preserved


def test_case3_guardian_equals_owner_does_not_self_adopt() -> None:
    pos = _position(
        qty=10,
        deployment_id=OWNER_DEPLOYMENT_ID,
        deployment_name="Owner Strat",
        position_lineage_id=uuid4(),
        adoption_status="managed",
    )
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=OWNER_DEPLOYMENT_ID,  # same as owner
        guardian_deployment_name="Owner Strat",
        is_guardian_healthy=True,
        is_owner_healthy=False,
        open_orders=(),
    )
    assert enriched.adoption_status != "adopted_by_guardian"
    assert enriched.deployment_id == OWNER_DEPLOYMENT_ID  # unchanged
    assert enriched.owner_deployment_healthy is False


# ---------------------------------------------------------------------------
# apply_guardian_adoption — Case 4: Owner down + SELF-PROTECTED → no adopt
# ---------------------------------------------------------------------------


def test_case4_owner_down_self_protected_does_not_adopt() -> None:
    pos = _position(
        qty=10,
        deployment_id=OWNER_DEPLOYMENT_ID,
        deployment_name="Owner Strat",
        position_lineage_id=uuid4(),
        adoption_status="managed",
    )
    orders = (_stop_order(side="sell", qty=10, order_type="stop"),)
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=GUARDIAN_DEPLOYMENT_ID,
        guardian_deployment_name="Guardian C",
        is_guardian_healthy=True,
        is_owner_healthy=False,
        open_orders=orders,
    )
    assert enriched.adoption_status != "adopted_by_guardian"
    assert enriched.deployment_id == OWNER_DEPLOYMENT_ID  # unchanged
    assert enriched.owner_deployment_healthy is False
    assert enriched.owner_self_protected is True


def test_case4_no_guardian_owner_down_self_protected_still_records_state() -> None:
    pos = _position(
        qty=10,
        deployment_id=OWNER_DEPLOYMENT_ID,
        deployment_name="Owner Strat",
        position_lineage_id=uuid4(),
        adoption_status="managed",
    )
    orders = (_stop_order(side="sell", qty=10, order_type="stop"),)
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=None,
        guardian_deployment_name=None,
        is_guardian_healthy=False,
        is_owner_healthy=False,
        open_orders=orders,
    )
    # Even without a Guardian, the operator UI needs to know the owner is
    # down and the position is self-protected — surface the state.
    assert enriched.owner_deployment_healthy is False
    assert enriched.owner_self_protected is True
    assert enriched.adoption_status == "managed"  # unchanged


# ---------------------------------------------------------------------------
# FR11.5 one-way invariant
# ---------------------------------------------------------------------------


def test_one_way_already_adopted_position_not_re_processed() -> None:
    pos = _position(
        qty=10,
        deployment_id=GUARDIAN_DEPLOYMENT_ID,
        deployment_name="Guardian C",
        position_lineage_id=uuid4(),
        adoption_status="adopted_by_guardian",
    )
    # Even with the original owner now reported healthy, no auto-revert.
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=GUARDIAN_DEPLOYMENT_ID,
        guardian_deployment_name="Guardian C",
        is_guardian_healthy=True,
        is_owner_healthy=True,
        open_orders=(),
    )
    assert enriched == pos


# ---------------------------------------------------------------------------
# Zero-qty short-circuit
# ---------------------------------------------------------------------------


def test_zero_qty_position_is_left_alone_by_guardian_pathway() -> None:
    pos = _position(qty=0)
    enriched = apply_guardian_adoption(
        pos,
        guardian_deployment_id=GUARDIAN_DEPLOYMENT_ID,
        guardian_deployment_name="Guardian C",
        is_guardian_healthy=True,
        is_owner_healthy=False,
        open_orders=(),
    )
    assert enriched == pos

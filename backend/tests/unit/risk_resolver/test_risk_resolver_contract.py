from __future__ import annotations

from uuid import uuid4

from backend.app.domain import (
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanRunner,
    SignalPlanSide,
    SignalPlanStop,
    SignalPlanTarget,
)
from backend.app.risk_resolver import LifecycleSizingInput, RiskResolver, StaticSizingInput


def _open_plan(*, multileg: bool = False) -> SignalPlan:
    return SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(),
        stop=SignalPlanStop(type="fixed", stop_price=95, required=True) if multileg else None,
        targets=(
            SignalPlanTarget(label="T1", quantity_pct=25, price=105),
            SignalPlanTarget(label="T2", quantity_pct=30, price=110),
            SignalPlanTarget(label="T3", quantity_pct=15, price=115),
        )
        if multileg
        else (),
        runner=SignalPlanRunner(quantity_pct=30) if multileg else None,
    )


def _open_plan_with_targets(*, targets: tuple[SignalPlanTarget, ...]) -> SignalPlan:
    return SignalPlan(
        signal_plan_id=uuid4(),
        deployment_id=uuid4(),
        strategy_id=uuid4(),
        strategy_version_id=uuid4(),
        symbol="SPY",
        side=SignalPlanSide.LONG,
        intent=SignalPlanIntent.OPEN,
        entry=SignalPlanEntry(),
        stop=SignalPlanStop(type="fixed", stop_price=95, required=True),
        targets=targets,
    )


def test_risk_resolver_is_first_quantity_boundary_for_signal_plan() -> None:
    account_id = uuid4()
    plan = _open_plan()

    result = RiskResolver().resolve_static(
        account_id=account_id,
        signal_plan=plan,
        sizing=StaticSizingInput(quantity=10, max_loss=100),
    )

    assert result.allowed is True
    assert result.account_id == account_id
    assert result.signal_plan_id == plan.signal_plan_id
    assert result.resolved_quantity == 10


def test_risk_resolver_rejects_missing_account_size() -> None:
    result = RiskResolver().resolve_static(
        account_id=uuid4(),
        signal_plan=_open_plan(),
        sizing=StaticSizingInput(),
    )

    assert result.allowed is False
    assert "missing_account_size" in result.violations


def test_lifecycle_allocation_resolves_total_risk_then_exact_fractional_legs() -> None:
    result = RiskResolver().resolve_lifecycle(
        account_id=uuid4(),
        signal_plan=_open_plan(multileg=True),
        sizing=LifecycleSizingInput(quantity=37, fractional_quantity_allowed=True),
    )

    allocations = {allocation.leg_label: allocation for allocation in result.leg_allocations}
    assert result.resolved_quantity == 37
    assert result.fractional_quantity_allowed is True
    assert allocations["entry"].resolved_quantity == 37
    assert allocations["stop"].resolved_quantity == 37
    assert allocations["T1"].resolved_quantity == 9.25
    assert allocations["T2"].resolved_quantity == 11.1
    assert allocations["T3"].resolved_quantity == 5.55
    assert allocations["runner"].resolved_quantity == 11.1


def test_lifecycle_allocation_floors_targets_and_assigns_remainder_to_runner_for_whole_shares() -> None:
    result = RiskResolver().resolve_lifecycle(
        account_id=uuid4(),
        signal_plan=_open_plan(multileg=True),
        sizing=LifecycleSizingInput(quantity=37, fractional_quantity_allowed=False),
    )

    allocations = {allocation.leg_label: allocation for allocation in result.leg_allocations}
    assert result.resolved_quantity == 37
    assert result.fractional_quantity_allowed is False
    assert result.quantity_rounding_policy == "floor_targets_remainder_to_runner"
    assert allocations["T1"].resolved_quantity == 9
    assert allocations["T2"].resolved_quantity == 11
    assert allocations["T3"].resolved_quantity == 5
    assert allocations["runner"].resolved_quantity == 12
    assert (
        allocations["T1"].resolved_quantity
        + allocations["T2"].resolved_quantity
        + allocations["T3"].resolved_quantity
        + allocations["runner"].resolved_quantity
    ) == 37


def test_lifecycle_allocation_assigns_whole_share_remainder_to_final_target_when_targets_cover_full_plan() -> None:
    result = RiskResolver().resolve_lifecycle(
        account_id=uuid4(),
        signal_plan=_open_plan_with_targets(
            targets=(
                SignalPlanTarget(label="T1", quantity_pct=33),
                SignalPlanTarget(label="T2", quantity_pct=33),
                SignalPlanTarget(label="T3", quantity_pct=34),
            )
        ),
        sizing=LifecycleSizingInput(quantity=37.8, fractional_quantity_allowed=False),
    )

    allocations = {allocation.leg_label: allocation for allocation in result.leg_allocations}
    assert result.resolved_quantity == 37
    assert allocations["T1"].resolved_quantity == 12
    assert allocations["T2"].resolved_quantity == 12
    assert allocations["T3"].resolved_quantity == 13
    assert (
        allocations["T1"].resolved_quantity
        + allocations["T2"].resolved_quantity
        + allocations["T3"].resolved_quantity
    ) == result.resolved_quantity
    assert "unallocated_quantity_after_lifecycle_allocation" not in result.warnings


def test_lifecycle_allocation_warns_when_plan_leaves_open_quantity_without_runner() -> None:
    result = RiskResolver().resolve_lifecycle(
        account_id=uuid4(),
        signal_plan=_open_plan_with_targets(
            targets=(
                SignalPlanTarget(label="T1", quantity_pct=25),
                SignalPlanTarget(label="T2", quantity_pct=25),
            )
        ),
        sizing=LifecycleSizingInput(quantity=20, fractional_quantity_allowed=False),
    )

    assert "unallocated_quantity_after_lifecycle_allocation" in result.warnings

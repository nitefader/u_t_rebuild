from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Protocol
from uuid import UUID, uuid4

from backend.app.domain import (
    RiskCalculationStep,
    RiskDecisionCard,
    RiskDecisionMode,
    RiskDecisionStatus,
    RiskResolvedLegAllocation,
    RiskResolverResult,
    SignalPlan,
    SignalPlanIntent,
    SignalPlanSide,
)
from backend.app.domain._base import utc_now
from backend.app.domain.risk_profile import PositionSizingMethod, RiskProfileVersion


RISK_RESOLVER_VERSION = "risk_resolver/v1"


@dataclass(frozen=True)
class AccountStateSnapshot:
    """Inputs RiskResolver needs to write the account-state portion of a card."""

    account_equity: float
    account_cash: float
    buying_power: float
    existing_position_quantity: float = 0
    existing_position_notional: float = 0
    existing_open_orders_count: int = 0
    existing_open_order_notional: float = 0
    account_id: UUID | None = None
    simulated_account_id: UUID | None = None


class RiskDecisionCardSink(Protocol):
    """Persistence target for emitted RiskDecisionCards."""

    def save_risk_decision_card(self, card: RiskDecisionCard) -> RiskDecisionCard: ...


class RiskResolverError(ValueError):
    """Raised when Account-specific risk cannot be resolved safely."""


@dataclass(frozen=True)
class StaticSizingInput:
    """Temporary sizing input for compatibility callers.

    This keeps the first quantity-producing boundary explicit without forcing the
    whole runtime refactor in the same slice.
    """

    quantity: float | None = None
    notional: float | None = None
    max_loss: float | None = None
    buying_power_required: float | None = None


@dataclass(frozen=True)
class LifecycleSizingInput(StaticSizingInput):
    """Account-specific sizing and quantity capability for a SignalPlan lifecycle."""

    fractional_quantity_allowed: bool = True
    whole_share_rounding: str = "floor_targets_remainder_to_runner"


@dataclass(frozen=True)
class AccountRiskSizingInput:
    """Inputs RiskResolver needs to become the first quantity boundary."""

    risk_profile: RiskProfileVersion
    price: float
    initial_cash: float
    stop_candidate: float | None = None
    fractional_quantity_allowed: bool = True
    whole_share_rounding: str = "floor_targets_remainder_to_runner"


class RiskResolver:
    """Account-specific SignalPlan risk resolver.

    SignalPlan stays neutral. This service is the first place final Account
    quantity or notional may appear.
    """

    def resolve_static(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        sizing: StaticSizingInput,
        existing_position_context: dict[str, object] | None = None,
    ) -> RiskResolverResult:
        if sizing.quantity is None and sizing.notional is None:
            return RiskResolverResult(
                account_id=account_id,
                signal_plan_id=signal_plan.signal_plan_id,
                allowed=False,
                violations=("missing_account_size",),
            )
        if signal_plan.intent == SignalPlanIntent.OPEN and signal_plan.entry is None:
            return RiskResolverResult(
                account_id=account_id,
                signal_plan_id=signal_plan.signal_plan_id,
                allowed=False,
                violations=("opening_signal_plan_missing_entry",),
            )
        return RiskResolverResult(
            account_id=account_id,
            signal_plan_id=signal_plan.signal_plan_id,
            allowed=True,
            resolved_quantity=sizing.quantity,
            resolved_notional=sizing.notional,
            max_loss=sizing.max_loss,
            buying_power_required=sizing.buying_power_required,
            existing_position_context=existing_position_context or {},
        )

    def resolve_lifecycle(
        self,
        *,
        account_id: UUID,
        signal_plan: SignalPlan,
        sizing: LifecycleSizingInput,
        existing_position_context: dict[str, object] | None = None,
    ) -> RiskResolverResult:
        base_result = self.resolve_static(
            account_id=account_id,
            signal_plan=signal_plan,
            sizing=sizing,
            existing_position_context=existing_position_context,
        )
        if not base_result.allowed or sizing.quantity is None:
            return base_result
        allocations = self._allocate_signal_plan_legs(signal_plan=signal_plan, sizing=sizing)
        resolved_quantity = self._round_quantity(
            sizing.quantity,
            fractional_allowed=sizing.fractional_quantity_allowed,
        )
        warnings = tuple(
            warning
            for warning in (
                *base_result.warnings,
                *self._allocation_warnings(signal_plan=signal_plan, total=resolved_quantity, allocations=allocations),
            )
        )
        return base_result.model_copy(
            update={
                "resolved_quantity": resolved_quantity,
                "leg_allocations": allocations,
                "fractional_quantity_allowed": sizing.fractional_quantity_allowed,
                "quantity_rounding_policy": sizing.whole_share_rounding if not sizing.fractional_quantity_allowed else "fractional_exact",
                "warnings": warnings,
            }
        )

    def decide(
        self,
        *,
        mode: RiskDecisionMode | str,
        run_id: UUID,
        signal_plan: SignalPlan,
        risk_plan_version: RiskProfileVersion,
        account_state: AccountStateSnapshot,
        current_price: float,
        stop_candidate: float | None = None,
        candidate_trade_intent_id: UUID | None = None,
        feature_snapshot_id: UUID | None = None,
        session_id: UUID | None = None,
        deployment_id: UUID | None = None,
        fractional_quantity_allowed: bool = True,
        whole_share_rounding: str = "floor",
        sink: RiskDecisionCardSink | None = None,
        exit_quantity_pct: float | None = None,
    ) -> RiskDecisionCard:
        """Emit a traceable RiskDecisionCard for a SignalPlan.

        RiskPlan belongs to the Account or selected research run. SignalPlan
        describes the proposed lifecycle action. RiskResolver combines the
        SignalPlan, RiskPlan, and current account or simulated account state to
        produce a RiskDecisionCard. No simulated or real order may be created
        without that RiskDecisionCard.
        """
        if current_price <= 0:
            raise RiskResolverError("current_price must be positive")
        normalized_mode = RiskDecisionMode(mode) if isinstance(mode, str) else mode

        # Exit-intent path: size from the existing position, not from the
        # RiskPlan's open-side sizing method. Doctrine: ``logical_exit`` is the
        # only exit intent — close, reduce, target, stop, trail, breakeven, and
        # runner all read from existing_position_quantity.
        if signal_plan.intent != SignalPlanIntent.OPEN:
            return self._decide_exit(
                signal_plan=signal_plan,
                risk_plan_version=risk_plan_version,
                account_state=account_state,
                current_price=current_price,
                stop_candidate=stop_candidate,
                candidate_trade_intent_id=candidate_trade_intent_id,
                feature_snapshot_id=feature_snapshot_id,
                session_id=session_id,
                deployment_id=deployment_id,
                fractional_quantity_allowed=fractional_quantity_allowed,
                whole_share_rounding=whole_share_rounding,
                sink=sink,
                normalized_mode=normalized_mode,
                run_id=run_id,
                exit_quantity_pct=exit_quantity_pct,
            )

        steps: list[RiskCalculationStep] = []
        constraints: list[str] = []
        warnings: list[str] = []

        sizing_method = risk_plan_version.sizing_method
        formula_used, raw_quantity, sized_warnings = self._sized_quantity_with_trace(
            risk=risk_plan_version,
            price=current_price,
            initial_cash=account_state.account_cash if account_state.account_cash > 0 else account_state.account_equity,
            stop_candidate=stop_candidate,
            side=signal_plan.side,
            steps=steps,
        )
        warnings.extend(sized_warnings)

        rounded_quantity = self._round_quantity(raw_quantity, fractional_allowed=fractional_quantity_allowed)
        if rounded_quantity != raw_quantity:
            steps.append(
                RiskCalculationStep(
                    name="rounding",
                    formula=f"{whole_share_rounding}(raw_quantity)" if not fractional_quantity_allowed else "fractional_exact",
                    inputs={
                        "raw_quantity": raw_quantity,
                        "fractional_allowed": fractional_quantity_allowed,
                        "policy": whole_share_rounding,
                    },
                    output=rounded_quantity,
                )
            )
            if not fractional_quantity_allowed:
                constraints.append("whole_share_rounding")

        capped_quantity: float | None = None
        rejected_quantity: float | None = None
        decision_status: RiskDecisionStatus
        reason_codes: list[str] = []
        violations: list[str] = []

        if rounded_quantity <= 0:
            decision_status = RiskDecisionStatus.REJECTED
            violations.append("zero_quantity_after_rounding")
            reason_codes.append("zero_quantity_after_rounding")
            final_quantity = 0.0
        else:
            final_quantity = rounded_quantity

            if risk_plan_version.max_symbol_exposure_pct is not None:
                cap_notional = account_state.account_equity * (risk_plan_version.max_symbol_exposure_pct / 100)
                projected_notional = final_quantity * current_price + account_state.existing_position_notional
                if projected_notional > cap_notional and current_price > 0:
                    pre_cap = final_quantity
                    capped_quantity = max(
                        (cap_notional - account_state.existing_position_notional) / current_price, 0
                    )
                    capped_quantity = self._round_quantity(capped_quantity, fractional_allowed=fractional_quantity_allowed)
                    steps.append(
                        RiskCalculationStep(
                            name="cap_by_max_symbol_exposure",
                            formula="min(quantity, (equity * max_symbol_exposure_pct / 100 - existing_notional) / price)",
                            inputs={
                                "quantity": pre_cap,
                                "equity": account_state.account_equity,
                                "max_symbol_exposure_pct": risk_plan_version.max_symbol_exposure_pct,
                                "existing_notional": account_state.existing_position_notional,
                                "price": current_price,
                            },
                            output=capped_quantity,
                        )
                    )
                    constraints.append("max_symbol_exposure_pct")
                    if capped_quantity <= 0:
                        decision_status = RiskDecisionStatus.REJECTED
                        violations.append("symbol_exposure_cap_blocks_entry")
                        reason_codes.append("symbol_exposure_cap_blocks_entry")
                        final_quantity = 0.0
                    else:
                        decision_status = RiskDecisionStatus.CAPPED
                        reason_codes.append("capped_by_max_symbol_exposure_pct")
                        final_quantity = capped_quantity
                else:
                    decision_status = RiskDecisionStatus.APPROVED
            else:
                decision_status = RiskDecisionStatus.APPROVED

            if final_quantity > 0 and rounded_quantity != raw_quantity and not fractional_quantity_allowed:
                rejected_quantity = max(raw_quantity - final_quantity, 0)
                if rejected_quantity > 0 and decision_status == RiskDecisionStatus.APPROVED:
                    decision_status = RiskDecisionStatus.REDUCED
                    reason_codes.append("rounded_down_to_whole_share")

            if decision_status == RiskDecisionStatus.APPROVED:
                reason_codes.append("approved")

        final_notional = final_quantity * current_price
        # SHORT stops sit ABOVE entry; LONG stops sit BELOW entry. Distance
        # is reported as a non-negative magnitude so downstream max-loss math
        # works for both sides.
        stop_distance = (
            self._signed_stop_distance(price=current_price, stop=stop_candidate, side=signal_plan.side)
            if stop_candidate is not None
            else None
        )
        stop_distance_pct = (stop_distance / current_price * 100) if stop_distance is not None and current_price > 0 else None
        max_loss_estimate = (final_quantity * stop_distance) if stop_distance is not None else None

        human_summary = self._build_human_summary(
            decision_status=decision_status,
            final_quantity=final_quantity,
            symbol=signal_plan.symbol,
            risk_plan=risk_plan_version,
            stop_distance=stop_distance,
            equity=account_state.account_equity,
            raw_quantity=raw_quantity,
            constraints=constraints,
        )

        card = RiskDecisionCard(
            mode=normalized_mode,
            run_id=run_id,
            session_id=session_id,
            account_id=account_state.account_id,
            simulated_account_id=account_state.simulated_account_id or (uuid4() if account_state.account_id is None else None),
            strategy_id=signal_plan.strategy_id,
            strategy_version_id=signal_plan.strategy_version_id,
            deployment_id=deployment_id or signal_plan.deployment_id,
            signal_plan_id=signal_plan.signal_plan_id,
            candidate_trade_intent_id=candidate_trade_intent_id,
            feature_snapshot_id=feature_snapshot_id,
            symbol=signal_plan.symbol,
            side=signal_plan.side.value,
            lifecycle_intent=signal_plan.intent.value,
            timestamp=signal_plan.created_at or utc_now(),
            risk_plan_id=risk_plan_version.risk_profile_id,
            risk_plan_version_id=risk_plan_version.id,
            risk_score=None,
            risk_tier=None,
            config_fingerprint=f"{risk_plan_version.sizing_method.value}:v{risk_plan_version.version}",
            account_equity=account_state.account_equity,
            account_cash=account_state.account_cash,
            buying_power=account_state.buying_power,
            current_price=current_price,
            entry_price=current_price,
            stop_price=stop_candidate,
            stop_distance=stop_distance,
            stop_distance_pct=stop_distance_pct,
            sizing_method=sizing_method.value,
            formula_used=formula_used,
            raw_quantity=raw_quantity,
            rounded_quantity=rounded_quantity,
            final_quantity=final_quantity,
            final_notional=final_notional,
            rejected_quantity=rejected_quantity,
            capped_quantity=capped_quantity,
            max_loss_estimate=max_loss_estimate,
            risk_amount_requested=self._risk_amount(risk_plan_version, account_state.account_equity),
            risk_amount_allowed=max_loss_estimate,
            buying_power_required=final_notional,
            projected_gross_exposure=final_notional + account_state.existing_position_notional,
            projected_symbol_exposure=final_notional + account_state.existing_position_notional,
            projected_open_risk=max_loss_estimate,
            existing_position_quantity=account_state.existing_position_quantity,
            existing_position_notional=account_state.existing_position_notional,
            existing_open_orders_count=account_state.existing_open_orders_count,
            existing_open_order_notional=account_state.existing_open_order_notional,
            fractional_quantity_allowed=fractional_quantity_allowed,
            whole_share_rounding=whole_share_rounding,
            constraints_applied=tuple(constraints),
            violations=tuple(violations),
            warnings=tuple(warnings),
            decision=decision_status,
            reason_codes=tuple(reason_codes),
            human_summary=human_summary,
            calculation_steps=tuple(steps),
            risk_resolver_version=RISK_RESOLVER_VERSION,
        )
        if sink is not None:
            sink.save_risk_decision_card(card)
        return card

    def _decide_exit(
        self,
        *,
        signal_plan: SignalPlan,
        risk_plan_version: RiskProfileVersion,
        account_state: AccountStateSnapshot,
        current_price: float,
        stop_candidate: float | None,
        candidate_trade_intent_id: UUID | None,
        feature_snapshot_id: UUID | None,
        session_id: UUID | None,
        deployment_id: UUID | None,
        fractional_quantity_allowed: bool,
        whole_share_rounding: str,
        sink: RiskDecisionCardSink | None,
        normalized_mode: RiskDecisionMode,
        run_id: UUID,
        exit_quantity_pct: float | None,
    ) -> RiskDecisionCard:
        existing_qty = max(account_state.existing_position_quantity, 0.0)
        steps: list[RiskCalculationStep] = []
        warnings: list[str] = []
        violations: list[str] = []
        constraints: list[str] = []
        reason_codes: list[str] = []

        steps.append(
            RiskCalculationStep(
                name="existing_position_quantity",
                formula="account_state.existing_position_quantity",
                inputs={"existing_position_quantity": existing_qty},
                output=existing_qty,
            )
        )

        # Reduce paths (intent=REDUCE, or LOGICAL_EXIT with action=reduce + quantity_pct)
        # honor exit_quantity_pct supplied by caller. Otherwise full close.
        target_pct = float(exit_quantity_pct) if exit_quantity_pct is not None else 100.0
        if target_pct <= 0 or target_pct > 100:
            target_pct = 100.0
            warnings.append("exit_quantity_pct_clamped_to_full_close")

        raw_quantity = existing_qty * (target_pct / 100.0)
        if target_pct < 100.0:
            constraints.append(f"reduce_quantity_pct={target_pct}")
        steps.append(
            RiskCalculationStep(
                name="exit_quantity_from_position",
                formula="existing_position_quantity * exit_quantity_pct / 100",
                inputs={"existing_position_quantity": existing_qty, "exit_quantity_pct": target_pct},
                output=raw_quantity,
            )
        )

        rounded_quantity = self._round_quantity(raw_quantity, fractional_allowed=fractional_quantity_allowed)
        if rounded_quantity != raw_quantity:
            steps.append(
                RiskCalculationStep(
                    name="rounding",
                    formula=(
                        f"{whole_share_rounding}(quantity)"
                        if not fractional_quantity_allowed
                        else "fractional_exact"
                    ),
                    inputs={
                        "raw_quantity": raw_quantity,
                        "fractional_allowed": fractional_quantity_allowed,
                        "policy": whole_share_rounding,
                    },
                    output=rounded_quantity,
                )
            )
            if not fractional_quantity_allowed:
                constraints.append("whole_share_rounding")

        if existing_qty <= 0 or rounded_quantity <= 0:
            decision = RiskDecisionStatus.SKIPPED
            violations.append("no_open_position_to_exit")
            reason_codes.append("no_open_position_to_exit")
            final_quantity = 0.0
        else:
            final_quantity = rounded_quantity
            decision = RiskDecisionStatus.APPROVED
            reason_codes.append("approved_exit")

        final_notional = final_quantity * current_price

        verb = {
            SignalPlanIntent.LOGICAL_EXIT: "logical exit",
            SignalPlanIntent.CLOSE: "close",
            SignalPlanIntent.REDUCE: "reduce",
            SignalPlanIntent.TARGET: "target take",
            SignalPlanIntent.STOP: "stop",
            SignalPlanIntent.TRAIL: "trailing exit",
            SignalPlanIntent.BREAKEVEN: "breakeven move",
            SignalPlanIntent.RUNNER: "runner action",
        }.get(signal_plan.intent, signal_plan.intent.value)
        action_phrase = (
            f"{final_quantity:.4f} shares of {signal_plan.symbol}"
            if final_quantity > 0
            else f"position in {signal_plan.symbol}"
        )
        if decision == RiskDecisionStatus.SKIPPED:
            human_summary = (
                f"Skipped {verb} on {signal_plan.symbol}: no open position to exit; "
                f"existing qty {existing_qty}."
            )
        else:
            human_summary = (
                f"Approved {verb} of {action_phrase}. RiskPlan {risk_plan_version.name}; "
                f"target {target_pct:.1f}% of {existing_qty:.4f} existing shares; price ${current_price:.4f}."
            )

        return self._persist_card(
            sink=sink,
            card=RiskDecisionCard(
                mode=normalized_mode,
                run_id=run_id,
                session_id=session_id,
                account_id=account_state.account_id,
                simulated_account_id=account_state.simulated_account_id
                or (uuid4() if account_state.account_id is None else None),
                strategy_id=signal_plan.strategy_id,
                strategy_version_id=signal_plan.strategy_version_id,
                deployment_id=deployment_id or signal_plan.deployment_id,
                signal_plan_id=signal_plan.signal_plan_id,
                candidate_trade_intent_id=candidate_trade_intent_id,
                feature_snapshot_id=feature_snapshot_id,
                symbol=signal_plan.symbol,
                side=signal_plan.side.value,
                lifecycle_intent=signal_plan.intent.value,
                timestamp=signal_plan.created_at or utc_now(),
                risk_plan_id=risk_plan_version.risk_profile_id,
                risk_plan_version_id=risk_plan_version.id,
                risk_score=None,
                risk_tier=None,
                config_fingerprint=f"exit:{signal_plan.intent.value}:v{risk_plan_version.version}",
                account_equity=account_state.account_equity,
                account_cash=account_state.account_cash,
                buying_power=account_state.buying_power,
                current_price=current_price,
                entry_price=current_price,
                stop_price=stop_candidate,
                stop_distance=None,
                stop_distance_pct=None,
                sizing_method=f"exit_from_position:{target_pct:.1f}%",
                formula_used="existing_position_quantity * exit_quantity_pct / 100",
                raw_quantity=raw_quantity,
                rounded_quantity=rounded_quantity,
                final_quantity=final_quantity,
                final_notional=final_notional,
                rejected_quantity=None,
                capped_quantity=None,
                max_loss_estimate=None,
                risk_amount_requested=None,
                risk_amount_allowed=None,
                buying_power_required=0.0,
                projected_gross_exposure=max(
                    account_state.existing_position_notional - final_notional, 0.0
                ),
                projected_symbol_exposure=max(
                    account_state.existing_position_notional - final_notional, 0.0
                ),
                projected_open_risk=None,
                existing_position_quantity=existing_qty,
                existing_position_notional=account_state.existing_position_notional,
                existing_open_orders_count=account_state.existing_open_orders_count,
                existing_open_order_notional=account_state.existing_open_order_notional,
                fractional_quantity_allowed=fractional_quantity_allowed,
                whole_share_rounding=whole_share_rounding,
                constraints_applied=tuple(constraints),
                violations=tuple(violations),
                warnings=tuple(warnings),
                decision=decision,
                reason_codes=tuple(reason_codes),
                human_summary=human_summary,
                calculation_steps=tuple(steps),
                risk_resolver_version=RISK_RESOLVER_VERSION,
            ),
        )

    @staticmethod
    def _persist_card(
        *,
        sink: RiskDecisionCardSink | None,
        card: RiskDecisionCard,
    ) -> RiskDecisionCard:
        if sink is not None:
            sink.save_risk_decision_card(card)
        return card

    @staticmethod
    def _signed_stop_distance(*, price: float, stop: float, side: SignalPlanSide) -> float:
        if side == SignalPlanSide.SHORT:
            return max(stop - price, 0.0)
        return max(price - stop, 0.0)

    def _sized_quantity_with_trace(
        self,
        *,
        risk: RiskProfileVersion,
        price: float,
        initial_cash: float,
        stop_candidate: float | None,
        steps: list[RiskCalculationStep],
        side: SignalPlanSide = SignalPlanSide.LONG,
    ) -> tuple[str, float, list[str]]:
        warnings: list[str] = []
        if risk.sizing_method == PositionSizingMethod.FIXED_SHARES:
            if risk.fixed_shares is None:
                raise RiskResolverError("fixed_shares sizing requires fixed_shares")
            quantity = float(risk.fixed_shares)
            steps.append(
                RiskCalculationStep(
                    name="fixed_shares",
                    formula="risk.fixed_shares",
                    inputs={"fixed_shares": risk.fixed_shares},
                    output=quantity,
                )
            )
            return "risk.fixed_shares", quantity, warnings
        if risk.sizing_method == PositionSizingMethod.FIXED_DOLLAR:
            if risk.fixed_notional is None:
                raise RiskResolverError("fixed_dollar sizing requires fixed_notional")
            quantity = max(risk.fixed_notional / price, 0.000001)
            steps.append(
                RiskCalculationStep(
                    name="fixed_notional",
                    formula="risk.fixed_notional / price",
                    inputs={"fixed_notional": risk.fixed_notional, "price": price},
                    output=quantity,
                )
            )
            return "risk.fixed_notional / price", quantity, warnings
        if risk.sizing_method == PositionSizingMethod.RISK_PERCENT_EQUITY:
            if risk.risk_per_trade_pct is None:
                raise RiskResolverError("risk_percent_equity sizing requires risk_per_trade_pct")
            risk_budget = initial_cash * (risk.risk_per_trade_pct / 100)
            steps.append(
                RiskCalculationStep(
                    name="risk_budget",
                    formula="equity * risk_per_trade_pct / 100",
                    inputs={"equity": initial_cash, "risk_per_trade_pct": risk.risk_per_trade_pct},
                    output=risk_budget,
                )
            )
            if stop_candidate is not None:
                stop_distance = self._signed_stop_distance(
                    price=price, stop=stop_candidate, side=side
                )
                steps.append(
                    RiskCalculationStep(
                        name="stop_distance",
                        formula=(
                            "stop_candidate - price"
                            if side == SignalPlanSide.SHORT
                            else "price - stop_candidate"
                        ),
                        inputs={"price": price, "stop_candidate": stop_candidate, "side": side.value},
                        output=stop_distance,
                    )
                )
                if stop_distance > 0:
                    quantity = max(risk_budget / stop_distance, 0.000001)
                    steps.append(
                        RiskCalculationStep(
                            name="raw_quantity",
                            formula="risk_budget / stop_distance",
                            inputs={"risk_budget": risk_budget, "stop_distance": stop_distance},
                            output=quantity,
                        )
                    )
                    return "risk_budget / stop_distance", quantity, warnings
                warnings.append("stop_distance_zero_falling_back_to_notional_sizing")
            quantity = max(risk_budget / price, 0.000001)
            steps.append(
                RiskCalculationStep(
                    name="raw_quantity",
                    formula="risk_budget / price",
                    inputs={"risk_budget": risk_budget, "price": price},
                    output=quantity,
                )
            )
            return "risk_budget / price", quantity, warnings
        raise RiskResolverError(f"unsupported sizing method '{risk.sizing_method}'")

    def _risk_amount(self, risk: RiskProfileVersion, equity: float) -> float | None:
        if risk.sizing_method == PositionSizingMethod.RISK_PERCENT_EQUITY and risk.risk_per_trade_pct is not None:
            return equity * (risk.risk_per_trade_pct / 100)
        if risk.sizing_method == PositionSizingMethod.FIXED_DOLLAR and risk.fixed_notional is not None:
            return risk.fixed_notional
        return None

    @staticmethod
    def _build_human_summary(
        *,
        decision_status: RiskDecisionStatus,
        final_quantity: float,
        symbol: str,
        risk_plan: RiskProfileVersion,
        stop_distance: float | None,
        equity: float,
        raw_quantity: float,
        constraints: list[str],
    ) -> str:
        verb = {
            RiskDecisionStatus.APPROVED: "Approved",
            RiskDecisionStatus.REDUCED: "Approved (reduced)",
            RiskDecisionStatus.CAPPED: "Approved (capped)",
            RiskDecisionStatus.REJECTED: "Rejected",
            RiskDecisionStatus.SKIPPED: "Skipped",
            RiskDecisionStatus.REQUIRES_OPERATOR: "Requires operator",
        }.get(decision_status, decision_status.value.title())
        qty_phrase = (
            f"{final_quantity:.4f} shares of {symbol}" if final_quantity > 0 else f"a position in {symbol}"
        )
        if risk_plan.sizing_method == PositionSizingMethod.FIXED_SHARES:
            method_phrase = f"fixed {risk_plan.fixed_shares or 0} shares"
        elif risk_plan.sizing_method == PositionSizingMethod.FIXED_DOLLAR:
            method_phrase = f"fixed ${(risk_plan.fixed_notional or 0):.2f} notional"
        elif risk_plan.sizing_method == PositionSizingMethod.RISK_PERCENT_EQUITY:
            method_phrase = f"{risk_plan.risk_per_trade_pct or 0}% account risk per trade"
        else:
            method_phrase = risk_plan.sizing_method.value
        cap_phrase = ""
        if constraints:
            cap_phrase = f" Constraints applied: {', '.join(constraints)}."
        stop_phrase = ""
        if stop_distance is not None:
            stop_phrase = f" Stop distance ${stop_distance:.4f}."
        return (
            f"{verb} {qty_phrase}. RiskPlan {risk_plan.name} ({method_phrase}); equity ${equity:,.2f}; "
            f"raw quantity {raw_quantity:.4f}.{stop_phrase}{cap_phrase}"
        )

    def lifecycle_sizing_from_risk_profile(self, sizing: AccountRiskSizingInput) -> LifecycleSizingInput:
        risk = sizing.risk_profile
        quantity = self._quantity_from_risk_profile(
            risk=risk,
            price=sizing.price,
            initial_cash=sizing.initial_cash,
            stop_candidate=sizing.stop_candidate,
        )
        return LifecycleSizingInput(
            quantity=quantity,
            fractional_quantity_allowed=sizing.fractional_quantity_allowed,
            whole_share_rounding=sizing.whole_share_rounding,
        )

    def _quantity_from_risk_profile(
        self,
        *,
        risk: RiskProfileVersion,
        price: float,
        initial_cash: float,
        stop_candidate: float | None,
    ) -> float:
        if risk.sizing_method == PositionSizingMethod.FIXED_SHARES:
            if risk.fixed_shares is None:
                raise RiskResolverError("fixed_shares sizing requires fixed_shares")
            return float(risk.fixed_shares)
        if risk.sizing_method == PositionSizingMethod.FIXED_DOLLAR:
            if risk.fixed_notional is None:
                raise RiskResolverError("fixed_dollar sizing requires fixed_notional")
            return max(risk.fixed_notional / price, 0.000001)
        if risk.sizing_method == PositionSizingMethod.RISK_PERCENT_EQUITY:
            if risk.risk_per_trade_pct is None:
                raise RiskResolverError("risk_percent_equity sizing requires risk_per_trade_pct")
            risk_amount = initial_cash * (risk.risk_per_trade_pct / 100)
            if stop_candidate is not None:
                # Side-agnostic risk-per-share = abs distance from price to stop.
                per_share_risk = abs(price - stop_candidate)
                if per_share_risk > 0:
                    return max(risk_amount / per_share_risk, 0.000001)
            return max(risk_amount / price, 0.000001)
        raise RiskResolverError(f"unsupported sizing method '{risk.sizing_method}'")

    def _allocate_signal_plan_legs(
        self,
        *,
        signal_plan: SignalPlan,
        sizing: LifecycleSizingInput,
    ) -> tuple[RiskResolvedLegAllocation, ...]:
        quantity = sizing.quantity
        if quantity is None:
            return ()
        total = self._round_quantity(quantity, fractional_allowed=sizing.fractional_quantity_allowed)
        if total <= 0:
            return ()
        allocations: list[RiskResolvedLegAllocation] = []
        if signal_plan.intent == SignalPlanIntent.OPEN:
            allocations.append(
                RiskResolvedLegAllocation(
                    leg_label="entry",
                    lifecycle_intent=SignalPlanIntent.OPEN,
                    resolved_quantity=total,
                    quantity_pct=100,
                    source="total_account_quantity",
                )
            )
            if signal_plan.stop is not None and signal_plan.stop.required:
                allocations.append(
                    RiskResolvedLegAllocation(
                        leg_label="stop",
                        lifecycle_intent=SignalPlanIntent.STOP,
                        resolved_quantity=total,
                        quantity_pct=100,
                        source="protective_full_position",
                    )
                )
            allocations.extend(self._target_and_runner_allocations(signal_plan=signal_plan, total=total, sizing=sizing))
            return tuple(allocations)

        allocations.append(
            RiskResolvedLegAllocation(
                leg_label=signal_plan.intent.value,
                lifecycle_intent=signal_plan.intent,
                resolved_quantity=total,
                quantity_pct=100,
                source="position_management_quantity",
            )
        )
        return tuple(allocations)

    def _target_and_runner_allocations(
        self,
        *,
        signal_plan: SignalPlan,
        total: float,
        sizing: LifecycleSizingInput,
    ) -> tuple[RiskResolvedLegAllocation, ...]:
        target_allocations: list[RiskResolvedLegAllocation] = []
        target_quantity_total = 0.0
        targets = signal_plan.targets
        for index, target in enumerate(targets):
            quantity = self._quantity_from_pct(
                total,
                target.quantity_pct,
                fractional_allowed=sizing.fractional_quantity_allowed,
            )
            if (
                not sizing.fractional_quantity_allowed
                and signal_plan.runner is None
                and index == len(targets) - 1
                and abs(sum(item.quantity_pct for item in targets) - 100) < 0.000001
            ):
                quantity = max(total - target_quantity_total, 0)
            if quantity <= 0:
                continue
            target_quantity_total += quantity
            target_allocations.append(
                RiskResolvedLegAllocation(
                    leg_label=target.label,
                    lifecycle_intent=SignalPlanIntent.TARGET,
                    resolved_quantity=quantity,
                    quantity_pct=target.quantity_pct,
                    source="target_pct",
                )
            )

        runner_allocation: RiskResolvedLegAllocation | None = None
        if signal_plan.runner is not None and signal_plan.runner.quantity_pct > 0:
            if sizing.fractional_quantity_allowed:
                runner_quantity = self._quantity_from_pct(total, signal_plan.runner.quantity_pct, fractional_allowed=True)
            else:
                runner_quantity = max(total - target_quantity_total, 0)
            if runner_quantity > 0:
                runner_allocation = RiskResolvedLegAllocation(
                    leg_label="runner",
                    lifecycle_intent=SignalPlanIntent.RUNNER,
                    resolved_quantity=runner_quantity,
                    quantity_pct=signal_plan.runner.quantity_pct,
                    source="runner_pct_remainder" if not sizing.fractional_quantity_allowed else "runner_pct",
                )
        return tuple([*target_allocations, *(() if runner_allocation is None else (runner_allocation,))])

    @staticmethod
    def _allocation_warnings(
        *,
        signal_plan: SignalPlan,
        total: float,
        allocations: tuple[RiskResolvedLegAllocation, ...],
    ) -> tuple[str, ...]:
        if signal_plan.intent != SignalPlanIntent.OPEN:
            return ()
        management_total = sum(
            allocation.resolved_quantity
            for allocation in allocations
            if allocation.lifecycle_intent in {
                SignalPlanIntent.TARGET,
                SignalPlanIntent.RUNNER,
                SignalPlanIntent.CLOSE,
                SignalPlanIntent.REDUCE,
                SignalPlanIntent.LOGICAL_EXIT,
            }
        )
        if 0 < management_total < total:
            return ("unallocated_quantity_after_lifecycle_allocation",)
        return ()

    @staticmethod
    def _quantity_from_pct(total: float, pct: float, *, fractional_allowed: bool) -> float:
        raw = total * pct / 100
        return raw if fractional_allowed else float(floor(raw))

    @staticmethod
    def _round_quantity(quantity: float, *, fractional_allowed: bool) -> float:
        return quantity if fractional_allowed else float(floor(quantity))

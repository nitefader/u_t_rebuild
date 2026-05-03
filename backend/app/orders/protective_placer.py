"""ProtectiveOrderPlacer — post-fill bracket completion.

T-4 of the Strategy-to-Broker Bracket Execution Program.

Doctrine: this is NOT a runtime root. It is a subscriber wired into the
existing ``BrokerSync`` event flow at the orchestrator composition root.
Per ``TURTLE_SHELL_GUARDRAILS.md`` §47-69 there is one runtime composition
root that owns deployment startup, SignalPlan publication, account fan-out,
RiskResolver invocation, Governor invocation, and OrderManager handoff.
This component consumes BrokerSync's ``EntryFillEvent`` and produces
child protective orders via ``OrderManager`` — it does not call the broker
directly, and it does not write broker truth.

Flow (per MAP §3 T-4 Mode A — post_fill_bracket):

    BrokerSync ingests trade-update stream
      -> emits EntryFillEvent(order_id, account_id, signal_plan_id, fill_price, filled_qty)
      -> ProtectiveOrderPlacer.handle_entry_fill(...)
        -> reads SignalPlan.stop.rule + SignalPlan.targets[*].rule
        -> decodes post_fill_pct:<pct> via parse_post_fill_pct
        -> computes concrete stop_price + target_price (long flips for short)
        -> calls OrderManager.create_protective_orders_post_fill(...)
        -> returns the created child orders
      -> orchestrator submits the child orders via BrokerAdapter (not here)

Idempotency: each call is keyed on (signal_plan_id, parent_order_id,
covered_qty_breakpoint). A second emission of the same fill event is a
no-op; a *new* fill event with cumulative_filled_qty greater than the last
covered breakpoint creates incremental protective orders for the new
uncovered shares only.

Side semantics:

- LONG entry  -> stop SELL @ fill * (1 - stop_pct/100), target SELL @ fill * (1 + target_pct/100)
- SHORT entry -> stop BUY  @ fill * (1 + stop_pct/100), target BUY  @ fill * (1 - target_pct/100)

The ProtectiveOrderPlacer does not concern itself with OCO grouping; the
two child orders carry ``order_class="oco"`` so the BrokerAdapter knows to
submit them as a mutually-exclusive pair when supported.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from backend.app.decision.signal_plan_common import parse_post_fill_pct
from backend.app.domain.signal_plan import (
    SignalPlan,
    SignalPlanIntent,
    SignalPlanSide,
)


class ProtectiveOrderPlacerError(ValueError):
    """Operator-readable failure on post-fill protective placement."""


@dataclass(frozen=True)
class ProtectiveLeg:
    """One side of the post-fill protective pair.

    The ``stop_price`` field is set on the stop leg and the ``limit_price``
    field is set on the target leg; the OrderManager translates this into
    the appropriate ``InternalOrder`` shape (STOP order for the stop,
    LIMIT order for the target).
    """

    label: str
    side: str  # "buy" | "sell" — opposite of the entry side
    quantity: float  # share count (always > 0)
    stop_price: float | None  # set on the stop leg, None on the target leg
    limit_price: float | None  # set on the target leg, None on the stop leg
    rule: str  # the original post_fill_pct:<pct> rule from the SignalPlan


@dataclass(frozen=True)
class ProtectivePlacementPlan:
    """The computed child-order plan for one fill event.

    Empty ``legs`` tuple means "no protection needed" (e.g. SignalPlan has
    no stop/target rules, or the rules are unsupported). The orchestrator
    must surface this as ``protection_status=naked`` if non-empty stop/
    target intent existed on the SignalPlan but produced no legs.
    """

    parent_order_id: UUID
    signal_plan_id: UUID
    account_id: UUID
    covered_qty: float  # how many filled shares this plan covers
    legs: tuple[ProtectiveLeg, ...]


class ProtectiveOrderPlacer:
    """Decode SignalPlan bracket intent + a fill event into a ProtectivePlacementPlan.

    This class is deliberately stateless and pure: it returns a *plan*
    object the orchestrator passes to ``OrderManager``. Idempotency state
    (covered breakpoints) lives in the OrderManager / orders ledger so it
    persists across orchestrator restarts.
    """

    def compute_protective_plan(
        self,
        *,
        signal_plan: SignalPlan,
        parent_order_id: UUID,
        account_id: UUID,
        fill_price: float,
        cumulative_filled_qty: float,
        already_covered_qty: float = 0.0,
    ) -> ProtectivePlacementPlan:
        """Compute the protective leg orders for a post-fill bracket.

        Args:
            signal_plan: The neutral SignalPlan that produced the entry.
                Carries ``stop.rule="post_fill_pct:<pct>"`` and
                ``targets[*].rule="post_fill_pct:<pct>"`` per T-3.
            parent_order_id: The InternalOrder id of the entry that just
                filled. Child orders carry this as ``parent_order_id``.
            account_id: The Account that owns the entry order.
            fill_price: BrokerSync-reported average fill price for the
                slice we're covering (must be > 0).
            cumulative_filled_qty: Total shares filled on the parent so far.
            already_covered_qty: Total shares already covered by previous
                protective placements. The new placement covers
                ``cumulative_filled_qty - already_covered_qty`` shares.

        Returns:
            A ProtectivePlacementPlan. ``legs`` is empty when:
                - SignalPlan intent is not OPEN
                - cumulative_filled_qty <= already_covered_qty (idempotent no-op)
                - SignalPlan has no stop/target rules
                - rules are not post_fill_pct (concrete prices live elsewhere)
        """

        if fill_price <= 0:
            raise ProtectiveOrderPlacerError(
                f"fill_price must be > 0; got {fill_price}"
            )
        if cumulative_filled_qty < 0 or already_covered_qty < 0:
            raise ProtectiveOrderPlacerError(
                "cumulative_filled_qty and already_covered_qty must be >= 0"
            )
        if signal_plan.intent != SignalPlanIntent.OPEN:
            return self._empty_plan(parent_order_id, signal_plan, account_id)

        new_qty = cumulative_filled_qty - already_covered_qty
        if new_qty <= 0:
            # Idempotent: same or stale fill event -> no new protection.
            return self._empty_plan(parent_order_id, signal_plan, account_id)

        legs: list[ProtectiveLeg] = []
        exit_side = self._exit_side(signal_plan.side)

        atr_value = self._atr_value(signal_plan)
        stop_rule = signal_plan.stop.rule if signal_plan.stop is not None else None
        stop_pct = self._read_post_fill_pct(stop_rule)
        if stop_pct is not None:
            stop_price = self._stop_price(
                fill_price=fill_price,
                stop_pct=stop_pct,
                side=signal_plan.side,
            )
            legs.append(
                ProtectiveLeg(
                    label="stop",
                    side=exit_side,
                    quantity=new_qty,
                    stop_price=stop_price,
                    limit_price=None,
                    rule=signal_plan.stop.rule or "",
                )
            )
        else:
            stop_atr_multiple = self._read_atr_multiple(stop_rule)
            if stop_atr_multiple is not None and atr_value is not None:
                stop_price = self._atr_stop_price(
                    fill_price=fill_price,
                    atr_value=atr_value,
                    multiple=stop_atr_multiple,
                    side=signal_plan.side,
                )
                legs.append(
                    ProtectiveLeg(
                        label="stop",
                        side=exit_side,
                        quantity=new_qty,
                        stop_price=stop_price,
                        limit_price=None,
                        rule=stop_rule or "",
                    )
                )

        for target in signal_plan.targets:
            target_pct = self._read_post_fill_pct(target.rule)
            if target_pct is not None:
                target_price = self._target_price(
                    fill_price=fill_price,
                    target_pct=target_pct,
                    side=signal_plan.side,
                )
            else:
                target_atr_multiple = self._read_atr_multiple(target.rule)
                if target_atr_multiple is None or atr_value is None:
                    continue
                target_price = self._atr_target_price(
                    fill_price=fill_price,
                    atr_value=atr_value,
                    multiple=target_atr_multiple,
                    side=signal_plan.side,
                )
            target_qty = new_qty * (target.quantity_pct / 100.0)
            if target_qty <= 0:
                continue
            legs.append(
                ProtectiveLeg(
                    label=target.label,
                    side=exit_side,
                    quantity=target_qty,
                    stop_price=None,
                    limit_price=target_price,
                    rule=target.rule or "",
                )
            )

        return ProtectivePlacementPlan(
            parent_order_id=parent_order_id,
            signal_plan_id=signal_plan.signal_plan_id,
            account_id=account_id,
            covered_qty=new_qty,
            legs=tuple(legs),
        )

    @staticmethod
    def _empty_plan(
        parent_order_id: UUID,
        signal_plan: SignalPlan,
        account_id: UUID,
    ) -> ProtectivePlacementPlan:
        return ProtectivePlacementPlan(
            parent_order_id=parent_order_id,
            signal_plan_id=signal_plan.signal_plan_id,
            account_id=account_id,
            covered_qty=0.0,
            legs=(),
        )

    @staticmethod
    def _read_post_fill_pct(rule: str | None) -> float | None:
        return parse_post_fill_pct(rule)

    @staticmethod
    def _read_atr_multiple(rule: str | None) -> float | None:
        if not rule:
            return None
        prefix, sep, raw = rule.strip().partition(":")
        if sep != ":" or prefix.lower() != "atr":
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        return value if value > 0 else None

    @staticmethod
    def _atr_value(signal_plan: SignalPlan) -> float | None:
        for key, raw in signal_plan.feature_snapshot.items():
            key_l = key.lower()
            if not (
                key_l.startswith("atr")
                or ".atr" in key_l
                or "technical.atr" in key_l
            ):
                continue
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                continue
            value = float(raw)
            if value > 0:
                return value
        return None

    @staticmethod
    def _exit_side(entry_side: SignalPlanSide) -> str:
        if entry_side == SignalPlanSide.LONG:
            return "sell"
        if entry_side == SignalPlanSide.SHORT:
            return "buy"
        raise ProtectiveOrderPlacerError(
            f"unsupported SignalPlan side for post-fill bracket: {entry_side}"
        )

    @staticmethod
    def _stop_price(*, fill_price: float, stop_pct: float, side: SignalPlanSide) -> float:
        # LONG: stop is BELOW fill price (loss exit on the way down)
        # SHORT: stop is ABOVE fill price (loss exit on the way up)
        delta = fill_price * (stop_pct / 100.0)
        if side == SignalPlanSide.LONG:
            return fill_price - delta
        if side == SignalPlanSide.SHORT:
            return fill_price + delta
        raise ProtectiveOrderPlacerError(
            f"unsupported side for stop computation: {side}"
        )

    @staticmethod
    def _target_price(*, fill_price: float, target_pct: float, side: SignalPlanSide) -> float:
        # LONG: target is ABOVE fill price (profit exit)
        # SHORT: target is BELOW fill price (profit exit)
        delta = fill_price * (target_pct / 100.0)
        if side == SignalPlanSide.LONG:
            return fill_price + delta
        if side == SignalPlanSide.SHORT:
            return fill_price - delta
        raise ProtectiveOrderPlacerError(
            f"unsupported side for target computation: {side}"
        )

    @staticmethod
    def _atr_stop_price(*, fill_price: float, atr_value: float, multiple: float, side: SignalPlanSide) -> float:
        delta = atr_value * multiple
        if side == SignalPlanSide.LONG:
            return fill_price - delta
        if side == SignalPlanSide.SHORT:
            return fill_price + delta
        raise ProtectiveOrderPlacerError(
            f"unsupported side for ATR stop computation: {side}"
        )

    @staticmethod
    def _atr_target_price(*, fill_price: float, atr_value: float, multiple: float, side: SignalPlanSide) -> float:
        delta = atr_value * multiple
        if side == SignalPlanSide.LONG:
            return fill_price + delta
        if side == SignalPlanSide.SHORT:
            return fill_price - delta
        raise ProtectiveOrderPlacerError(
            f"unsupported side for ATR target computation: {side}"
        )

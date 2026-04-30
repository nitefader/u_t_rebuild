from __future__ import annotations

from uuid import UUID, uuid4

from backend.app.domain import (
    CandidateTradeIntent,
    IntentType,
    LogicalExitRule,
    SignalPlan,
    SignalPlanEntry,
    SignalPlanIntent,
    SignalPlanLogicalExit,
    SignalPlanLogicalExitScope,
    SignalPlanSide,
    SignalPlanStop,
    SignalPlanTarget,
    SignalPlanTargetAction,
)
from backend.app.domain.execution_style import (
    BracketRunnerPreset,
    BracketStopTargetPreset,
    ExecutionStyleVersion,
    ExecutionStylePresetKind,
    MultiTargetScaleOutPreset,
)


class SignalPlanBuilderError(ValueError):
    """Raised when a candidate cannot become a neutral SignalPlan."""


# T-3 (Bracket Program): rule prefix used when stop/target prices are computed
# *post-fill* by the OrderManager rather than pre-baked in the SignalPlan.
# Format is ``post_fill_pct:<pct>``. The ProtectiveOrderPlacer parses this back.
POST_FILL_PCT_RULE_PREFIX = "post_fill_pct"


def post_fill_pct_rule(pct: float) -> str:
    """Encode a post-fill percent for SignalPlanStop.rule / SignalPlanTarget.rule.

    Doctrine: SignalPlan stays neutral and quantity-free. When the operator
    declared "5% stop / 10% target" on a market entry, the *concrete* prices
    can only be known after the fill price is known. The builder encodes the
    operator's intent here; the runtime decodes it after BrokerSync confirms
    the entry fill.
    """

    if pct <= 0:
        raise SignalPlanBuilderError(f"post_fill_pct must be > 0; got {pct}")
    return f"{POST_FILL_PCT_RULE_PREFIX}:{pct}"


def parse_post_fill_pct(rule: str | None) -> float | None:
    """Parse ``post_fill_pct:<pct>`` back to a float. Returns None on miss."""

    if not rule or ":" not in rule:
        return None
    prefix, _, value = rule.partition(":")
    if prefix != POST_FILL_PCT_RULE_PREFIX:
        return None
    try:
        pct = float(value)
    except ValueError:
        return None
    if pct <= 0:
        return None
    return pct


class SignalPlanBuilder:
    """Build neutral SignalPlans from signal candidates.

    Doctrine: ``logical_exit`` is the only exit intent. Exit candidates always
    produce ``intent = SignalPlanIntent.LOGICAL_EXIT`` carrying a typed
    ``SignalPlanLogicalExit`` payload — never a sibling top-level intent.

    This builder does not know Account id, final quantity, buying power,
    broker credentials, or Governor approval.

    T-3 (Bracket Program): when ``execution_plan`` is provided the builder
    enriches the SignalPlan's stop/target with the operator-declared bracket
    intent — *symmetrically for long and short*. The encoded rule is
    ``post_fill_pct:<pct>``; concrete prices are resolved by the
    ProtectiveOrderPlacer once BrokerSync confirms the entry fill. SignalPlan
    remains quantity-free per the Account Evaluation Rule.
    """

    def build_from_candidate(
        self,
        *,
        candidate: CandidateTradeIntent,
        deployment_id: UUID,
        strategy_id: UUID,
        strategy_version_id: UUID,
        watchlist_snapshot_id: UUID | None = None,
        opening_signal_plan_id: UUID | None = None,
        related_position_lineage_id: UUID | None = None,
        logical_exit_rule: LogicalExitRule | None = None,
        logical_exit_action: SignalPlanTargetAction = SignalPlanTargetAction.CLOSE,
        logical_exit_quantity_pct: float | None = None,
        logical_exit_scope: SignalPlanLogicalExitScope = SignalPlanLogicalExitScope.REMAINING_QUANTITY,
        execution_plan: ExecutionStyleVersion | None = None,
    ) -> SignalPlan:
        intent = self._intent_for_candidate(candidate.intent_type)
        logical_exit_payload: SignalPlanLogicalExit | None = None
        if intent == SignalPlanIntent.LOGICAL_EXIT and logical_exit_rule is not None:
            logical_exit_payload = SignalPlanLogicalExit(
                rule=logical_exit_rule,
                action=logical_exit_action,
                quantity_pct=logical_exit_quantity_pct,
                applies_to=logical_exit_scope,
            )
        if intent == SignalPlanIntent.OPEN:
            stop, targets = self._open_legs_from_inputs(candidate, execution_plan)
        else:
            stop, targets = None, ()
        return SignalPlan(
            signal_plan_id=uuid4(),
            deployment_id=deployment_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            watchlist_snapshot_id=watchlist_snapshot_id,
            symbol=candidate.symbol.upper(),
            side=SignalPlanSide(candidate.side.value),
            intent=intent,
            entry=SignalPlanEntry() if intent == SignalPlanIntent.OPEN else None,
            stop=stop,
            targets=targets,
            logical_exit=logical_exit_payload,
            opening_signal_plan_id=opening_signal_plan_id,
            related_position_lineage_id=related_position_lineage_id,
            created_at=candidate.timestamp,
            reason=candidate.reason,
            feature_snapshot=candidate.feature_values_used,
        )

    def _intent_for_candidate(self, intent_type: IntentType) -> SignalPlanIntent:
        if intent_type == IntentType.ENTRY:
            return SignalPlanIntent.OPEN
        if intent_type == IntentType.EXIT:
            return SignalPlanIntent.LOGICAL_EXIT
        raise SignalPlanBuilderError(f"unsupported candidate intent type: {intent_type}")

    def _open_legs_from_inputs(
        self,
        candidate: CandidateTradeIntent,
        execution_plan: ExecutionStyleVersion | None,
    ) -> tuple[SignalPlanStop | None, tuple[SignalPlanTarget, ...]]:
        """Resolve OPEN-side stop + targets.

        Priority:
        1. ``execution_plan.preset`` (T-3): symmetric long/short bracket per
           operator-declared preset. Encoded as ``post_fill_pct:<pct>``.
        2. ``candidate.stop_candidate`` / ``candidate.target_candidate``:
           legacy concrete prices computed by the SignalEngine. Used when the
           ExecutionPlan does not declare a bracket preset.
        """

        stop_from_plan, targets_from_plan = self._legs_from_execution_plan(execution_plan)
        if stop_from_plan is not None or targets_from_plan:
            return stop_from_plan, targets_from_plan
        return self._stop_from_candidate(candidate), self._targets_from_candidate(candidate)

    def _legs_from_execution_plan(
        self, execution_plan: ExecutionStyleVersion | None
    ) -> tuple[SignalPlanStop | None, tuple[SignalPlanTarget, ...]]:
        if execution_plan is None or execution_plan.preset is None:
            return None, ()
        preset = execution_plan.preset
        if isinstance(preset, BracketStopTargetPreset):
            stop = SignalPlanStop(
                type="percent",
                rule=post_fill_pct_rule(preset.stop_pct),
                required=True,
            )
            target = SignalPlanTarget(
                label="t1",
                action=SignalPlanTargetAction.CLOSE,
                quantity_pct=100,
                rule=post_fill_pct_rule(preset.target_pct),
            )
            return stop, (target,)
        if isinstance(preset, BracketRunnerPreset):
            # First slice is the locked target; the remaining quantity is the
            # runner managed by the trail rule. Operator's first_target_pct is
            # post-fill percent; first_slice_pct is fraction of position.
            stop = SignalPlanStop(
                type="trail",
                rule=post_fill_pct_rule(preset.trail_pct),
                required=True,
            )
            slice_pct = max(min(preset.first_slice_pct * 100.0, 100.0), 0.000001)
            target = SignalPlanTarget(
                label="t1",
                action=SignalPlanTargetAction.REDUCE,
                quantity_pct=slice_pct,
                rule=post_fill_pct_rule(preset.first_target_pct),
            )
            return stop, (target,)
        if isinstance(preset, MultiTargetScaleOutPreset):
            stop: SignalPlanStop | None = None
            if preset.stop_pct is not None:
                stop = SignalPlanStop(
                    type="percent",
                    rule=post_fill_pct_rule(preset.stop_pct),
                    required=True,
                )
            targets = tuple(
                SignalPlanTarget(
                    label=f"t{i + 1}",
                    action=SignalPlanTargetAction.REDUCE,
                    quantity_pct=max(min(tier.slice_pct * 100.0, 100.0), 0.000001),
                    rule=post_fill_pct_rule(tier.target_pct),
                )
                for i, tier in enumerate(preset.targets)
            )
            return stop, targets
        # MarketEntryMarketExit / StopEntryMarketExit have no bracket legs.
        return None, ()

    def _stop_from_candidate(self, candidate: CandidateTradeIntent) -> SignalPlanStop | None:
        if candidate.stop_candidate is None:
            return None
        return SignalPlanStop(type="fixed", stop_price=candidate.stop_candidate, required=True)

    def _targets_from_candidate(self, candidate: CandidateTradeIntent) -> tuple[SignalPlanTarget, ...]:
        if candidate.target_candidate is None:
            return ()
        return (SignalPlanTarget(label="T1", quantity_pct=100, price=candidate.target_candidate),)

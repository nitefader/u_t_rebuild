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


class SignalPlanBuilderError(ValueError):
    """Raised when a candidate cannot become a neutral SignalPlan."""


class SignalPlanBuilder:
    """Build neutral SignalPlans from signal candidates.

    Doctrine: ``logical_exit`` is the only exit intent. Exit candidates always
    produce ``intent = SignalPlanIntent.LOGICAL_EXIT`` carrying a typed
    ``SignalPlanLogicalExit`` payload — never a sibling top-level intent.

    This builder does not know Account id, final quantity, buying power,
    broker credentials, or Governor approval.
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
            stop=self._stop_from_candidate(candidate) if intent == SignalPlanIntent.OPEN else None,
            targets=self._targets_from_candidate(candidate) if intent == SignalPlanIntent.OPEN else (),
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

    def _stop_from_candidate(self, candidate: CandidateTradeIntent) -> SignalPlanStop | None:
        if candidate.stop_candidate is None:
            return None
        return SignalPlanStop(type="fixed", stop_price=candidate.stop_candidate, required=True)

    def _targets_from_candidate(self, candidate: CandidateTradeIntent) -> tuple[SignalPlanTarget, ...]:
        if candidate.target_candidate is None:
            return ()
        return (SignalPlanTarget(label="T1", quantity_pct=100, price=candidate.target_candidate),)

from __future__ import annotations

from uuid import UUID, uuid4

from backend.app.domain import (
    CandidateTradeIntent,
    IntentType,
    LogicalExitRule,
    SignalPlan,
    SignalPlanIntent,
    SignalPlanLogicalExit,
    SignalPlanLogicalExitScope,
    SignalPlanSide,
    SignalPlanTargetAction,
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
    """Build Deployment-owned logical-exit SignalPlans from exit candidates.

    V4 entries build SignalPlans directly through the v4 signal source. This
    builder is the remaining candidate-to-SignalPlan bridge for position
    management, and stays account-neutral.
    """

    def build_from_candidate(
        self,
        *,
        candidate: CandidateTradeIntent,
        deployment_id: UUID,
        strategy_id: UUID,
        strategy_version_id: UUID,
        opening_signal_plan_id: UUID | None = None,
        related_position_lineage_id: UUID | None = None,
        logical_exit_rule: LogicalExitRule | None = None,
        logical_exit_action: SignalPlanTargetAction = SignalPlanTargetAction.CLOSE,
        logical_exit_quantity_pct: float | None = None,
        logical_exit_scope: SignalPlanLogicalExitScope = SignalPlanLogicalExitScope.REMAINING_QUANTITY,
    ) -> SignalPlan:
        intent = self._intent_for_candidate(candidate.intent_type)
        logical_exit_payload = (
            SignalPlanLogicalExit(
                rule=logical_exit_rule,
                action=logical_exit_action,
                quantity_pct=logical_exit_quantity_pct,
                applies_to=logical_exit_scope,
            )
            if logical_exit_rule is not None
            else None
        )
        return SignalPlan(
            signal_plan_id=uuid4(),
            deployment_id=deployment_id,
            strategy_id=strategy_id,
            strategy_version_id=strategy_version_id,
            symbol=candidate.symbol.upper(),
            side=SignalPlanSide(candidate.side.value),
            intent=intent,
            logical_exit=logical_exit_payload,
            opening_signal_plan_id=opening_signal_plan_id,
            related_position_lineage_id=related_position_lineage_id,
            created_at=candidate.timestamp,
            reason=candidate.reason,
            feature_snapshot=candidate.feature_values_used,
        )

    def _intent_for_candidate(self, intent_type: IntentType) -> SignalPlanIntent:
        if intent_type == IntentType.EXIT:
            return SignalPlanIntent.LOGICAL_EXIT
        raise SignalPlanBuilderError(f"unsupported candidate intent type: {intent_type}")


__all__ = [
    "POST_FILL_PCT_RULE_PREFIX",
    "SignalPlanBuilder",
    "SignalPlanBuilderError",
    "parse_post_fill_pct",
    "post_fill_pct_rule",
]

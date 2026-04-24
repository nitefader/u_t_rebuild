from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import (
    CandidateTradeIntent,
    ConditionGroup,
    ConditionNode,
    ConditionOperator,
    SignalRule,
    StrategyVersion,
)
from backend.app.features import FeatureAvailability, FeatureSnapshot, make_feature_key, parse_feature_expression


class SignalEvaluationError(ValueError):
    """Raised when a signal cannot be evaluated from the supplied snapshot."""


class SignalEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intents: tuple[CandidateTradeIntent, ...] = ()
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class SignalEngine:
    """Evaluate strategy signal rules using FeatureSnapshot values only."""

    def evaluate(self, strategy: StrategyVersion, snapshot: FeatureSnapshot) -> SignalEvaluation:
        intents: list[CandidateTradeIntent] = []
        rule_diagnostics: list[dict[str, Any]] = []

        for rule in [*strategy.entry_rules, *strategy.exit_rules]:
            is_true, features_used, diagnostics = self._evaluate_rule(rule, snapshot)
            rule_diagnostics.append(diagnostics)
            if is_true:
                intents.append(
                    CandidateTradeIntent(
                        timestamp=snapshot.timestamp,
                        symbol=snapshot.symbol,
                        side=rule.side,
                        intent_type=rule.intent_type,
                        signal_name=rule.name,
                        reason="signal_condition_true",
                        feature_values_used=features_used,
                        stop_candidate=self._optional_feature_value(rule.stop_candidate_feature, snapshot, features_used),
                        target_candidate=self._optional_feature_value(rule.target_candidate_feature, snapshot, features_used),
                        diagnostics=diagnostics,
                    )
                )

        return SignalEvaluation(
            intents=tuple(intents),
            diagnostics={
                "rules": rule_diagnostics,
                "intent_count": len(intents),
            },
        )

    def _evaluate_rule(self, rule: SignalRule, snapshot: FeatureSnapshot) -> tuple[bool, dict[str, float], dict[str, Any]]:
        is_true, features_used, condition_diagnostics = self._evaluate_condition(rule.condition, snapshot)
        return (
            is_true,
            features_used,
            {
                "rule": rule.name,
                "result": is_true,
                "reason": "signal_condition_true" if is_true else "signal_condition_false",
                "condition": condition_diagnostics,
                "features_used": features_used,
            },
        )

    def _evaluate_condition(
        self,
        condition: ConditionNode | ConditionGroup,
        snapshot: FeatureSnapshot,
    ) -> tuple[bool, dict[str, float], dict[str, Any]]:
        if isinstance(condition, ConditionNode):
            return self._evaluate_node(condition, snapshot)
        return self._evaluate_group(condition, snapshot)

    def _evaluate_group(
        self,
        group: ConditionGroup,
        snapshot: FeatureSnapshot,
    ) -> tuple[bool, dict[str, float], dict[str, Any]]:
        child_results: list[bool] = []
        merged_features: dict[str, float] = {}
        child_diagnostics: list[dict[str, Any]] = []
        for child in group.children:
            result, features_used, diagnostics = self._evaluate_condition(child, snapshot)
            child_results.append(result)
            merged_features.update(features_used)
            child_diagnostics.append(diagnostics)

        if group.operator in {"all", "and"}:
            group_result = all(child_results)
        elif group.operator in {"any", "or"}:
            group_result = any(child_results)
        else:
            raise SignalEvaluationError(f"unsupported condition group operator '{group.operator}'")

        return (
            group_result,
            merged_features,
            {
                "kind": "group",
                "operator": group.operator,
                "result": group_result,
                "children": child_diagnostics,
            },
        )

    def _evaluate_node(
        self,
        node: ConditionNode,
        snapshot: FeatureSnapshot,
    ) -> tuple[bool, dict[str, float], dict[str, Any]]:
        left = self._required_feature_value(node.left_feature, snapshot)
        features_used = {node.left_feature: left}

        if node.right_feature is not None:
            right = self._required_feature_value(node.right_feature, snapshot)
            features_used[node.right_feature] = right
            right_repr: str | float | int | bool = node.right_feature
        else:
            right = node.right_value
            right_repr = node.right_value  # type: ignore[assignment]

        if right is None:
            raise SignalEvaluationError("condition right operand cannot be None")

        result = self._compare(node, left, right, snapshot, features_used)
        return (
            result,
            features_used,
            {
                "kind": "condition",
                "left_feature": node.left_feature,
                "operator": node.operator,
                "right": right_repr,
                "left_value": left,
                "right_value": right,
                "result": result,
            },
        )

    def _compare(
        self,
        node: ConditionNode,
        left: float,
        right: float | int | str | bool,
        snapshot: FeatureSnapshot,
        features_used: dict[str, float],
    ) -> bool:
        if not isinstance(right, int | float):
            raise SignalEvaluationError(f"numeric comparison requires numeric right operand for '{node.left_feature}'")

        if node.operator in {ConditionOperator.GT, ConditionOperator.GREATER_THAN}:
            return left > right
        if node.operator == ConditionOperator.GTE:
            return left >= right
        if node.operator in {ConditionOperator.LT, ConditionOperator.LESS_THAN}:
            return left < right
        if node.operator == ConditionOperator.LTE:
            return left <= right
        if node.operator == ConditionOperator.EQ:
            return left == right
        if node.operator == ConditionOperator.CROSS_ABOVE:
            previous_left = self._previous_feature_value(node.left_feature, snapshot)
            previous_right = self._previous_right_value(node, snapshot)
            features_used[f"{node.left_feature}#previous"] = previous_left
            if node.right_feature is not None:
                features_used[f"{node.right_feature}#previous"] = previous_right
            return previous_left <= previous_right and left > right
        if node.operator == ConditionOperator.CROSS_BELOW:
            previous_left = self._previous_feature_value(node.left_feature, snapshot)
            previous_right = self._previous_right_value(node, snapshot)
            features_used[f"{node.left_feature}#previous"] = previous_left
            if node.right_feature is not None:
                features_used[f"{node.right_feature}#previous"] = previous_right
            return previous_left >= previous_right and left < right
        raise SignalEvaluationError(f"unsupported condition operator '{node.operator}'")

    def _previous_right_value(self, node: ConditionNode, snapshot: FeatureSnapshot) -> float:
        if node.right_feature is not None:
            return self._previous_feature_value(node.right_feature, snapshot)
        if isinstance(node.right_value, int | float):
            return float(node.right_value)
        raise SignalEvaluationError("cross comparison requires numeric right operand")

    def _required_feature_value(self, feature_ref: str, snapshot: FeatureSnapshot) -> float:
        key = self._feature_key(feature_ref)
        try:
            feature_value = snapshot.values[key]
        except KeyError as exc:
            raise SignalEvaluationError(f"missing feature value for '{feature_ref}'") from exc
        if feature_value.availability != FeatureAvailability.AVAILABLE or feature_value.value is None:
            raise SignalEvaluationError(f"feature value unavailable for '{feature_ref}': {feature_value.availability}")
        return float(feature_value.value)

    def _optional_feature_value(
        self,
        feature_ref: str | None,
        snapshot: FeatureSnapshot,
        features_used: dict[str, float],
    ) -> float | None:
        if feature_ref is None:
            return None
        value = self._required_feature_value(feature_ref, snapshot)
        features_used[feature_ref] = value
        return value

    def _previous_feature_value(self, feature_ref: str, snapshot: FeatureSnapshot) -> float:
        spec = parse_feature_expression(feature_ref)
        previous_spec = spec.model_copy(update={"lookback": spec.lookback + 1})
        key = make_feature_key(previous_spec)
        try:
            feature_value = snapshot.values[key]
        except KeyError as exc:
            raise SignalEvaluationError(f"missing previous feature value for '{feature_ref}'") from exc
        if feature_value.availability != FeatureAvailability.AVAILABLE or feature_value.value is None:
            raise SignalEvaluationError(f"previous feature value unavailable for '{feature_ref}': {feature_value.availability}")
        return float(feature_value.value)

    def _feature_key(self, feature_ref: str) -> str:
        return make_feature_key(parse_feature_expression(feature_ref))

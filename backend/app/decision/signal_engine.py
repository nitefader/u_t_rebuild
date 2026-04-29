from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from backend.app.domain import (
    CandidateTradeIntent,
    ConditionGroup,
    ConditionNode,
    ConditionOperator,
    IntentType,
    LogicalExitRule,
    LogicalExitRuleKind,
    SignalRule,
    StrategyVersion,
)
from backend.app.features import FeatureAvailability, FeatureSnapshot, make_feature_key, parse_feature_expression


# Default US equity regular-session window in Eastern time. The SignalEngine
# evaluates ``time_of_day_et`` and ``minutes_before_session_close`` against this
# window unless a different one is supplied per-symbol via ``PositionContext``.
_DEFAULT_SESSION_OPEN_ET = time(9, 30)
_DEFAULT_SESSION_CLOSE_ET = time(16, 0)


class SignalEvaluationError(ValueError):
    """Raised when a signal cannot be evaluated from the supplied snapshot."""


@dataclass(frozen=True)
class PositionContext:
    """Per-symbol position + clock state supplied to exit-rule evaluation.

    Doctrine: ``logical_exit`` is the only exit intent. Time-based, bar-count,
    session, and hybrid exit rules read this context; pure feature-condition
    exits do not need it (they evaluate against ``FeatureSnapshot`` only).
    """

    has_position: bool = False
    entry_timestamp: datetime | None = None
    entry_bar_index: int | None = None
    current_bar_index: int | None = None
    bar_timestamp: datetime | None = None
    session_open_et: time = _DEFAULT_SESSION_OPEN_ET
    session_close_et: time = _DEFAULT_SESSION_CLOSE_ET

    @property
    def bars_since_entry(self) -> int:
        if self.current_bar_index is None or self.entry_bar_index is None:
            return 0
        return max(0, self.current_bar_index - self.entry_bar_index)

    @property
    def seconds_since_entry(self) -> int:
        if self.bar_timestamp is None or self.entry_timestamp is None:
            return 0
        delta = self.bar_timestamp - self.entry_timestamp
        return max(0, int(delta.total_seconds()))


class SignalEvaluation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    intents: tuple[CandidateTradeIntent, ...] = ()
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class SignalEngine:
    """Evaluate strategy signal rules using FeatureSnapshot + PositionContext.

    Doctrine: ``logical_exit`` is the only exit intent. Exit rules may declare:
    - a ``condition`` tree (feature-based exit), and/or
    - a ``logical_exit_rule`` typed payload (time / bar / session / hybrid).

    When both are present they AND together. Position context is required only
    as input for evaluating non-feature logical exits.
    """

    def evaluate(
        self,
        strategy: StrategyVersion,
        snapshot: FeatureSnapshot,
        *,
        position_contexts: dict[str, PositionContext] | None = None,
    ) -> SignalEvaluation:
        intents: list[CandidateTradeIntent] = []
        rule_diagnostics: list[dict[str, Any]] = []
        contexts = position_contexts or {}

        for rule in strategy.entry_rules:
            is_true, features_used, diagnostics = self._evaluate_entry_rule(rule, snapshot)
            rule_diagnostics.append(diagnostics)
            if is_true:
                intents.append(self._build_intent(rule, snapshot, features_used, diagnostics))

        for rule in strategy.exit_rules:
            position_context = contexts.get(snapshot.symbol)
            is_true, features_used, diagnostics = self._evaluate_exit_rule(
                rule=rule,
                snapshot=snapshot,
                position_context=position_context,
            )
            rule_diagnostics.append(diagnostics)
            if is_true:
                intents.append(self._build_intent(rule, snapshot, features_used, diagnostics))

        return SignalEvaluation(
            intents=tuple(intents),
            diagnostics={
                "rules": rule_diagnostics,
                "intent_count": len(intents),
            },
        )

    def _build_intent(
        self,
        rule: SignalRule,
        snapshot: FeatureSnapshot,
        features_used: dict[str, float],
        diagnostics: dict[str, Any],
    ) -> CandidateTradeIntent:
        return CandidateTradeIntent(
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

    def _evaluate_entry_rule(
        self, rule: SignalRule, snapshot: FeatureSnapshot
    ) -> tuple[bool, dict[str, float], dict[str, Any]]:
        if rule.condition is None:
            raise SignalEvaluationError(f"entry rule '{rule.name}' missing condition")
        is_true, features_used, condition_diagnostics = self._evaluate_condition(rule.condition, snapshot)
        return (
            is_true,
            features_used,
            {
                "rule": rule.name,
                "intent_type": rule.intent_type.value,
                "result": is_true,
                "reason": "signal_condition_true" if is_true else "signal_condition_false",
                "condition": condition_diagnostics,
                "features_used": features_used,
            },
        )

    def _evaluate_exit_rule(
        self,
        *,
        rule: SignalRule,
        snapshot: FeatureSnapshot,
        position_context: PositionContext | None,
    ) -> tuple[bool, dict[str, float], dict[str, Any]]:
        # Exit semantics: only fire when there is an open position to exit.
        if position_context is None or not position_context.has_position:
            return (
                False,
                {},
                {
                    "rule": rule.name,
                    "intent_type": rule.intent_type.value,
                    "result": False,
                    "reason": "no_open_position",
                },
            )

        diagnostics: dict[str, Any] = {
            "rule": rule.name,
            "intent_type": rule.intent_type.value,
            "result": False,
            "reason": "exit_condition_false",
            "features_used": {},
        }
        features_used: dict[str, float] = {}

        condition_truthy: bool | None = None
        if rule.condition is not None:
            condition_truthy, condition_features, condition_diag = self._evaluate_condition(rule.condition, snapshot)
            features_used.update(condition_features)
            diagnostics["condition"] = condition_diag

        logical_truthy: bool | None = None
        if rule.logical_exit_rule is not None:
            logical_truthy, logical_diag = self._evaluate_logical_exit_rule(
                rule.logical_exit_rule, snapshot, position_context
            )
            diagnostics["logical_exit_rule"] = logical_diag

        # AND semantics across condition + logical_exit_rule (operator may add
        # OR explicitly using LogicalExitRule kind=HYBRID, operator='any').
        results = [r for r in (condition_truthy, logical_truthy) if r is not None]
        if not results:
            return False, features_used, diagnostics
        is_true = all(results)
        diagnostics["result"] = is_true
        diagnostics["reason"] = "signal_condition_true" if is_true else "exit_condition_false"
        diagnostics["features_used"] = features_used
        return is_true, features_used, diagnostics

    def _evaluate_logical_exit_rule(
        self,
        rule: LogicalExitRule,
        snapshot: FeatureSnapshot,
        ctx: PositionContext,
    ) -> tuple[bool, dict[str, Any]]:
        kind = rule.kind
        if kind == LogicalExitRuleKind.FEATURE_CONDITION:
            assert rule.feature_condition is not None
            is_true, _, condition_diag = self._evaluate_condition(rule.feature_condition, snapshot)
            return is_true, {"kind": kind.value, "result": is_true, "condition": condition_diag}
        if kind == LogicalExitRuleKind.BARS_SINCE_ENTRY:
            assert rule.bars is not None
            actual = ctx.bars_since_entry
            is_true = actual >= rule.bars
            return is_true, {
                "kind": kind.value,
                "result": is_true,
                "bars_required": rule.bars,
                "bars_since_entry": actual,
            }
        if kind == LogicalExitRuleKind.TIME_IN_POSITION_SECONDS:
            assert rule.seconds is not None
            actual_seconds = ctx.seconds_since_entry
            is_true = actual_seconds >= rule.seconds
            return is_true, {
                "kind": kind.value,
                "result": is_true,
                "seconds_required": rule.seconds,
                "seconds_in_position": actual_seconds,
            }
        if kind == LogicalExitRuleKind.TIME_OF_DAY_ET:
            assert rule.time_of_day_et is not None
            current_et = _bar_time_in_et(ctx.bar_timestamp or snapshot.timestamp)
            target = _parse_hhmm(rule.time_of_day_et)
            is_true = current_et is not None and current_et >= target
            return is_true, {
                "kind": kind.value,
                "result": is_true,
                "target_time_et": rule.time_of_day_et,
                "bar_time_et": current_et.isoformat() if current_et else None,
            }
        if kind == LogicalExitRuleKind.MINUTES_BEFORE_SESSION_CLOSE:
            assert rule.minutes_before_close is not None
            current_et = _bar_time_in_et(ctx.bar_timestamp or snapshot.timestamp)
            session_close_minutes = ctx.session_close_et.hour * 60 + ctx.session_close_et.minute
            current_minutes = current_et.hour * 60 + current_et.minute if current_et else 0
            minutes_to_close = session_close_minutes - current_minutes
            is_true = current_et is not None and minutes_to_close <= rule.minutes_before_close
            return is_true, {
                "kind": kind.value,
                "result": is_true,
                "minutes_before_close": rule.minutes_before_close,
                "minutes_to_close_actual": minutes_to_close,
            }
        if kind == LogicalExitRuleKind.SESSION_WINDOW:
            assert rule.session is not None
            current_et = _bar_time_in_et(ctx.bar_timestamp or snapshot.timestamp)
            in_session = current_et is not None and ctx.session_open_et <= current_et <= ctx.session_close_et
            if rule.session == "regular":
                is_true = bool(in_session)
            elif rule.session in {"extended", "premarket", "afterhours"}:
                is_true = current_et is not None and not in_session
            else:
                is_true = False
            return is_true, {
                "kind": kind.value,
                "result": is_true,
                "session": rule.session,
                "in_regular_session": bool(in_session),
            }
        if kind == LogicalExitRuleKind.HYBRID:
            assert rule.operator in {"all", "any"}
            child_results: list[bool] = []
            child_diags: list[dict[str, Any]] = []
            for child in rule.children:
                child_truthy, child_diag = self._evaluate_logical_exit_rule(child, snapshot, ctx)
                child_results.append(child_truthy)
                child_diags.append(child_diag)
            is_true = all(child_results) if rule.operator == "all" else any(child_results)
            return is_true, {
                "kind": kind.value,
                "operator": rule.operator,
                "result": is_true,
                "children": child_diags,
            }
        raise SignalEvaluationError(f"unsupported logical exit rule kind: {kind}")

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


_ET_ZONE = ZoneInfo("America/New_York")


def _bar_time_in_et(timestamp: datetime | None) -> time | None:
    if timestamp is None:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(_ET_ZONE).timetz().replace(tzinfo=None)


def _parse_hhmm(text: str) -> time:
    hours, minutes = text.split(":")
    return time(int(hours), int(minutes))

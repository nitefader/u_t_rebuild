from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.app.decision import SignalEngine, SignalEvaluationError
from backend.app.domain import ConditionGroup, ConditionNode, ConditionOperator, StrategyVersion
from backend.app.domain.strategy import CandidateSide, IntentType, SignalRule
from backend.app.features import FeatureAvailability, FeatureSnapshot, FeatureValue, make_feature_key, parse_feature_expression


def _key(feature_ref: str) -> str:
    return make_feature_key(parse_feature_expression(feature_ref))


def _snapshot(values: dict[str, float | None]) -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 1, 14, 30, tzinfo=timezone.utc),
        values={
            _key(feature_ref): FeatureValue(
                value=value,
                availability=FeatureAvailability.AVAILABLE if value is not None else FeatureAvailability.MISSING,
            )
            for feature_ref, value in values.items()
        },
    )


def _strategy(condition: ConditionNode | ConditionGroup) -> StrategyVersion:
    return StrategyVersion(
        id=uuid4(),
        strategy_id=uuid4(),
        version=1,
        name="Signal Test Strategy",
        entry_rules=[
            SignalRule(
                name="long_signal",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=condition,
            )
        ],
    )


def test_signal_engine_emits_intent_when_condition_true() -> None:
    strategy = _strategy(
        ConditionNode(
            left_feature="5m.close[0]",
            operator=ConditionOperator.GREATER_THAN,
            right_feature="5m.ema:length=20[0]",
        )
    )
    snapshot = _snapshot({"5m.close[0]": 101, "5m.ema:length=20[0]": 100})

    result = SignalEngine().evaluate(strategy, snapshot)

    assert len(result.intents) == 1
    intent = result.intents[0]
    assert intent.symbol == "SPY"
    assert intent.side == CandidateSide.LONG
    assert intent.timestamp == snapshot.timestamp
    assert intent.reason == "signal_condition_true"
    assert intent.feature_values_used["5m.close[0]"] == 101
    assert intent.feature_values_used["5m.ema:length=20[0]"] == 100


def test_signal_engine_emits_no_intent_when_condition_false() -> None:
    strategy = _strategy(
        ConditionNode(
            left_feature="5m.close[0]",
            operator=ConditionOperator.LESS_THAN,
            right_feature="5m.ema:length=20[0]",
        )
    )
    snapshot = _snapshot({"5m.close[0]": 101, "5m.ema:length=20[0]": 100})

    result = SignalEngine().evaluate(strategy, snapshot)

    assert result.intents == ()
    assert result.diagnostics["rules"][0]["reason"] == "signal_condition_false"


def test_signal_engine_diagnostics_include_feature_values() -> None:
    strategy = _strategy(
        ConditionGroup(
            operator="and",
            children=[
                ConditionNode(left_feature="5m.close[0]", operator=ConditionOperator.GREATER_THAN, right_value=100),
                ConditionNode(left_feature="5m.volume[0]", operator=ConditionOperator.GREATER_THAN, right_value=1000),
            ],
        )
    )
    snapshot = _snapshot({"5m.close[0]": 101, "5m.volume[0]": 1500})

    result = SignalEngine().evaluate(strategy, snapshot)

    assert result.intents
    diagnostics = result.diagnostics["rules"][0]
    assert diagnostics["features_used"]["5m.close[0]"] == 101
    assert diagnostics["features_used"]["5m.volume[0]"] == 1500
    assert diagnostics["condition"]["operator"] == "and"


def test_signal_engine_rejects_missing_feature_values() -> None:
    strategy = _strategy(
        ConditionNode(
            left_feature="5m.close[0]",
            operator=ConditionOperator.GREATER_THAN,
            right_feature="5m.ema:length=20[0]",
        )
    )
    snapshot = _snapshot({"5m.close[0]": 101})

    with pytest.raises(SignalEvaluationError, match="missing feature value"):
        SignalEngine().evaluate(strategy, snapshot)


def test_signal_engine_rejects_unavailable_feature_values() -> None:
    strategy = _strategy(
        ConditionNode(
            left_feature="5m.close[0]",
            operator=ConditionOperator.GREATER_THAN,
            right_value=100,
        )
    )
    snapshot = _snapshot({"5m.close[0]": None})

    with pytest.raises(SignalEvaluationError, match="feature value unavailable"):
        SignalEngine().evaluate(strategy, snapshot)


def test_signal_engine_evaluates_crosses_above_from_snapshot_values_only() -> None:
    strategy = _strategy(
        ConditionNode(
            left_feature="5m.close[0]",
            operator=ConditionOperator.CROSS_ABOVE,
            right_feature="5m.ema:length=20[0]",
        )
    )
    snapshot = _snapshot(
        {
            "5m.close[0]": 101,
            "5m.ema:length=20[0]": 100,
            "5m.close[1]": 99,
            "5m.ema:length=20[1]": 100,
        }
    )

    result = SignalEngine().evaluate(strategy, snapshot)

    assert len(result.intents) == 1
    features = result.intents[0].feature_values_used
    assert features["5m.close[0]#previous"] == 99
    assert features["5m.ema:length=20[0]#previous"] == 100


def test_signal_engine_does_not_import_batch_engine_or_compute_features() -> None:
    import backend.app.decision.signal_engine as signal_engine_module

    module_names = {value.__module__ for value in signal_engine_module.__dict__.values() if hasattr(value, "__module__")}

    assert "backend.app.features.batch" not in module_names
    assert "BatchFeatureEngine" not in signal_engine_module.__dict__
    assert "NormalizedBar" not in signal_engine_module.__dict__

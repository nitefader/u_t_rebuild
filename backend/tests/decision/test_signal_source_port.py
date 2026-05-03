from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.app.decision.ports import (
    PositionSignalContext,
    SignalEvaluationContext,
    SignalEvaluationResult,
    SignalSourcePort,
)
from backend.app.domain import (
    CandidateSide,
    ConditionNode,
    ConditionOperator,
    IntentType,
    SignalRule,
    StrategyVersion,
)
from backend.app.features import FeatureSnapshot


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot(
        symbol="SPY",
        timeframe="5m",
        timestamp=datetime(2026, 1, 2, 14, 30, tzinfo=timezone.utc),
    )


def _context() -> SignalEvaluationContext:
    strategy = StrategyVersion(
        id=uuid4(),
        strategy_id=uuid4(),
        version=1,
        name="Port Shape Smoke",
        entry_rules=[
            SignalRule(
                name="close_above_zero",
                side=CandidateSide.LONG,
                intent_type=IntentType.ENTRY,
                condition=ConditionNode(
                    left_feature="5m.close",
                    operator=ConditionOperator.GREATER_THAN,
                    right_value=0,
                ),
            )
        ],
    )
    return SignalEvaluationContext(strategy=strategy)


class _TinySignalSource:
    def evaluate(
        self,
        snapshot: FeatureSnapshot,
        contexts: SignalEvaluationContext,
    ) -> SignalEvaluationResult:
        return SignalEvaluationResult(
            decision="no_signal",
            source="legacy_rule",
            diagnostics={
                "symbol": snapshot.symbol,
                "strategy_name": contexts.strategy.name,
            },
        )


def test_signal_source_port_accepts_structural_implementation() -> None:
    source = _TinySignalSource()

    assert isinstance(source, SignalSourcePort)


def test_signal_source_port_evaluate_returns_unified_result() -> None:
    source = _TinySignalSource()

    result = source.evaluate(_snapshot(), _context())

    assert result.decision == "no_signal"
    assert result.source == "legacy_rule"
    assert result.signal_plan is None
    assert result.candidate_intents == ()
    assert result.diagnostics["symbol"] == "SPY"


def test_signal_evaluation_result_constructs_from_minimal_payload() -> None:
    result = SignalEvaluationResult(decision="no_signal", source="v4_expression")

    assert result.signal_plan is None
    assert result.candidate_intents == ()
    assert result.diagnostics == {}


def test_signal_evaluation_context_accepts_position_contexts() -> None:
    context = SignalEvaluationContext(
        strategy=_context().strategy,
        position_contexts={"SPY": PositionSignalContext(has_position=True)},
    )

    assert context.position_contexts["SPY"].has_position is True

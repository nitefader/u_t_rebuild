from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

import pytest

from backend.app.decision import signal_plan_builder_v4
from backend.app.decision.ports import (
    FeatureSnapshot,
    PositionSignalContext,
    SignalEvaluationContext,
    SignalSourcePort,
)
from backend.app.decision.signal_plan_builder_v4 import (
    ExpressionLoader,
    _default_expression_loader,
    build_signal_plan_from_v4,
)
from backend.app.decision.signal_sources import V4ExpressionSignalSource
from backend.app.decision.signal_sources import v4_expression
from backend.app.domain import CandidateSide, CandidateTradeIntent, IntentType, StrategyVersion
from backend.app.domain.signal_plan import SignalPlan
from backend.app.domain.strategy_v4 import (
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLogicalExitV4,
    StrategyLogicalExitsV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.strategies.expression_engine.ast_nodes import CompiledExpr


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot.model_construct(values={})


def _strategy(expression_text: str) -> StrategyVersionV4:
    return StrategyVersionV4(
        version=1,
        name="Test V4 Strategy",
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(expression_text=expression_text),
        ),
        stops=(
            StrategyStopV4(
                mode="simple",
                simple_type="$",
                simple_value=1.0,
            ),
        ),
        legs=(),
    )


def _context(
    strategy: StrategyVersionV4,
    *,
    evaluation_type: Literal["entry", "logical_exit"] = "entry",
    symbol: str | None = "SPY",
    side: Literal["long", "short"] | None = "long",
    timestamp: datetime | None = datetime(2026, 5, 2, tzinfo=timezone.utc),
    deployment_id: UUID | None = uuid4(),
    watchlist_snapshot_id: UUID | None = None,
    position_contexts: dict[str, PositionSignalContext] | None = None,
) -> SignalEvaluationContext:
    return SignalEvaluationContext(
        strategy=strategy,
        evaluation_type=evaluation_type,
        symbol=symbol,
        side=side,
        timestamp=timestamp,
        deployment_id=deployment_id,
        watchlist_snapshot_id=watchlist_snapshot_id,
        position_contexts=position_contexts or {},
    )


def test_implements_port() -> None:
    adapter = V4ExpressionSignalSource()

    assert isinstance(adapter, SignalSourcePort)


def test_evaluate_returns_emitted_when_builder_yields_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    strategy = _strategy("true")
    snapshot = _snapshot()
    contexts = _context(strategy)
    plan = build_signal_plan_from_v4(
        strategy=strategy,
        snapshot=snapshot,
        symbol="SPY",
        side="long",
        timestamp=contexts.timestamp,
        deployment_id=contexts.deployment_id,
    )
    assert plan is not None

    def fake_builder(
        *,
        strategy: StrategyVersionV4,
        snapshot: FeatureSnapshot,
        symbol: str,
        side: Literal["long", "short"],
        timestamp: datetime,
        deployment_id: UUID,
        watchlist_snapshot_id: UUID | None = None,
        expression_loader: ExpressionLoader = _default_expression_loader,
    ) -> SignalPlan | None:
        return plan

    monkeypatch.setattr(v4_expression, "build_signal_plan_from_v4", fake_builder)

    result = V4ExpressionSignalSource().evaluate(snapshot, contexts)

    assert result.decision == "emitted"
    assert result.source == "v4_expression"
    assert result.signal_plan is plan


def test_evaluate_returns_no_signal_when_builder_returns_none() -> None:
    result = V4ExpressionSignalSource().evaluate(
        _snapshot(),
        _context(_strategy("false")),
    )

    assert result.decision == "no_signal"
    assert result.source == "v4_expression"
    assert result.signal_plan is None


def test_entry_evaluation_type_routes_to_existing_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def fail_exit_evaluator(**_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("logical-exit evaluator should not run for entry")

    def fake_builder(
        *,
        strategy: StrategyVersionV4,
        snapshot: FeatureSnapshot,
        symbol: str,
        side: Literal["long", "short"],
        timestamp: datetime,
        deployment_id: UUID,
        watchlist_snapshot_id: UUID | None = None,
        expression_loader: ExpressionLoader = _default_expression_loader,
    ) -> None:
        calls.append(symbol)
        return None

    monkeypatch.setattr(v4_expression, "evaluate_v4_logical_exits", fail_exit_evaluator)
    monkeypatch.setattr(v4_expression, "build_signal_plan_from_v4", fake_builder)

    result = V4ExpressionSignalSource().evaluate(
        _snapshot(),
        _context(_strategy("false"), evaluation_type="entry"),
    )

    assert result.decision == "no_signal"
    assert calls == ["SPY"]


def test_logical_exit_evaluation_type_routes_to_v4_evaluator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    timestamp = datetime(2026, 5, 2, tzinfo=timezone.utc)
    intent = CandidateTradeIntent(
        timestamp=timestamp,
        symbol="SPY",
        side=CandidateSide.LONG,
        intent_type=IntentType.EXIT,
        signal_name="v4_bars_since_long",
        feature_values_used={},
    )

    def fake_evaluator(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return (intent,), {"bars_since": "diagnostic"}

    monkeypatch.setattr(v4_expression, "evaluate_v4_logical_exits", fake_evaluator)

    result = V4ExpressionSignalSource().evaluate(
        _snapshot(),
        _context(
            _strategy("false"),
            evaluation_type="logical_exit",
            timestamp=timestamp,
            position_contexts={"SPY": PositionSignalContext(has_position=True)},
        ),
    )

    assert result.decision == "emitted"
    assert result.source == "v4_expression"
    assert result.signal_plan is None
    assert result.candidate_intents == (intent,)
    assert result.diagnostics == {"bars_since": "diagnostic"}
    assert calls[0]["symbol"] == "SPY"


def test_logical_exit_missing_symbol_side_timestamp_raises() -> None:
    contexts = SignalEvaluationContext(
        strategy=_strategy("false"),
        evaluation_type="logical_exit",
        deployment_id=uuid4(),
    )

    with pytest.raises(ValueError) as exc_info:
        V4ExpressionSignalSource().evaluate(_snapshot(), contexts)

    message = str(exc_info.value)
    assert "symbol" in message
    assert "side" in message
    assert "timestamp" in message
    assert "deployment_id" not in message


def test_logical_exit_result_shape_populates_candidate_intents() -> None:
    strategy = _strategy("false").model_copy(
        update={
            "logical_exits": StrategyLogicalExitsV4(
                long=(StrategyLogicalExitV4(template_id="bars_since", params={"bars": 1}),),
            )
        }
    )
    result = V4ExpressionSignalSource().evaluate(
        _snapshot(),
        _context(
            strategy,
            evaluation_type="logical_exit",
            position_contexts={
                "SPY": PositionSignalContext(
                    has_position=True,
                    entry_bar_index=0,
                    current_bar_index=1,
                )
            },
        ),
    )

    assert result.decision == "emitted"
    assert result.signal_plan is None
    assert len(result.candidate_intents) == 1


def test_rejects_non_v4_strategy() -> None:
    legacy_strategy = StrategyVersion.model_construct()
    contexts = SignalEvaluationContext(
        strategy=legacy_strategy,
        symbol="SPY",
        side="long",
        timestamp=datetime(2026, 5, 2, tzinfo=timezone.utc),
        deployment_id=uuid4(),
    )

    with pytest.raises(
        TypeError,
        match="V4ExpressionSignalSource requires StrategyVersionV4",
    ):
        V4ExpressionSignalSource().evaluate(_snapshot(), contexts)


def test_rejects_missing_required_context_fields() -> None:
    contexts = SignalEvaluationContext(strategy=_strategy("true"))

    with pytest.raises(ValueError) as exc_info:
        V4ExpressionSignalSource().evaluate(_snapshot(), contexts)

    message = str(exc_info.value)
    assert "symbol" in message
    assert "side" in message
    assert "timestamp" in message
    assert "deployment_id" in message


def test_custom_expression_loader_is_used() -> None:
    calls: list[str] = []

    def recording_loader(text: str, blob: bytes | None) -> CompiledExpr:
        calls.append(text)
        return _default_expression_loader(text, blob)

    result = V4ExpressionSignalSource(
        expression_loader=recording_loader,
    ).evaluate(
        _snapshot(),
        _context(_strategy("true")),
    )

    assert result.decision == "emitted"
    assert calls == ["true"]


def test_port_and_builder_feature_snapshots_are_same_alias() -> None:
    assert FeatureSnapshot is signal_plan_builder_v4.RuntimeFeatureSnapshot

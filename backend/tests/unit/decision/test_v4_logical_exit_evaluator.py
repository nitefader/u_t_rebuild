from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app.decision.ports import PositionSignalContext
from backend.app.decision.v4_logical_exit_evaluator import evaluate_v4_logical_exits
from backend.app.domain import CandidateSide, IntentType
from backend.app.domain.strategy_v4 import (
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLogicalExitV4,
    StrategyLogicalExitsV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.features import FeatureSnapshot


def _snapshot() -> FeatureSnapshot:
    return FeatureSnapshot.model_construct(values={})


def _position_context(
    *,
    has_position: bool = True,
    entry_bar_index: int | None = 0,
    current_bar_index: int | None = 5,
    bar_timestamp: datetime | None = None,
) -> PositionSignalContext:
    return PositionSignalContext(
        has_position=has_position,
        entry_bar_index=entry_bar_index,
        current_bar_index=current_bar_index,
        bar_timestamp=bar_timestamp,
    )


def _strategy(
    template: StrategyLogicalExitV4,
    *,
    side: str = "long",
) -> StrategyVersionV4:
    exits = (
        StrategyLogicalExitsV4(long=(template,))
        if side == "long"
        else StrategyLogicalExitsV4(short=(template,))
    )
    return StrategyVersionV4(
        version=1,
        name="Logical Exit Test",
        entries=StrategyEntriesV4(long=StrategyEntryV4(expression_text="true")),
        stops=(StrategyStopV4(mode="simple", simple_type="%", simple_value=2.0),),
        legs=(),
        logical_exits=exits,
    )


def _template(template_id: str, params: dict[str, object] | None = None) -> StrategyLogicalExitV4:
    if template_id in {"no_progress", "opposite_cross", "session_end", "bars_since"}:
        return StrategyLogicalExitV4(template_id=template_id, params=params or {})
    return StrategyLogicalExitV4.model_construct(template_id=template_id, params=params or {})


def _evaluate(
    template_id: str,
    params: dict[str, object] | None = None,
    *,
    side: str = "long",
    context: PositionSignalContext | None = None,
    timestamp: datetime = datetime(2026, 1, 5, 20, 55, tzinfo=timezone.utc),
):
    return evaluate_v4_logical_exits(
        strategy=_strategy(_template(template_id, params), side=side),
        snapshot=_snapshot(),
        symbol="spy",
        side=side,  # type: ignore[arg-type]
        timestamp=timestamp,
        position_context=context or _position_context(),
    )


def test_bars_since_fires_when_threshold_met() -> None:
    intents, diagnostics = _evaluate("bars_since", {"bars": 5})

    assert diagnostics == {}
    assert len(intents) == 1
    assert intents[0].signal_name == "v4_bars_since_long"


def test_bars_since_waits_until_threshold() -> None:
    intents, diagnostics = _evaluate(
        "bars_since",
        {"bars": 6},
        context=_position_context(current_bar_index=5),
    )

    assert intents == ()
    assert diagnostics == {}


@pytest.mark.parametrize("params", [{}, {"bars": "invalid"}])
def test_bars_since_blocks_on_missing_or_invalid_bars_param(params: dict[str, object]) -> None:
    intents, diagnostics = _evaluate("bars_since", params)

    assert intents == ()
    assert diagnostics == {"bars_since": "bars_since_missing_param"}


def test_session_end_fires_when_within_offset_minutes() -> None:
    intents, diagnostics = _evaluate(
        "session_end",
        {"offset_minutes": 5},
        timestamp=datetime(2026, 1, 5, 20, 57, tzinfo=timezone.utc),
    )

    assert diagnostics == {}
    assert len(intents) == 1
    assert intents[0].signal_name == "v4_session_end_long"


def test_session_end_does_not_fire_well_before_close() -> None:
    intents, diagnostics = _evaluate(
        "session_end",
        {"offset_minutes": 5},
        timestamp=datetime(2026, 1, 5, 20, 40, tzinfo=timezone.utc),
    )

    assert intents == ()
    assert diagnostics == {}


def test_session_end_uses_default_offset_minutes() -> None:
    intents, diagnostics = _evaluate(
        "session_end",
        {},
        timestamp=datetime(2026, 1, 5, 20, 56, tzinfo=timezone.utc),
    )

    assert diagnostics == {}
    assert len(intents) == 1


def test_opposite_cross_is_blocked_with_diagnostic() -> None:
    intents, diagnostics = _evaluate("opposite_cross")

    assert intents == ()
    assert diagnostics == {
        "opposite_cross": "opposite_cross_requires_feature_expression_runtime_wiring"
    }


def test_no_progress_is_blocked_with_diagnostic() -> None:
    intents, diagnostics = _evaluate("no_progress")

    assert intents == ()
    assert diagnostics == {
        "no_progress": "no_progress_requires_feature_expression_runtime_wiring"
    }


def test_unknown_template_is_blocked_with_diagnostic() -> None:
    intents, diagnostics = _evaluate("mystery_exit")

    assert intents == ()
    assert diagnostics == {
        "mystery_exit": "unknown_v4_logical_exit_template:mystery_exit"
    }


def test_no_position_context_returns_reason() -> None:
    intents, diagnostics = _evaluate(
        "bars_since",
        {"bars": 1},
        context=_position_context(has_position=False),
    )

    assert intents == ()
    assert diagnostics == {"reason": "no_open_position"}


def test_intent_shape_maps_side_and_exit_payload() -> None:
    timestamp = datetime(2026, 1, 5, 20, 57, tzinfo=timezone.utc)
    intents, _diagnostics = _evaluate(
        "session_end",
        {"offset_minutes": 5},
        side="short",
        timestamp=timestamp,
    )

    intent = intents[0]
    assert intent.timestamp == timestamp
    assert intent.symbol == "SPY"
    assert intent.side == CandidateSide.SHORT
    assert intent.intent_type == IntentType.EXIT
    assert intent.signal_name == "v4_session_end_short"
    assert intent.reason == "signal_condition_true"
    assert intent.feature_values_used == {}
    assert intent.stop_candidate is None
    assert intent.target_candidate is None
    assert intent.diagnostics == {
        "logical_exit_rule_payload": {
            "template_id": "session_end",
            "params": {"offset_minutes": 5},
        }
    }

"""V4-native logical-exit evaluator.

This module intentionally stays independent from the legacy rule engine and
SignalPlan builders. It reads v4 logical-exit templates and emits candidate
trade intents for the runtime position-management bridge.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from backend.app.decision.ports import PositionSignalContext
from backend.app.domain import CandidateSide, CandidateTradeIntent, IntentType
from backend.app.domain.strategy_v4 import StrategyVersionV4
from backend.app.features import FeatureSnapshot


_ET_ZONE = ZoneInfo("America/New_York")


def evaluate_v4_logical_exits(
    *,
    strategy: StrategyVersionV4,
    snapshot: FeatureSnapshot,
    symbol: str,
    side: Literal["long", "short"],
    timestamp: datetime,
    position_context: PositionSignalContext,
) -> tuple[tuple[CandidateTradeIntent, ...], dict[str, Any]]:
    """Evaluate v4 logical-exit templates for one symbol and active side."""
    _ = snapshot
    if not position_context.has_position:
        return (), {"reason": "no_open_position"}

    intents: list[CandidateTradeIntent] = []
    diagnostics: dict[str, Any] = {}
    templates = strategy.logical_exits.long if side == "long" else strategy.logical_exits.short

    for template in templates:
        template_id = str(getattr(template, "template_id", "unknown"))
        params = getattr(template, "params", {}) or {}
        if template_id == "bars_since":
            bars = _parse_positive_int(params.get("bars"))
            if bars is None:
                diagnostics[template_id] = "bars_since_missing_param"
                continue
            if _bars_since_entry(position_context) >= bars:
                intents.append(
                    _intent(
                        timestamp=timestamp,
                        symbol=symbol,
                        side=side,
                        template_id=template_id,
                        params=params,
                    )
                )
            continue

        if template_id == "session_end":
            offset_minutes = _parse_positive_int(params.get("offset_minutes"), default=5) or 5
            if _minutes_to_session_close(position_context, timestamp) <= offset_minutes:
                intents.append(
                    _intent(
                        timestamp=timestamp,
                        symbol=symbol,
                        side=side,
                        template_id=template_id,
                        params=params,
                    )
                )
            continue

        if template_id == "opposite_cross":
            diagnostics[template_id] = "opposite_cross_requires_feature_expression_runtime_wiring"
            continue

        if template_id == "no_progress":
            diagnostics[template_id] = "no_progress_requires_feature_expression_runtime_wiring"
            continue

        diagnostics[template_id] = f"unknown_v4_logical_exit_template:{template_id}"

    return tuple(intents), diagnostics


def _intent(
    *,
    timestamp: datetime,
    symbol: str,
    side: Literal["long", "short"],
    template_id: str,
    params: Any,
) -> CandidateTradeIntent:
    return CandidateTradeIntent(
        timestamp=timestamp,
        symbol=symbol.upper(),
        side=CandidateSide.LONG if side == "long" else CandidateSide.SHORT,
        intent_type=IntentType.EXIT,
        signal_name=f"v4_{template_id}_{side}",
        reason="signal_condition_true",
        feature_values_used={},
        stop_candidate=None,
        target_candidate=None,
        diagnostics={
            "logical_exit_rule_payload": {
                "template_id": template_id,
                "params": dict(params),
            }
        },
    )


def _parse_positive_int(raw: object, *, default: int | None = None) -> int | None:
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _bars_since_entry(context: PositionSignalContext) -> int:
    if context.current_bar_index is None or context.entry_bar_index is None:
        return 0
    return max(0, context.current_bar_index - context.entry_bar_index)


def _minutes_to_session_close(
    context: PositionSignalContext,
    timestamp: datetime,
) -> float:
    bar_timestamp = context.bar_timestamp or timestamp
    bar_time_et = _bar_datetime_in_et(bar_timestamp)
    close_dt = datetime.combine(
        bar_time_et.date(),
        _plain_time(context.session_close_et),
        tzinfo=_ET_ZONE,
    )
    return (close_dt - bar_time_et).total_seconds() / 60.0


def _bar_datetime_in_et(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(_ET_ZONE)


def _plain_time(value: time) -> time:
    return value.replace(tzinfo=None)

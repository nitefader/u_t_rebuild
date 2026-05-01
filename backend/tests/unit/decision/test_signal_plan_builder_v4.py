from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.app.decision.signal_plan_builder_v4 import build_signal_plan_from_v4
from backend.app.domain.signal_plan import SignalPlanIntent
from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLegV4,
    StrategyStopV4,
    StrategyVersionV4,
)
from backend.app.features import FeatureAvailability, FeatureSnapshot, FeatureValue


def _strategy() -> StrategyVersionV4:
    return StrategyVersionV4(
        version=1,
        name="ATR v4",
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(expression_text="1m.close < 1m.open")
        ),
        stops=(
            StrategyStopV4(
                mode="simple",
                scope="all",
                simple_type="ATR",
                simple_value=2.0,
                feature_requirements=("atr:length=14[0]",),
            ),
        ),
        legs=(
            StrategyLegV4(
                position=1,
                kind="target",
                size_pct=1.0,
                target_type="ATR",
                target_value=4.0,
                on_fill_action=OnFillActionV4(kind="leave"),
            ),
        ),
        feature_requirements=("1m.close", "1m.open", "atr:length=14[0]"),
    )


def _snapshot(*, include_atr: bool) -> FeatureSnapshot:
    values = {
        "1m.close": FeatureValue(value=99.0, availability=FeatureAvailability.AVAILABLE),
        "1m.open": FeatureValue(value=100.0, availability=FeatureAvailability.AVAILABLE),
    }
    if include_atr:
        values["atr:length=14[0]"] = FeatureValue(
            value=1.25,
            availability=FeatureAvailability.AVAILABLE,
        )
    return FeatureSnapshot(
        symbol="TQQQ",
        timeframe="1m",
        timestamp=datetime(2026, 5, 1, 17, 26, tzinfo=timezone.utc),
        values=values,
    )


def test_v4_atr_stop_and_target_emit_atr_rules_when_atr_available() -> None:
    plan = build_signal_plan_from_v4(
        strategy=_strategy(),
        snapshot=_snapshot(include_atr=True),
        symbol="TQQQ",
        side="long",
        timestamp=datetime(2026, 5, 1, 17, 26, tzinfo=timezone.utc),
        deployment_id=uuid4(),
    )

    assert plan is not None
    assert plan.intent == SignalPlanIntent.OPEN
    assert plan.stop is not None
    assert plan.stop.rule == "atr:2.0"
    assert plan.targets[0].rule == "atr:4.0"
    assert plan.feature_snapshot["atr:length=14[0]"] == 1.25


def test_v4_atr_protected_entry_waits_until_atr_available() -> None:
    plan = build_signal_plan_from_v4(
        strategy=_strategy(),
        snapshot=_snapshot(include_atr=False),
        symbol="TQQQ",
        side="long",
        timestamp=datetime(2026, 5, 1, 17, 26, tzinfo=timezone.utc),
        deployment_id=uuid4(),
    )

    assert plan is None

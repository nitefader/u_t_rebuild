from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.app.decision.signal_plan_builder_v4 import build_signal_plan_from_v4
from backend.app.domain.signal_plan import SignalPlanIntent
from backend.app.domain.strategy_v4 import (
    OnFillActionV4,
    StrategyEntriesV4,
    StrategyEntryV4,
    StrategyLegV4,
    StrategyStopV4,
    StrategyVariableV4,
    StrategyVersionV4,
)
from backend.app.features import FeatureAvailability, FeatureSnapshot, FeatureValue
from backend.app.strategies.expression_api import compile_for_storage, load_compiled


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


def test_v4_builder_passes_compiled_blobs_to_loader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, bytes | None]] = []
    real_load_compiled = load_compiled

    def _blob(
        text: str,
        *,
        expression_variable_names: tuple[str, ...] = (),
    ) -> bytes:
        return compile_for_storage(
            real_load_compiled(
                text,
                None,
                expression_variable_names=expression_variable_names,
            )
        )

    variable_blob = _blob("1m.close < 1m.open")
    entry_blob = _blob("bear_bar", expression_variable_names=("bear_bar",))
    stop_blob = _blob("1m.open - 1m.close")

    def recording_load_compiled(
        text: str,
        blob: bytes | None,
        *,
        expression_variable_names=(),
        timeframe_variable_names=(),
    ):
        calls.append((text, blob))
        return real_load_compiled(
            text,
            blob,
            expression_variable_names=expression_variable_names,
            timeframe_variable_names=timeframe_variable_names,
        )

    from backend.app.decision import signal_plan_builder_v4

    monkeypatch.setattr(signal_plan_builder_v4, "load_compiled", recording_load_compiled)

    strategy = StrategyVersionV4(
        version=1,
        name="Blob-backed v4",
        variables=(
            StrategyVariableV4(
                name="bear_bar",
                expression_text="1m.close < 1m.open",
                compiled_blob=variable_blob,
            ),
        ),
        entries=StrategyEntriesV4(
            long=StrategyEntryV4(
                expression_text="bear_bar",
                compiled_blob=entry_blob,
            )
        ),
        stops=(
            StrategyStopV4(
                mode="expression",
                scope="all",
                expression_text="1m.open - 1m.close",
                compiled_blob=stop_blob,
            ),
        ),
        legs=(),
    )

    plan = build_signal_plan_from_v4(
        strategy=strategy,
        snapshot=_snapshot(include_atr=False),
        symbol="TQQQ",
        side="long",
        timestamp=datetime(2026, 5, 1, 17, 26, tzinfo=timezone.utc),
        deployment_id=uuid4(),
    )

    assert plan is not None
    assert calls == [
        ("1m.close < 1m.open", variable_blob),
        ("bear_bar", entry_blob),
        ("1m.open - 1m.close", stop_blob),
    ]

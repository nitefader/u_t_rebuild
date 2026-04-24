from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.decision import SignalEngine, SignalEvaluationError
from backend.app.domain import ChartLabMode, ChartLabSession
from backend.app.features import (
    BatchFeatureEngine,
    FeatureAvailability,
    FeatureFrame,
    FeatureFrameSet,
    FeaturePlan,
    FeatureSnapshot,
    FeatureValue,
    NormalizedBar,
    ResolvedProgramComponents,
    build_feature_plan,
)


class ChartLabFeatureValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_key: str
    value: float | None
    availability: FeatureAvailability
    source_timeframe: str
    source_timestamp: datetime


class ChartLabSignalMarker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    symbol: str
    marker_type: str
    side: str
    reason: str
    signal_name: str


class ChartLabBarPreview(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    timestamp: datetime
    symbol: str
    timeframe: str
    feature_values: tuple[ChartLabFeatureValue, ...]
    signal_markers: tuple[ChartLabSignalMarker, ...] = ()
    condition_truth_tree: dict[str, Any] = Field(default_factory=dict)
    non_fire_reasons: tuple[str, ...] = ()


class ChartLabPreviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session: ChartLabSession
    feature_plan: FeaturePlan
    bars: tuple[ChartLabBarPreview, ...]


class ChartLabPreviewService:
    def __init__(
        self,
        *,
        feature_engine: BatchFeatureEngine | None = None,
        signal_engine: SignalEngine | None = None,
    ) -> None:
        self._feature_engine = feature_engine or BatchFeatureEngine()
        self._signal_engine = signal_engine or SignalEngine()

    def preview_program(
        self,
        *,
        components: ResolvedProgramComponents,
        bars: Sequence[NormalizedBar],
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> ChartLabPreviewResponse:
        session = ChartLabSession(
            id=uuid4(),
            mode=ChartLabMode.PROGRAM_PREVIEW,
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            program_version_id=components.program.id,
        )
        plan = build_feature_plan(components, consumer="chart_lab")
        frame_set = self._feature_engine.compute(plan, bars)
        previews = self._build_previews(
            components=components,
            plan=plan,
            frame_set=frame_set,
            symbol=symbol.upper(),
            base_timeframe=timeframe,
        )
        return ChartLabPreviewResponse(session=session, feature_plan=plan, bars=tuple(previews))

    def _build_previews(
        self,
        *,
        components: ResolvedProgramComponents,
        plan: FeaturePlan,
        frame_set: FeatureFrameSet,
        symbol: str,
        base_timeframe: str,
    ) -> list[ChartLabBarPreview]:
        base_frame = frame_set.frame_for(symbol, base_timeframe)
        frames_by_timeframe = {
            frame.timeframe: frame
            for frame in frame_set.frames
            if frame.symbol == symbol
        }
        previews: list[ChartLabBarPreview] = []
        for base_snapshot in base_frame.snapshots:
            aligned_snapshot, displayed_values = self._aligned_snapshot(
                plan=plan,
                frames_by_timeframe=frames_by_timeframe,
                base_snapshot=base_snapshot,
            )
            signal_markers: tuple[ChartLabSignalMarker, ...] = ()
            condition_truth_tree: dict[str, Any] = {}
            non_fire_reasons: tuple[str, ...] = ()
            try:
                signal_result = self._signal_engine.evaluate(components.strategy, aligned_snapshot)
                condition_truth_tree = signal_result.diagnostics
                signal_markers = tuple(
                    ChartLabSignalMarker(
                        timestamp=intent.timestamp,
                        symbol=intent.symbol,
                        marker_type=f"candidate_{intent.intent_type.value}",
                        side=intent.side.value,
                        reason=intent.reason,
                        signal_name=intent.signal_name,
                    )
                    for intent in signal_result.intents
                )
                if not signal_markers:
                    non_fire_reasons = tuple(
                        rule.get("reason", "signal_condition_false")
                        for rule in signal_result.diagnostics.get("rules", [])
                    )
            except SignalEvaluationError as exc:
                condition_truth_tree = {"error": str(exc)}
                non_fire_reasons = (str(exc),)

            previews.append(
                ChartLabBarPreview(
                    timestamp=base_snapshot.timestamp,
                    symbol=symbol,
                    timeframe=base_timeframe,
                    feature_values=tuple(displayed_values),
                    signal_markers=signal_markers,
                    condition_truth_tree=condition_truth_tree,
                    non_fire_reasons=non_fire_reasons,
                )
            )
        return previews

    def _aligned_snapshot(
        self,
        *,
        plan: FeaturePlan,
        frames_by_timeframe: dict[str, FeatureFrame],
        base_snapshot: FeatureSnapshot,
    ) -> tuple[FeatureSnapshot, list[ChartLabFeatureValue]]:
        values: dict[str, FeatureValue] = {}
        displayed_values: list[ChartLabFeatureValue] = []
        for spec, feature_key in zip(plan.feature_specs, plan.feature_keys, strict=True):
            frame = frames_by_timeframe.get(spec.timeframe)
            if frame is None:
                values[feature_key] = FeatureValue(value=None, availability=FeatureAvailability.MISSING)
                displayed_values.append(
                    ChartLabFeatureValue(
                        feature_key=feature_key,
                        value=None,
                        availability=FeatureAvailability.MISSING,
                        source_timeframe=spec.timeframe,
                        source_timestamp=base_snapshot.timestamp,
                    )
                )
                continue
            source_snapshot = self._latest_snapshot_at_or_before(frame, base_snapshot.timestamp)
            if source_snapshot is None:
                values[feature_key] = FeatureValue(value=None, availability=FeatureAvailability.MISSING)
                displayed_values.append(
                    ChartLabFeatureValue(
                        feature_key=feature_key,
                        value=None,
                        availability=FeatureAvailability.MISSING,
                        source_timeframe=spec.timeframe,
                        source_timestamp=base_snapshot.timestamp,
                    )
                )
                continue
            feature_value = source_snapshot.values[feature_key]
            values[feature_key] = feature_value
            displayed_values.append(
                ChartLabFeatureValue(
                    feature_key=feature_key,
                    value=feature_value.value,
                    availability=feature_value.availability,
                    source_timeframe=spec.timeframe,
                    source_timestamp=source_snapshot.timestamp,
                )
            )
        return (
            FeatureSnapshot(
                symbol=base_snapshot.symbol,
                timeframe=base_snapshot.timeframe,
                timestamp=base_snapshot.timestamp,
                values=values,
            ),
            displayed_values,
        )

    def _latest_snapshot_at_or_before(self, frame: FeatureFrame, timestamp: datetime) -> FeatureSnapshot | None:
        latest: FeatureSnapshot | None = None
        for snapshot in frame.snapshots:
            if snapshot.timestamp <= timestamp:
                latest = snapshot
            else:
                break
        return latest

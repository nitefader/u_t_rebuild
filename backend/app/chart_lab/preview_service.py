from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.decision import SignalEngine, SignalEvaluationError
from backend.app.domain import ChartLabPreviewEvidence, ChartLabSession, TradingMode
from backend.app.domain import StrategyVersion
from backend.app.features import (
    FeatureAvailability,
    FeatureFrame,
    FeatureFrameSet,
    FeaturePlan,
    FeatureSnapshot,
    FeatureValue,
    IncrementalFeatureEngine,
    NormalizedBar,
    ResolvedDeploymentComponents,
    build_feature_plan,
    build_strategy_only_feature_plan,
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
    evidence: ChartLabPreviewEvidence | None = None


class ChartLabPreviewService:
    def __init__(
        self,
        *,
        feature_engine: IncrementalFeatureEngine | None = None,
        signal_engine: SignalEngine | None = None,
        evidence_recorder: object | None = None,
    ) -> None:
        self._feature_engine = feature_engine or IncrementalFeatureEngine()
        self._signal_engine = signal_engine or SignalEngine()
        self._evidence_recorder = evidence_recorder

    def preview_program(
        self,
        *,
        components: ResolvedDeploymentComponents,
        bars: Sequence[NormalizedBar],
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> ChartLabPreviewResponse:
        plan = build_feature_plan(components, consumer="chart_lab")
        return self._run_preview(
            strategy=components.strategy,
            plan=plan,
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )

    def preview_strategy(
        self,
        *,
        strategy: StrategyVersion,
        bars: Sequence[NormalizedBar],
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> ChartLabPreviewResponse:
        """Preview a saved StrategyVersion with no Deployment binding.

        Auto-derives the strategy's features via
        ``build_strategy_only_feature_plan`` and replays them over ``bars``.
        Drafts and frozen versions both work — Chart Lab is research, not
        deployment, so freeze-gating does not apply.
        """
        plan = build_strategy_only_feature_plan(
            strategy,
            default_timeframe=timeframe,
            consumer="chart_lab",
        )
        return self._run_preview(
            strategy=strategy,
            plan=plan,
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
        )

    def _run_preview(
        self,
        *,
        strategy: StrategyVersion,
        plan: FeaturePlan,
        bars: Sequence[NormalizedBar],
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> ChartLabPreviewResponse:
        session = ChartLabSession(
            id=uuid4(),
            mode=TradingMode.CHART_LAB_BATCH,
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            strategy_version_id=strategy.id,
        )
        if not plan.symbols:
            plan = plan.model_copy(update={"symbols": (symbol.upper(),)})
        frame_set = self._feature_engine.compute(plan, bars)
        previews = self._build_previews(
            strategy=strategy,
            plan=plan,
            frame_set=frame_set,
            symbol=symbol.upper(),
            base_timeframe=timeframe,
        )
        evidence = ChartLabPreviewEvidence(
            evidence_id=uuid4(),
            strategy_id=strategy.strategy_id,
            strategy_version_id=strategy.id,
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            feature_snapshot_count=sum(len(preview.feature_values) for preview in previews),
            signal_marker_count=sum(len(preview.signal_markers) for preview in previews),
            metadata={"session_id": str(session.id), "feature_plan_id": str(plan.id)},
        )
        self._save_evidence(evidence)
        return ChartLabPreviewResponse(session=session, feature_plan=plan, bars=tuple(previews), evidence=evidence)

    def _save_evidence(self, evidence: ChartLabPreviewEvidence) -> None:
        if self._evidence_recorder is not None and hasattr(self._evidence_recorder, "save_research_evidence"):
            self._evidence_recorder.save_research_evidence(evidence)

    def _build_previews(
        self,
        *,
        strategy: StrategyVersion,
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
                signal_result = self._signal_engine.evaluate(strategy, aligned_snapshot)
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

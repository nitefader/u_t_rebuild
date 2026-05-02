from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from backend.app.decision import SignalEngine, SignalEvaluationError
from backend.app.domain import ChartLabPreviewEvidence, ChartLabSession, ResearchRunArtifact, TradingMode
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
)
from backend.app.features.registry import registry as feature_registry
from backend.app.features.spec import FeatureSpec


class ChartLabTimeframeMismatchError(ValueError):
    """Raised when the requested preview timeframe has no feature frame.

    ``required_timeframes`` lists the timeframes the feature engine
    produced for the given strategy (derived from the strategy's feature
    expressions). ``requested_timeframe`` is the bar resolution the
    caller supplied. The caller must retry with one of the required
    timeframes.
    """

    def __init__(self, *, required_timeframes: tuple[str, ...], requested_timeframe: str) -> None:
        self.required_timeframes = required_timeframes
        self.requested_timeframe = requested_timeframe
        super().__init__(
            f"no feature frame for {requested_timeframe!r}; "
            f"strategy requires timeframes: {sorted(required_timeframes)}"
        )


class ChartLabFeatureValue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_key: str
    value: float | None
    availability: FeatureAvailability
    source_timeframe: str
    source_timestamp: datetime


ChartLabFeatureOrigin = Literal["derived", "manual"]
ChartLabFeatureGroup = Literal["Trend", "Momentum", "Volatility", "Volume", "Price", "Time"]


class ChartLabFeatureDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feature_key: str
    feature_ref: str
    name: str
    timeframe: str
    indicator_type: str
    group: ChartLabFeatureGroup
    origin: ChartLabFeatureOrigin
    badge: str


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

    bar_index: int
    timestamp: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    is_warmup: bool = False
    feature_values: tuple[ChartLabFeatureValue, ...]
    signal_markers: tuple[ChartLabSignalMarker, ...] = ()
    condition_truth_tree: dict[str, Any] = Field(default_factory=dict)
    non_fire_reasons: tuple[str, ...] = ()


class ChartLabMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    adjustment: str
    total_bars: int
    active_bars: int
    warmup_bars: int
    dataset_count: int
    warnings: tuple[str, ...] = ()


class ChartLabPreviewResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session: ChartLabSession
    feature_plan: FeaturePlan
    features: tuple[ChartLabFeatureDescriptor, ...] = ()
    bars: tuple[ChartLabBarPreview, ...]
    metadata: ChartLabMetadata | None = None
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
        artifact: ResearchRunArtifact | None = None,
        evidence_id: UUID | None = None,
    ) -> ChartLabPreviewResponse:
        if components.strategy is None:
            raise ValueError("Chart Lab preview requires a resolved StrategyVersion")
        plan = build_feature_plan(components, consumer="chart_lab")
        return self.preview_plan(
            strategy=components.strategy,
            plan=plan,
            bars=bars,
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            feature_origins={feature_key: "derived" for feature_key in plan.feature_keys},
            artifact=artifact,
            evidence_id=evidence_id,
        )

    def preview_plan(
        self,
        *,
        strategy: StrategyVersion | None,
        plan: FeaturePlan,
        bars: Sequence[NormalizedBar],
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        feature_origins: Mapping[str, ChartLabFeatureOrigin] | None = None,
        artifact: ResearchRunArtifact | None = None,
        evidence_id: UUID | None = None,
    ) -> ChartLabPreviewResponse:
        session = ChartLabSession(
            id=uuid4(),
            mode=TradingMode.CHART_LAB_BATCH,
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            strategy_version_id=strategy.id if strategy is not None else None,
            metadata={
                "surface": "signal_feature_verification",
                "strategy_mode": strategy is not None,
            },
        )
        if not plan.symbols:
            plan = plan.model_copy(update={"symbols": (symbol.upper(),)})
        frame_set = (
            self._feature_engine.compute(plan, bars)
            if plan.feature_specs
            else FeatureFrameSet(frames=())
        )
        origins = dict(feature_origins or {})
        previews = self._build_previews(
            strategy=strategy,
            plan=plan,
            frame_set=frame_set,
            bars=bars,
            symbol=symbol.upper(),
            base_timeframe=timeframe,
            active_start=start,
        )
        metadata: dict[str, Any] = {"session_id": str(session.id), "feature_plan_id": str(plan.id)}
        if artifact is not None:
            metadata.update(
                {
                    "artifact_id": str(artifact.artifact_id),
                    "deployment_snapshot_id": str(artifact.deployment_snapshot.snapshot_id),
                    "run_kind": artifact.run_kind.value,
                    "producer": artifact.producer,
                }
            )
        evidence = None
        if strategy is not None:
            evidence = ChartLabPreviewEvidence(
                evidence_id=evidence_id or (artifact.run_id if artifact is not None else uuid4()),
                strategy_id=strategy.strategy_id,
                strategy_version_id=strategy.id,
                symbol=symbol.upper(),
                timeframe=timeframe,
                start=start,
                end=end,
                feature_snapshot_count=sum(len(preview.feature_values) for preview in previews),
                signal_marker_count=sum(len(preview.signal_markers) for preview in previews),
                artifact_id=artifact.artifact_id if artifact is not None else None,
                deployment_snapshot_id=(
                    artifact.deployment_snapshot.snapshot_id if artifact is not None else None
                ),
                deployment_snapshot=artifact.deployment_snapshot if artifact is not None else None,
                metadata=metadata,
            )
            self._save_evidence(evidence)
        return ChartLabPreviewResponse(
            session=session,
            feature_plan=plan,
            features=self._feature_descriptors(plan=plan, origins=origins),
            bars=tuple(previews),
            evidence=evidence,
        )

    def _save_evidence(self, evidence: ChartLabPreviewEvidence) -> None:
        if self._evidence_recorder is not None and hasattr(self._evidence_recorder, "save_research_evidence"):
            self._evidence_recorder.save_research_evidence(evidence)

    def _build_previews(
        self,
        *,
        strategy: StrategyVersion | None,
        plan: FeaturePlan,
        frame_set: FeatureFrameSet,
        bars: Sequence[NormalizedBar],
        symbol: str,
        base_timeframe: str,
        active_start: datetime,
    ) -> list[ChartLabBarPreview]:
        base_bars = tuple(
            sorted(
                (
                    bar
                    for bar in bars
                    if bar.symbol.upper() == symbol.upper()
                    and bar.timeframe == base_timeframe
                ),
                key=lambda item: item.timestamp,
            )
        )
        if not base_bars:
            available_timeframes = tuple(
                sorted({frame.timeframe for frame in frame_set.frames if frame.symbol == symbol.upper()})
            )
            raise ChartLabTimeframeMismatchError(
                required_timeframes=available_timeframes,
                requested_timeframe=base_timeframe,
            )
        frames_by_timeframe = {
            frame.timeframe: frame
            for frame in frame_set.frames
            if frame.symbol == symbol
        }
        previews: list[ChartLabBarPreview] = []
        for bar_index, bar in enumerate(base_bars):
            base_snapshot = FeatureSnapshot(
                symbol=symbol,
                timeframe=base_timeframe,
                timestamp=bar.timestamp,
                values={},
            )
            aligned_snapshot, displayed_values = self._aligned_snapshot(
                plan=plan,
                frames_by_timeframe=frames_by_timeframe,
                base_snapshot=base_snapshot,
            )
            is_warmup = bar.timestamp < active_start or any(
                value.availability != FeatureAvailability.AVAILABLE
                for value in displayed_values
            )
            signal_markers: tuple[ChartLabSignalMarker, ...] = ()
            condition_truth_tree: dict[str, Any] = {}
            non_fire_reasons: tuple[str, ...] = ()
            if strategy is not None:
                if is_warmup:
                    non_fire_reasons = ("warmup_bar",)
                else:
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
                    bar_index=bar_index,
                    timestamp=bar.timestamp,
                    symbol=symbol,
                    timeframe=base_timeframe,
                    open=float(bar.open),
                    high=float(bar.high),
                    low=float(bar.low),
                    close=float(bar.close),
                    volume=None if bar.volume is None else float(bar.volume),
                    is_warmup=is_warmup,
                    feature_values=tuple(displayed_values),
                    signal_markers=signal_markers,
                    condition_truth_tree=condition_truth_tree,
                    non_fire_reasons=non_fire_reasons,
                )
            )
        return previews

    def _feature_descriptors(
        self,
        *,
        plan: FeaturePlan,
        origins: Mapping[str, ChartLabFeatureOrigin],
    ) -> tuple[ChartLabFeatureDescriptor, ...]:
        descriptors: list[ChartLabFeatureDescriptor] = []
        for spec, feature_key in zip(plan.feature_specs, plan.feature_keys, strict=True):
            origin = origins.get(feature_key, "manual")
            descriptors.append(
                ChartLabFeatureDescriptor(
                    feature_key=feature_key,
                    feature_ref=_feature_ref(spec),
                    name=_feature_name(spec),
                    timeframe=spec.timeframe,
                    indicator_type=f"{spec.namespace.value}.{spec.kind}",
                    group=_feature_group(spec),
                    origin=origin,
                    badge="Derived from Strategy" if origin == "derived" else "Manual",
                )
            )
        return tuple(descriptors)

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
            feature_value = source_snapshot.values.get(
                feature_key,
                FeatureValue(value=None, availability=FeatureAvailability.MISSING),
            )
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


def _feature_ref(spec: FeatureSpec) -> str:
    params = ",".join(f"{key}={value}" for key, value in dict(spec.params).items())
    param_segment = f":{params}" if params else ""
    lookback_segment = f"[{spec.lookback}]" if spec.lookback else ""
    return f"{spec.timeframe}.{spec.kind}{param_segment}{lookback_segment}"


def _feature_name(spec: FeatureSpec) -> str:
    entry = feature_registry.get(spec.kind)
    params = dict(spec.params)
    if "length" in params:
        return f"{_title_feature(spec.kind)} {params['length']}"
    if spec.kind == "macd":
        output = params.get("output", "line")
        return f"MACD {str(output).title()}"
    if spec.kind in {"opening_range_high", "opening_range_low", "opening_range_mid", "opening_range_width"}:
        minutes = params.get("window_minutes")
        return f"{_title_feature(spec.kind)} {minutes}m" if minutes else _title_feature(spec.kind)
    if entry.namespace.value == "price":
        return _title_feature(spec.kind)
    return _title_feature(spec.kind)


def _title_feature(kind: str) -> str:
    known = {
        "rsi": "RSI",
        "sma": "SMA",
        "ema": "EMA",
        "atr": "ATR",
        "vwap": "VWAP",
        "macd": "MACD",
        "roc": "ROC",
        "ibs": "IBS",
        "fvg_up": "FVG Up",
        "fvg_down": "FVG Down",
    }
    return known.get(kind, kind.replace("_", " ").title())


def _feature_group(spec: FeatureSpec) -> ChartLabFeatureGroup:
    if spec.kind == "volume":
        return "Volume"
    if spec.namespace.value == "price":
        return "Price"
    if spec.namespace.value == "session":
        return "Time"
    if spec.kind in {"atr", "fvg_up", "fvg_down", "opening_range_width", "opening_range_width_pct"}:
        return "Volatility"
    if spec.kind in {"rsi", "macd", "roc", "down_streak", "ibs", "chikou_span"}:
        return "Momentum"
    return "Trend"

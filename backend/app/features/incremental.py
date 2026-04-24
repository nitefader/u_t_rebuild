from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .batch import SUPPORTED_BATCH_KINDS, UnsupportedBatchFeatureError
from .frames import FeatureAvailability, FeatureFrame, FeatureSnapshot, FeatureValue, NormalizedBar
from .key import make_feature_key
from .planner import FeaturePlan
from .registry import FeatureRegistry, registry
from .spec import FeatureNamespace, FeatureScope, FeatureSpec


class IncrementalFeatureEngineError(ValueError):
    """Raised when incremental feature updates cannot proceed safely."""


@dataclass
class _FeatureState:
    spec: FeatureSpec
    feature_key: str
    warmup: int
    index: int = -1
    source_window: deque[float] = field(default_factory=deque)
    rolling_sum: float = 0.0
    previous_ema: float | None = None
    monotonic_window: deque[tuple[int, float]] = field(default_factory=deque)
    base_history: deque[FeatureValue] = field(default_factory=deque)

    def update(self, bar: NormalizedBar) -> FeatureValue:
        self.index += 1
        base_value = self._compute_base_value(bar)
        self.base_history.append(base_value)
        while len(self.base_history) > self.spec.lookback + 1:
            self.base_history.popleft()
        if len(self.base_history) <= self.spec.lookback:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return self.base_history[-(self.spec.lookback + 1)]

    def _compute_base_value(self, bar: NormalizedBar) -> FeatureValue:
        if self.spec.kind in {"open", "high", "low", "close", "volume"}:
            return FeatureValue(value=self._source_value(bar), availability=FeatureAvailability.AVAILABLE)
        if self.spec.kind == "sma":
            return self._update_sma(bar)
        if self.spec.kind == "ema":
            return self._update_ema(bar)
        if self.spec.kind == "highest":
            return self._update_extreme(bar, highest=True)
        if self.spec.kind == "lowest":
            return self._update_extreme(bar, highest=False)
        raise UnsupportedBatchFeatureError(f"unsupported incremental feature '{self.spec.kind}'")

    def _source_value(self, bar: NormalizedBar) -> float:
        source = str(self.spec.params.get("source", self.spec.source))
        if source not in {"open", "high", "low", "close", "volume"}:
            raise UnsupportedBatchFeatureError(f"unsupported source '{source}' for feature '{self.spec.kind}'")
        return float(getattr(bar, source))

    def _update_sma(self, bar: NormalizedBar) -> FeatureValue:
        length = int(self.spec.params["length"])
        value = self._source_value(bar)
        self.source_window.append(value)
        self.rolling_sum += value
        if len(self.source_window) > length:
            self.rolling_sum -= self.source_window.popleft()
        if len(self.source_window) < length:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.rolling_sum / length, availability=FeatureAvailability.AVAILABLE)

    def _update_ema(self, bar: NormalizedBar) -> FeatureValue:
        length = int(self.spec.params["length"])
        alpha = 2 / (length + 1)
        source_value = self._source_value(bar)
        self.previous_ema = (
            source_value
            if self.previous_ema is None
            else alpha * source_value + (1 - alpha) * self.previous_ema
        )
        if self.index < self.warmup - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.previous_ema, availability=FeatureAvailability.AVAILABLE)

    def _update_extreme(self, bar: NormalizedBar, *, highest: bool) -> FeatureValue:
        length = int(self.spec.params["length"])
        source_value = self._source_value(bar)
        should_remove = (
            (lambda existing: existing <= source_value)
            if highest
            else (lambda existing: existing >= source_value)
        )
        while self.monotonic_window and should_remove(self.monotonic_window[-1][1]):
            self.monotonic_window.pop()
        self.monotonic_window.append((self.index, source_value))
        min_index = self.index - length + 1
        while self.monotonic_window and self.monotonic_window[0][0] < min_index:
            self.monotonic_window.popleft()
        if self.index < length - 1:
            return FeatureValue(value=None, availability=FeatureAvailability.WARMUP)
        return FeatureValue(value=self.monotonic_window[0][1], availability=FeatureAvailability.AVAILABLE)


@dataclass
class _FrameState:
    symbol: str
    timeframe: str
    snapshots: list[FeatureSnapshot] = field(default_factory=list)
    last_timestamp: datetime | None = None


class FeatureCache:
    """Rolling state for incremental feature updates.

    The cache is intentionally in-memory and transport-agnostic. A websocket or
    broker adapter can feed completed bars later, but this layer only knows bars.
    """

    def __init__(self) -> None:
        self._frames: dict[tuple[str, str], _FrameState] = {}
        self._feature_states: dict[tuple[str, str, str], _FeatureState] = {}
        self.processed_bar_count = 0

    def frame_for(self, symbol: str, timeframe: str) -> FeatureFrame:
        state = self._frames[(symbol.upper(), timeframe)]
        return FeatureFrame(symbol=state.symbol, timeframe=state.timeframe, snapshots=tuple(state.snapshots))

    def latest_snapshot_at_or_before(
        self,
        *,
        symbol: str,
        timeframe: str,
        timestamp: datetime,
    ) -> FeatureSnapshot | None:
        state = self._frames.get((symbol.upper(), timeframe))
        if state is None:
            return None
        latest: FeatureSnapshot | None = None
        for snapshot in state.snapshots:
            if snapshot.timestamp <= timestamp:
                latest = snapshot
            else:
                break
        return latest

    def _frame_state(self, symbol: str, timeframe: str) -> _FrameState:
        key = (symbol.upper(), timeframe)
        if key not in self._frames:
            self._frames[key] = _FrameState(symbol=symbol.upper(), timeframe=timeframe)
        return self._frames[key]

    def _feature_state(
        self,
        *,
        symbol: str,
        timeframe: str,
        spec: FeatureSpec,
        feature_key: str,
        feature_registry: FeatureRegistry,
    ) -> _FeatureState:
        key = (symbol.upper(), timeframe, feature_key)
        if key not in self._feature_states:
            self._feature_states[key] = _FeatureState(
                spec=spec,
                feature_key=feature_key,
                warmup=feature_registry.warmup_bars(spec),
            )
        return self._feature_states[key]


class IncrementalFeatureUpdate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    frame: FeatureFrame
    snapshot: FeatureSnapshot


class IncrementalFeatureEngine:
    def __init__(self, feature_registry: FeatureRegistry = registry) -> None:
        self._registry = feature_registry

    def update(
        self,
        *,
        plan: FeaturePlan,
        bar: NormalizedBar,
        cache: FeatureCache,
    ) -> IncrementalFeatureUpdate:
        self._validate_supported(plan.feature_specs)
        normalized_bar = bar.model_copy(update={"symbol": bar.symbol.upper()})
        if normalized_bar.symbol not in plan.symbols:
            raise IncrementalFeatureEngineError(f"bar symbol '{normalized_bar.symbol}' is not in feature plan")
        if normalized_bar.timeframe not in plan.timeframes:
            raise IncrementalFeatureEngineError(f"bar timeframe '{normalized_bar.timeframe}' is not in feature plan")

        frame_state = cache._frame_state(normalized_bar.symbol, normalized_bar.timeframe)
        if frame_state.last_timestamp is not None and normalized_bar.timestamp <= frame_state.last_timestamp:
            raise IncrementalFeatureEngineError("incremental updates require strictly increasing completed bars")

        values: dict[str, FeatureValue] = {}
        for spec, feature_key in zip(plan.feature_specs, plan.feature_keys, strict=True):
            if spec.timeframe != normalized_bar.timeframe:
                continue
            feature_state = cache._feature_state(
                symbol=normalized_bar.symbol,
                timeframe=normalized_bar.timeframe,
                spec=spec,
                feature_key=feature_key,
                feature_registry=self._registry,
            )
            values[feature_key] = feature_state.update(normalized_bar)

        snapshot = FeatureSnapshot(
            symbol=normalized_bar.symbol,
            timeframe=normalized_bar.timeframe,
            timestamp=normalized_bar.timestamp,
            values=values,
        )
        frame_state.snapshots.append(snapshot)
        frame_state.last_timestamp = normalized_bar.timestamp
        cache.processed_bar_count += 1
        return IncrementalFeatureUpdate(
            frame=FeatureFrame(
                symbol=frame_state.symbol,
                timeframe=frame_state.timeframe,
                snapshots=tuple(frame_state.snapshots),
            ),
            snapshot=snapshot,
        )

    def _validate_supported(self, specs: tuple[FeatureSpec, ...]) -> None:
        unsupported = [
            f"{spec.timeframe}.{spec.kind}"
            for spec in specs
            if spec.kind not in SUPPORTED_BATCH_KINDS
            or spec.namespace not in {FeatureNamespace.PRICE, FeatureNamespace.TECHNICAL}
            or spec.scope != FeatureScope.SYMBOL
        ]
        if unsupported:
            raise UnsupportedBatchFeatureError(f"unsupported incremental feature(s): {unsupported}")

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from .frames import FeatureAvailability, FeatureFrame, FeatureFrameSet, FeatureSnapshot, FeatureValue, NormalizedBar
from .key import make_feature_key
from .planner import FeaturePlan
from .registry import FeatureRegistry, registry
from .spec import FeatureNamespace, FeatureScope, FeatureSpec


class BatchFeatureEngineError(ValueError):
    """Raised when batch feature computation cannot proceed."""


class UnsupportedBatchFeatureError(BatchFeatureEngineError):
    """Raised when a registry feature has no batch implementation in this skeleton."""


SUPPORTED_BATCH_KINDS = frozenset({"open", "high", "low", "close", "volume", "sma", "ema", "highest", "lowest"})


class BatchFeatureEngine:
    def __init__(self, feature_registry: FeatureRegistry = registry) -> None:
        self._registry = feature_registry

    def compute(self, plan: FeaturePlan, bars: Sequence[NormalizedBar]) -> FeatureFrameSet:
        self._validate_supported(plan.feature_specs)
        bars_by_group: dict[tuple[str, str], list[NormalizedBar]] = defaultdict(list)
        for bar in bars:
            bars_by_group[(bar.symbol.upper(), bar.timeframe)].append(
                NormalizedBar(
                    symbol=bar.symbol.upper(),
                    timeframe=bar.timeframe,
                    timestamp=bar.timestamp,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                )
            )

        frames: list[FeatureFrame] = []
        for symbol in plan.symbols:
            for timeframe in plan.timeframes:
                group_bars = sorted(bars_by_group.get((symbol.upper(), timeframe), []), key=lambda item: item.timestamp)
                if not group_bars:
                    continue
                specs = tuple(spec for spec in plan.feature_specs if spec.timeframe == timeframe)
                if not specs:
                    continue
                computed = {make_feature_key(spec): self._compute_series(spec, group_bars) for spec in specs}
                snapshots: list[FeatureSnapshot] = []
                for index, bar in enumerate(group_bars):
                    values = {
                        feature_key: series[index]
                        for feature_key, series in computed.items()
                    }
                    snapshots.append(
                        FeatureSnapshot(
                            symbol=symbol.upper(),
                            timeframe=timeframe,
                            timestamp=bar.timestamp,
                            values=values,
                        )
                    )
                frames.append(FeatureFrame(symbol=symbol.upper(), timeframe=timeframe, snapshots=tuple(snapshots)))
        return FeatureFrameSet(frames=tuple(frames))

    def _validate_supported(self, specs: Sequence[FeatureSpec]) -> None:
        unsupported = [
            f"{spec.timeframe}.{spec.kind}"
            for spec in specs
            if spec.kind not in SUPPORTED_BATCH_KINDS
            or spec.namespace not in {FeatureNamespace.PRICE, FeatureNamespace.TECHNICAL}
            or spec.scope != FeatureScope.SYMBOL
        ]
        if unsupported:
            raise UnsupportedBatchFeatureError(f"unsupported batch feature(s): {unsupported}")

    def _compute_series(self, spec: FeatureSpec, bars: Sequence[NormalizedBar]) -> list[FeatureValue]:
        if spec.kind in {"open", "high", "low", "close", "volume"}:
            return self._price_series(spec, bars)
        if spec.kind == "sma":
            return self._sma_series(spec, bars)
        if spec.kind == "ema":
            return self._ema_series(spec, bars)
        if spec.kind == "highest":
            return self._window_extreme_series(spec, bars, highest=True)
        if spec.kind == "lowest":
            return self._window_extreme_series(spec, bars, highest=False)
        raise UnsupportedBatchFeatureError(f"unsupported batch feature '{spec.kind}'")

    def _source_values(self, spec: FeatureSpec, bars: Sequence[NormalizedBar]) -> list[float]:
        source = str(spec.params.get("source", spec.source))
        if source not in {"open", "high", "low", "close", "volume"}:
            raise UnsupportedBatchFeatureError(f"unsupported source '{source}' for feature '{spec.kind}'")
        return [float(getattr(bar, source)) for bar in bars]

    def _price_series(self, spec: FeatureSpec, bars: Sequence[NormalizedBar]) -> list[FeatureValue]:
        raw = self._source_values(spec, bars)
        values: list[FeatureValue] = []
        for index in range(len(bars)):
            source_index = index - spec.lookback
            if source_index < 0:
                values.append(FeatureValue(value=None, availability=FeatureAvailability.WARMUP))
            else:
                values.append(FeatureValue(value=raw[source_index], availability=FeatureAvailability.AVAILABLE))
        return values

    def _sma_series(self, spec: FeatureSpec, bars: Sequence[NormalizedBar]) -> list[FeatureValue]:
        source = self._source_values(spec, bars)
        length = int(spec.params["length"])
        base: list[float | None] = []
        for index in range(len(source)):
            if index < length - 1:
                base.append(None)
            else:
                window = source[index - length + 1:index + 1]
                base.append(sum(window) / length)
        return self._apply_lookback(base, spec.lookback)

    def _ema_series(self, spec: FeatureSpec, bars: Sequence[NormalizedBar]) -> list[FeatureValue]:
        source = self._source_values(spec, bars)
        length = int(spec.params["length"])
        alpha = 2 / (length + 1)
        base: list[float | None] = []
        previous: float | None = None
        for value in source:
            previous = value if previous is None else alpha * value + (1 - alpha) * previous
            base.append(previous)
        warmup = self._registry.warmup_bars(spec)
        return self._apply_lookback(base, spec.lookback, warmup=warmup)

    def _window_extreme_series(self, spec: FeatureSpec, bars: Sequence[NormalizedBar], *, highest: bool) -> list[FeatureValue]:
        source = self._source_values(spec, bars)
        length = int(spec.params["length"])
        base: list[float | None] = []
        for index in range(len(source)):
            if index < length - 1:
                base.append(None)
            else:
                window = source[index - length + 1:index + 1]
                base.append(max(window) if highest else min(window))
        return self._apply_lookback(base, spec.lookback)

    def _apply_lookback(self, base: Sequence[float | None], lookback: int, *, warmup: int | None = None) -> list[FeatureValue]:
        values: list[FeatureValue] = []
        for index in range(len(base)):
            source_index = index - lookback
            if source_index < 0:
                values.append(FeatureValue(value=None, availability=FeatureAvailability.WARMUP))
                continue
            value = base[source_index]
            if value is None:
                values.append(FeatureValue(value=None, availability=FeatureAvailability.WARMUP))
                continue
            if warmup is not None and source_index < warmup - 1:
                values.append(FeatureValue(value=None, availability=FeatureAvailability.WARMUP))
                continue
            values.append(FeatureValue(value=value, availability=FeatureAvailability.AVAILABLE))
        return values

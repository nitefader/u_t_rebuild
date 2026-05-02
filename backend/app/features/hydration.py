from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .frames import FeatureAvailability, FeatureSnapshot, FeatureValue, NormalizedBar
from .incremental import FeatureCache, IncrementalFeatureEngine
from .planner import FeaturePlan
from .spec import FeatureScope


class FeatureHydrationBarsRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str
    warmup_bars: int
    as_of: datetime


class FeatureHydrationBarsSource(Protocol):
    def fetch_bars(self, request: FeatureHydrationBarsRequest) -> Iterable[NormalizedBar]:
        """Return recent completed bars for one symbol/timeframe."""


class FeatureHydrationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: FeaturePlan
    symbols: tuple[str, ...]
    as_of: datetime


class FeatureHydrationBlocker(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str
    symbol: str | None = None
    timeframe: str | None = None
    feature_key: str | None = None
    warmup_bars: int | None = None
    bars_seen: int | None = None
    availability: FeatureAvailability | None = None
    error_type: str | None = None
    error: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class FeatureHydrationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    success: bool
    hydrated_feature_keys: tuple[str, ...] = ()
    unavailable_feature_keys: tuple[str, ...] = ()
    blockers: tuple[FeatureHydrationBlocker, ...] = ()
    bars_requested: dict[str, int] = Field(default_factory=dict)
    bars_received: dict[str, int] = Field(default_factory=dict)
    warmup_by_timeframe: dict[str, int] = Field(default_factory=dict)
    replayed_bar_count: int = 0


class FeatureHydrationService:
    """Replay historical bars into the active feature cache."""

    def hydrate(
        self,
        *,
        plan: FeaturePlan,
        symbols: tuple[str, ...],
        as_of: datetime,
        bars_source: FeatureHydrationBarsSource,
        feature_engine: IncrementalFeatureEngine,
        feature_cache: FeatureCache,
    ) -> FeatureHydrationResult:
        request = FeatureHydrationRequest(
            plan=plan,
            symbols=tuple(sorted({symbol.upper() for symbol in symbols})),
            as_of=as_of,
        )
        if not request.plan.feature_keys:
            return FeatureHydrationResult(success=True, warmup_by_timeframe=dict(plan.warmup_by_timeframe))

        blockers: list[FeatureHydrationBlocker] = []
        preblocked_feature_keys: set[tuple[str, str]] = set()
        bars_requested: dict[str, int] = {}
        bars_received: dict[str, int] = {}
        replayed_bar_count = 0

        for symbol in request.symbols:
            for timeframe in request.plan.timeframes:
                if not self._timeframe_has_symbol_features(request.plan, timeframe):
                    continue
                warmup_bars = self._required_warmup_bars(request.plan, timeframe)
                request_key = self._bars_key(symbol=symbol, timeframe=timeframe)
                bars_requested[request_key] = warmup_bars
                bars_request = FeatureHydrationBarsRequest(
                    symbol=symbol,
                    timeframe=timeframe,
                    warmup_bars=warmup_bars,
                    as_of=as_of,
                )
                try:
                    raw_bars = tuple(bars_source.fetch_bars(bars_request))
                except Exception as exc:  # noqa: BLE001 - startup must return an exact blocker.
                    for feature_key, _spec in self._feature_keys_for_timeframe(request.plan, timeframe):
                        preblocked_feature_keys.add((symbol, feature_key))
                        blockers.append(
                            FeatureHydrationBlocker(
                                reason="startup_feature_warmup_failed",
                                symbol=symbol,
                                timeframe=timeframe,
                                feature_key=feature_key,
                                warmup_bars=self._required_warmup_bars_for_feature(
                                    request.plan,
                                    feature_key,
                                    timeframe,
                                ),
                                bars_seen=0,
                                error_type=type(exc).__name__,
                                error=str(exc),
                            )
                        )
                    bars_received[request_key] = 0
                    continue

                bars = self._dedupe_sort_filter_bars(
                    raw_bars,
                    symbol=symbol,
                    timeframe=timeframe,
                    as_of=as_of,
                )
                bars_received[request_key] = len(bars)
                stale_bar_blocked = False
                if bars and self._bars_are_stale(bars=bars, timeframe=timeframe, as_of=as_of):
                    stale_bar_blocked = True
                    last_bar = bars[-1]
                    max_age = self._max_historical_bar_age(timeframe)
                    for feature_key, _spec in self._feature_keys_for_timeframe(request.plan, timeframe):
                        preblocked_feature_keys.add((symbol, feature_key))
                        blockers.append(
                            FeatureHydrationBlocker(
                                reason="stale_historical_bars",
                                symbol=symbol,
                                timeframe=timeframe,
                                feature_key=feature_key,
                                warmup_bars=self._required_warmup_bars_for_feature(
                                    request.plan,
                                    feature_key,
                                    timeframe,
                                ),
                                bars_seen=len(bars),
                                metadata={
                                    "last_bar_timestamp": last_bar.timestamp.isoformat(),
                                    "as_of": as_of.isoformat(),
                                    "max_age_seconds": max_age.total_seconds(),
                                },
                            )
                        )
                for feature_key, _spec in self._feature_keys_for_timeframe(request.plan, timeframe):
                    feature_warmup_bars = self._required_warmup_bars_for_feature(
                        request.plan,
                        feature_key,
                        timeframe,
                    )
                    if len(bars) >= feature_warmup_bars:
                        continue
                    preblocked_feature_keys.add((symbol, feature_key))
                    blockers.append(
                        FeatureHydrationBlocker(
                            reason="missing_historical_bars",
                            symbol=symbol,
                            timeframe=timeframe,
                            feature_key=feature_key,
                            warmup_bars=feature_warmup_bars,
                            bars_seen=len(bars),
                        )
                    )

                if stale_bar_blocked:
                    continue

                for bar in bars:
                    try:
                        feature_engine.update(plan=request.plan, bar=bar, cache=feature_cache)
                    except Exception as exc:  # noqa: BLE001 - exact replay blocker.
                        for feature_key, _spec in self._feature_keys_for_timeframe(request.plan, timeframe):
                            preblocked_feature_keys.add((symbol, feature_key))
                            blockers.append(
                                FeatureHydrationBlocker(
                                    reason="startup_feature_warmup_failed",
                                    symbol=symbol,
                                    timeframe=timeframe,
                                    feature_key=feature_key,
                                    warmup_bars=self._required_warmup_bars_for_feature(
                                        request.plan,
                                        feature_key,
                                        timeframe,
                                    ),
                                    bars_seen=len(bars),
                                    error_type=type(exc).__name__,
                                    error=str(exc),
                                )
                            )
                        break
                    else:
                        replayed_bar_count += 1

        hydrated: set[str] = set()
        unavailable: set[str] = set()
        for symbol in request.symbols:
            for feature_key, feature_value, snapshot in self.latest_feature_values(
                plan=request.plan,
                cache=feature_cache,
                symbol=symbol,
                as_of=as_of,
            ):
                if feature_value.availability == FeatureAvailability.AVAILABLE and feature_value.value is not None:
                    hydrated.add(feature_key)
                    continue
                if (symbol, feature_key) in preblocked_feature_keys:
                    continue
                unavailable.add(feature_key)
                spec = self._spec_for_key(request.plan, feature_key)
                blockers.append(
                    FeatureHydrationBlocker(
                        reason="feature_unavailable_after_warmup",
                        symbol=symbol,
                        timeframe=None if spec is None else spec.timeframe,
                        feature_key=feature_key,
                        warmup_bars=None
                        if spec is None
                        else self._required_warmup_bars_for_feature(request.plan, feature_key, spec.timeframe),
                        bars_seen=None
                        if spec is None
                        else bars_received.get(self._bars_key(symbol=symbol, timeframe=spec.timeframe), 0),
                        availability=feature_value.availability,
                        metadata={
                            "snapshot_timestamp": snapshot.timestamp.isoformat() if snapshot is not None else None,
                        },
                    )
                )

        unique_blockers = self._dedupe_blockers(blockers)
        return FeatureHydrationResult(
            success=not unique_blockers,
            hydrated_feature_keys=tuple(sorted(hydrated)),
            unavailable_feature_keys=tuple(sorted(unavailable)),
            blockers=tuple(unique_blockers),
            bars_requested=bars_requested,
            bars_received=bars_received,
            warmup_by_timeframe={
                timeframe: self._required_warmup_bars(request.plan, timeframe)
                for timeframe in request.plan.timeframes
                if self._timeframe_has_symbol_features(request.plan, timeframe)
            },
            replayed_bar_count=replayed_bar_count,
        )

    @staticmethod
    def latest_feature_values(
        *,
        plan: FeaturePlan,
        cache: FeatureCache,
        symbol: str,
        as_of: datetime,
    ) -> tuple[tuple[str, FeatureValue, FeatureSnapshot | None], ...]:
        values: list[tuple[str, FeatureValue, FeatureSnapshot | None]] = []
        for spec, feature_key in zip(plan.feature_specs, plan.feature_keys, strict=True):
            if spec.scope != FeatureScope.SYMBOL:
                continue
            snapshot = cache.latest_snapshot_at_or_before(
                symbol=symbol,
                timeframe=spec.timeframe,
                timestamp=as_of,
            )
            feature_value = (
                FeatureValue(value=None, availability=FeatureAvailability.MISSING)
                if snapshot is None
                else snapshot.values.get(
                    feature_key,
                    FeatureValue(value=None, availability=FeatureAvailability.MISSING),
                )
            )
            values.append((feature_key, feature_value, snapshot))
        return tuple(values)

    @staticmethod
    def _required_warmup_bars(plan: FeaturePlan, timeframe: str) -> int:
        return max(int(plan.warmup_by_timeframe.get(timeframe, 0)), 1)

    @staticmethod
    def _required_warmup_bars_for_feature(plan: FeaturePlan, feature_key: str, timeframe: str) -> int:
        for requirement in plan.data_requirements:
            if requirement.feature_key == feature_key:
                return max(int(requirement.warmup_bars), 1)
        return FeatureHydrationService._required_warmup_bars(plan, timeframe)

    @staticmethod
    def _timeframe_has_symbol_features(plan: FeaturePlan, timeframe: str) -> bool:
        return any(spec.timeframe == timeframe and spec.scope == FeatureScope.SYMBOL for spec in plan.feature_specs)

    @staticmethod
    def _feature_keys_for_timeframe(plan: FeaturePlan, timeframe: str) -> tuple[tuple[str, object], ...]:
        return tuple(
            (feature_key, spec)
            for spec, feature_key in zip(plan.feature_specs, plan.feature_keys, strict=True)
            if spec.timeframe == timeframe and spec.scope == FeatureScope.SYMBOL
        )

    @staticmethod
    def _bars_key(*, symbol: str, timeframe: str) -> str:
        return f"{symbol.upper()}|{timeframe}"

    @staticmethod
    def _dedupe_sort_filter_bars(
        bars: Iterable[NormalizedBar],
        *,
        symbol: str,
        timeframe: str,
        as_of: datetime,
    ) -> tuple[NormalizedBar, ...]:
        by_timestamp: dict[datetime, NormalizedBar] = {}
        for bar in bars:
            normalized = bar.model_copy(update={"symbol": bar.symbol.upper()})
            if normalized.symbol != symbol.upper() or normalized.timeframe != timeframe:
                continue
            if normalized.timestamp > as_of:
                continue
            by_timestamp[normalized.timestamp] = normalized
        return tuple(by_timestamp[timestamp] for timestamp in sorted(by_timestamp))

    @staticmethod
    def _bars_are_stale(
        *,
        bars: tuple[NormalizedBar, ...],
        timeframe: str,
        as_of: datetime,
    ) -> bool:
        if not bars:
            return False
        return as_of - bars[-1].timestamp > FeatureHydrationService._max_historical_bar_age(timeframe)

    @staticmethod
    def _max_historical_bar_age(timeframe: str) -> timedelta:
        duration = FeatureHydrationService._timeframe_delta(timeframe)
        if duration is None:
            return timedelta(days=14)
        normalized = timeframe.strip().lower()
        if normalized.endswith("mo"):
            return max(duration * 3, timedelta(days=93))
        if normalized.endswith("w"):
            return max(duration * 3, timedelta(days=21))
        if normalized.endswith("d"):
            return max(duration * 4, timedelta(days=10))
        return max(duration * 4, timedelta(days=4))

    @staticmethod
    def _timeframe_delta(timeframe: str) -> timedelta | None:
        normalized = timeframe.strip().lower()
        if normalized.endswith("mo") and normalized[:-2].isdigit():
            return timedelta(days=31 * int(normalized[:-2]))
        if len(normalized) < 2 or not normalized[:-1].isdigit():
            return None
        count = int(normalized[:-1])
        unit = normalized[-1]
        if unit == "m":
            return timedelta(minutes=count)
        if unit == "h":
            return timedelta(hours=count)
        if unit == "d":
            return timedelta(days=count)
        if unit == "w":
            return timedelta(days=7 * count)
        return None

    @staticmethod
    def _spec_for_key(plan: FeaturePlan, feature_key: str):
        for spec, key in zip(plan.feature_specs, plan.feature_keys, strict=True):
            if key == feature_key:
                return spec
        return None

    @staticmethod
    def _dedupe_blockers(blockers: list[FeatureHydrationBlocker]) -> list[FeatureHydrationBlocker]:
        result: list[FeatureHydrationBlocker] = []
        seen: set[tuple[object, ...]] = set()
        for blocker in blockers:
            key = (
                blocker.reason,
                blocker.symbol,
                blocker.timeframe,
                blocker.feature_key,
                blocker.warmup_bars,
                blocker.bars_seen,
                blocker.availability,
                blocker.error_type,
                blocker.error,
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(blocker)
        return result

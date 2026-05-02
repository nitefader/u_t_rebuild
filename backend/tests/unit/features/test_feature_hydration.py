from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from backend.app.features import (
    FeatureAvailability,
    FeatureCache,
    FeatureDataRequirement,
    FeatureHydrationBarsRequest,
    FeatureHydrationService,
    FeaturePlan,
    FeatureScope,
    FeatureSnapshot,
    FeatureSpec,
    FeatureValue,
    IncrementalFeatureEngine,
    NormalizedBar,
    make_feature_key,
    parse_feature_expression,
)
from backend.app.features.spec import FeatureNamespace


AS_OF = datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc)


def _plan(*expressions: str, symbols: tuple[str, ...] = ("SPY",)) -> FeaturePlan:
    specs = tuple(parse_feature_expression(expression) for expression in expressions)
    keys = tuple(make_feature_key(spec) for spec in specs)
    warmup: dict[str, int] = {}
    warmup_by_key: dict[str, int] = {}
    for spec in specs:
        if spec.kind in {"rsi", "atr", "ema"}:
            bars = int(spec.params["length"]) * 3
        elif spec.kind in {"sma", "highest", "lowest"}:
            bars = int(spec.params["length"])
        else:
            bars = 1
        feature_warmup = bars + spec.lookback
        warmup_by_key[make_feature_key(spec)] = feature_warmup
        warmup[spec.timeframe] = max(warmup.get(spec.timeframe, 0), feature_warmup)
    return FeaturePlan(
        strategy_version_id=uuid4(),
        consumer="runtime",
        symbols=symbols,
        timeframes=tuple(sorted({spec.timeframe for spec in specs})),
        feature_specs=specs,
        feature_keys=keys,
        warmup_by_timeframe=warmup,
        data_requirements=tuple(
            FeatureDataRequirement(
                feature_key=key,
                timeframe=spec.timeframe,
                instrument_class="equity",
                requires_streaming=True,
                requires_realtime=True,
                requires_intraday=True,
                requires_historical=False,
                requires_long_range_history=False,
                warmup_bars=warmup_by_key[key],
            )
            for spec, key in zip(specs, keys, strict=True)
        ),
    )


def _bar(
    index: int,
    *,
    symbol: str = "SPY",
    timeframe: str = "1m",
    close: float = 100.0,
) -> NormalizedBar:
    return NormalizedBar(
        symbol=symbol,
        timeframe=timeframe,
        timestamp=AS_OF - timedelta(minutes=1000) + timedelta(minutes=index),
        open=close - 0.5,
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=10_000 + index,
    )


class BarsSource:
    def __init__(self, bars_by_key: dict[tuple[str, str], tuple[NormalizedBar, ...]]) -> None:
        self.bars_by_key = bars_by_key
        self.requests: list[FeatureHydrationBarsRequest] = []

    def fetch_bars(self, request: FeatureHydrationBarsRequest):
        self.requests.append(request)
        return self.bars_by_key.get((request.symbol.upper(), request.timeframe), ())


class RaisingBarsSource:
    def fetch_bars(self, request: FeatureHydrationBarsRequest):
        raise RuntimeError(f"history unavailable for {request.symbol}/{request.timeframe}")


def test_hydrator_warms_atr_from_historical_bars() -> None:
    plan = _plan("1m.atr:length=14[0]")
    source = BarsSource({("SPY", "1m"): tuple(_bar(index, close=100 + index * 0.1) for index in range(42))})
    cache = FeatureCache()

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=source,
        feature_engine=IncrementalFeatureEngine(),
        feature_cache=cache,
    )

    assert result.success is True
    key = plan.feature_keys[0]
    snapshot = cache.latest_snapshot_at_or_before(symbol="SPY", timeframe="1m", timestamp=AS_OF)
    assert snapshot is not None
    assert snapshot.availability_for(key) == FeatureAvailability.AVAILABLE
    assert snapshot.value_for(key) is not None


def test_hydrator_warms_rsi_from_historical_bars() -> None:
    plan = _plan("1m.rsi:length=21[0]")
    source = BarsSource({("SPY", "1m"): tuple(_bar(index, close=100 + index) for index in range(63))})
    cache = FeatureCache()

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=source,
        feature_engine=IncrementalFeatureEngine(),
        feature_cache=cache,
    )

    assert result.success is True
    snapshot = cache.latest_snapshot_at_or_before(symbol="SPY", timeframe="1m", timestamp=AS_OF)
    assert snapshot is not None
    assert snapshot.availability_for(plan.feature_keys[0]) == FeatureAvailability.AVAILABLE
    assert snapshot.value_for(plan.feature_keys[0]) == 100.0


def test_hydrator_handles_multiple_symbols_and_timeframes() -> None:
    plan = _plan("1m.rsi:length=2[0]", "5m.atr:length=2[0]", symbols=("SPY", "QQQ"))
    bars_by_key = {
        ("SPY", "1m"): tuple(_bar(index, symbol="SPY", timeframe="1m", close=100 + index) for index in range(6)),
        ("SPY", "5m"): tuple(_bar(index, symbol="SPY", timeframe="5m", close=100 + index) for index in range(6)),
        ("QQQ", "1m"): tuple(_bar(index, symbol="QQQ", timeframe="1m", close=200 + index) for index in range(6)),
        ("QQQ", "5m"): tuple(_bar(index, symbol="QQQ", timeframe="5m", close=200 + index) for index in range(6)),
    }
    cache = FeatureCache()

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY", "QQQ"),
        as_of=AS_OF,
        bars_source=BarsSource(bars_by_key),
        feature_engine=IncrementalFeatureEngine(),
        feature_cache=cache,
    )

    assert result.success is True
    assert result.bars_requested == {"QQQ|1m": 6, "QQQ|5m": 6, "SPY|1m": 6, "SPY|5m": 6}
    assert cache.latest_snapshot_at_or_before(symbol="SPY", timeframe="1m", timestamp=AS_OF) is not None
    assert cache.latest_snapshot_at_or_before(symbol="QQQ", timeframe="5m", timestamp=AS_OF) is not None


def test_hydrator_dedupes_and_sorts_bars() -> None:
    plan = _plan("1m.close[0]")
    first = _bar(1, close=101.0)
    duplicate = _bar(1, close=111.0)
    latest = _bar(2, close=102.0)
    source = BarsSource({("SPY", "1m"): (latest, first, duplicate)})
    cache = FeatureCache()

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=source,
        feature_engine=IncrementalFeatureEngine(),
        feature_cache=cache,
    )

    assert result.success is True
    frame = cache.frame_for("SPY", "1m")
    assert [snapshot.timestamp for snapshot in frame.snapshots] == [first.timestamp, latest.timestamp]
    assert frame.snapshots[0].value_for(plan.feature_keys[0]) == 111.0


def test_hydrator_returns_exact_blocker_when_bars_are_insufficient() -> None:
    plan = _plan("1m.rsi:length=21[0]")
    source = BarsSource({("SPY", "1m"): tuple(_bar(index, close=100 + index) for index in range(8))})

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=source,
        feature_engine=IncrementalFeatureEngine(),
        feature_cache=FeatureCache(),
    )

    assert result.success is False
    blocker = result.blockers[0]
    assert blocker.reason == "missing_historical_bars"
    assert blocker.feature_key == plan.feature_keys[0]
    assert blocker.symbol == "SPY"
    assert blocker.timeframe == "1m"
    assert blocker.warmup_bars == 63
    assert blocker.bars_seen == 8


def test_hydrator_blocks_stale_historical_bars() -> None:
    plan = _plan("1m.close[0]")
    stale_bars = tuple(
        NormalizedBar(
            symbol="SPY",
            timeframe="1m",
            timestamp=AS_OF - timedelta(days=30) + timedelta(minutes=index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0 + index,
            volume=10_000,
        )
        for index in range(3)
    )
    cache = FeatureCache()

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=BarsSource({("SPY", "1m"): stale_bars}),
        feature_engine=IncrementalFeatureEngine(),
        feature_cache=cache,
    )

    assert result.success is False
    assert result.hydrated_feature_keys == ()
    blocker = result.blockers[0]
    assert blocker.reason == "stale_historical_bars"
    assert blocker.feature_key == plan.feature_keys[0]
    assert blocker.symbol == "SPY"
    assert blocker.timeframe == "1m"
    assert blocker.warmup_bars == 1
    assert blocker.bars_seen == 3
    assert blocker.metadata["last_bar_timestamp"] == stale_bars[-1].timestamp.isoformat()
    assert cache.processed_bar_count == 0


def test_hydrator_replays_available_bars_and_blocks_only_features_missing_warmup() -> None:
    plan = _plan("1m.close[0]", "1m.rsi:length=21[0]")
    cache = FeatureCache()

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=BarsSource({("SPY", "1m"): tuple(_bar(index, close=100 + index) for index in range(8))}),
        feature_engine=IncrementalFeatureEngine(),
        feature_cache=cache,
    )

    close_key = make_feature_key(parse_feature_expression("1m.close[0]"))
    rsi_key = make_feature_key(parse_feature_expression("1m.rsi:length=21[0]"))
    assert result.success is False
    assert result.hydrated_feature_keys == (close_key,)
    assert result.unavailable_feature_keys == ()
    assert [(blocker.reason, blocker.feature_key, blocker.warmup_bars, blocker.bars_seen) for blocker in result.blockers] == [
        ("missing_historical_bars", rsi_key, 63, 8)
    ]
    snapshot = cache.latest_snapshot_at_or_before(symbol="SPY", timeframe="1m", timestamp=AS_OF)
    assert snapshot is not None
    assert snapshot.availability_for(close_key) == FeatureAvailability.AVAILABLE


def test_hydrator_returns_exact_blocker_when_history_source_fails() -> None:
    plan = _plan("1m.atr:length=14[0]")

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=RaisingBarsSource(),
        feature_engine=IncrementalFeatureEngine(),
        feature_cache=FeatureCache(),
    )

    assert result.success is False
    assert result.unavailable_feature_keys == ()
    assert len(result.blockers) == 1
    blocker = result.blockers[0]
    assert blocker.reason == "startup_feature_warmup_failed"
    assert blocker.symbol == "SPY"
    assert blocker.timeframe == "1m"
    assert blocker.feature_key == plan.feature_keys[0]
    assert blocker.warmup_bars == 42
    assert blocker.bars_seen == 0
    assert blocker.error_type == "RuntimeError"
    assert "history unavailable" in (blocker.error or "")


class AlwaysWarmupEngine:
    def update(self, *, plan: FeaturePlan, bar: NormalizedBar, cache: FeatureCache):
        frame_state = cache._frame_state(bar.symbol.upper(), bar.timeframe)  # type: ignore[attr-defined]
        snapshot = FeatureSnapshot(
            symbol=bar.symbol.upper(),
            timeframe=bar.timeframe,
            timestamp=bar.timestamp,
            values={
                plan.feature_keys[0]: FeatureValue(
                    value=None,
                    availability=FeatureAvailability.WARMUP,
                )
            },
        )
        frame_state.snapshots.append(snapshot)
        frame_state.last_timestamp = bar.timestamp
        cache.processed_bar_count += 1


def test_hydrator_returns_exact_blocker_when_feature_stays_unavailable_after_warmup() -> None:
    plan = _plan("1m.close[0]")

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=BarsSource({("SPY", "1m"): (_bar(1),)}),
        feature_engine=AlwaysWarmupEngine(),  # type: ignore[arg-type]
        feature_cache=FeatureCache(),
    )

    assert result.success is False
    assert result.hydrated_feature_keys == ()
    assert result.unavailable_feature_keys == (plan.feature_keys[0],)
    assert len(result.blockers) == 1
    blocker = result.blockers[0]
    assert blocker.reason == "feature_unavailable_after_warmup"
    assert blocker.symbol == "SPY"
    assert blocker.timeframe == "1m"
    assert blocker.feature_key == plan.feature_keys[0]
    assert blocker.warmup_bars == 1
    assert blocker.bars_seen == 1
    assert blocker.availability == FeatureAvailability.WARMUP


class DummyFutureFeatureEngine:
    def __init__(self) -> None:
        self.count = 0

    def update(self, *, plan: FeaturePlan, bar: NormalizedBar, cache: FeatureCache):
        self.count += 1
        frame_state = cache._frame_state(bar.symbol.upper(), bar.timeframe)  # type: ignore[attr-defined]
        values = {
            plan.feature_keys[0]: FeatureValue(
                value=bar.close if self.count >= 3 else None,
                availability=FeatureAvailability.AVAILABLE if self.count >= 3 else FeatureAvailability.WARMUP,
            )
        }
        snapshot = FeatureSnapshot(
            symbol=bar.symbol.upper(),
            timeframe=bar.timeframe,
            timestamp=bar.timestamp,
            values=values,
        )
        frame_state.snapshots.append(snapshot)
        frame_state.last_timestamp = bar.timestamp
        cache.processed_bar_count += 1


def test_hydrator_path_is_feature_agnostic_for_future_engine_supported_features() -> None:
    spec = FeatureSpec(
        kind="hma",
        namespace=FeatureNamespace.TECHNICAL,
        timeframe="1m",
        source="close",
        params={"length": 3},
        scope=FeatureScope.SYMBOL,
    )
    plan = FeaturePlan(
        strategy_version_id=uuid4(),
        consumer="runtime",
        symbols=("SPY",),
        timeframes=("1m",),
        feature_specs=(spec,),
        feature_keys=(make_feature_key(spec),),
        warmup_by_timeframe={"1m": 3},
    )
    cache = FeatureCache()

    result = FeatureHydrationService().hydrate(
        plan=plan,
        symbols=("SPY",),
        as_of=AS_OF,
        bars_source=BarsSource({("SPY", "1m"): tuple(_bar(index, close=100 + index) for index in range(3))}),
        feature_engine=DummyFutureFeatureEngine(),  # type: ignore[arg-type]
        feature_cache=cache,
    )

    assert result.success is True
    assert result.hydrated_feature_keys == (plan.feature_keys[0],)
    snapshot = cache.latest_snapshot_at_or_before(symbol="SPY", timeframe="1m", timestamp=AS_OF)
    assert snapshot is not None
    assert snapshot.value_for(plan.feature_keys[0]) == 102.0

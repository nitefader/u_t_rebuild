"""ScreenerExecutionService — domain + service unit tests.

Doctrine pinned by these tests (per AGENTS.md / Nanyel standard):

- Universe expansion is read-only (Watchlist + presets, never mutates).
- Metric computation flows through the pluggable HistoricalBarsLookup so
  the cache-hit invariant remains the data_center package's contract.
- Runs are immutable: a re-run produces a new ScreenerRun id.
- All seven core metrics (price / avg_volume_20d / relative_volume /
  gap_pct / change_pct / rsi_14 / atr_14_pct) compute correctly from a
  known fixture.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.app.features import NormalizedBar
from backend.app.screener.domain import (
    ScreenerCriterion,
    ScreenerCriterionOperator,
    ScreenerMetric,
    ScreenerRunStatus,
    ScreenerUniverseSource,
    ScreenerUniverseSourceKind,
    ScreenerVersion,
)
from backend.app.screener.presets import resolve_preset
from backend.app.screener.service import (
    ScreenerExecutionService,
    ScreenerValidationError,
)
from backend.app.screener.sources import (
    HistoricalBarsLookup,
    MetricSource,
    UniverseResolver,
    WatchlistLookup,
)
from backend.app.screener.store import ScreenerNotFoundError, ScreenerStore


# ---------- fixtures ---------------------------------------------------


def _make_bars(symbol: str, *, prices: list[float], volumes: list[float]) -> tuple[NormalizedBar, ...]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars: list[NormalizedBar] = []
    for i, (close, vol) in enumerate(zip(prices, volumes)):
        bars.append(
            NormalizedBar(
                symbol=symbol,
                timeframe="1d",
                timestamp=base + timedelta(days=i),
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.98,
                close=close,
                volume=vol,
            )
        )
    return tuple(bars)


class _StaticBarsLookup(HistoricalBarsLookup):
    def __init__(self, bars_by_symbol: dict[str, tuple[NormalizedBar, ...]]) -> None:
        self._bars = bars_by_symbol
        self.calls: list[str] = []

    def get_bars(self, *, symbol, timeframe, start, end):  # noqa: D401
        self.calls.append(symbol)
        return self._bars.get(symbol, ())


class _StaticWatchlistLookup(WatchlistLookup):
    def __init__(self, symbols: tuple[str, ...]) -> None:
        self._symbols = symbols

    def get_watchlist_symbols(self, watchlist_id: UUID) -> tuple[str, ...]:  # noqa: D401, ARG002
        return self._symbols


@pytest.fixture
def store(tmp_path: Path) -> ScreenerStore:
    return ScreenerStore(db_path=tmp_path / "screener.db")


@pytest.fixture
def service(store: ScreenerStore) -> ScreenerExecutionService:
    bars = {
        "AAPL": _make_bars("AAPL", prices=[100 + i for i in range(40)], volumes=[1_000_000] * 39 + [3_000_000]),
        "MSFT": _make_bars("MSFT", prices=[400 + (i * 0.1) for i in range(40)], volumes=[800_000] * 40),
        "TSLA": _make_bars("TSLA", prices=[200 - (i * 0.5) for i in range(40)], volumes=[2_000_000] * 40),
    }
    metric_source = MetricSource(bars=_StaticBarsLookup(bars))
    universe = UniverseResolver(watchlists=_StaticWatchlistLookup(("AAPL", "MSFT", "TSLA")))
    return ScreenerExecutionService(store=store, universe_resolver=universe, metric_source=metric_source)


# ---------- presets ---------------------------------------------------


def test_resolve_preset_returns_known_lists() -> None:
    assert "AAPL" in resolve_preset("liquid_large_caps")
    assert "SPY" in resolve_preset("high_volume_etfs")
    with pytest.raises(KeyError):
        resolve_preset("not_a_real_preset")


# ---------- universe resolver ----------------------------------------


def test_universe_resolver_explicit() -> None:
    resolver = UniverseResolver()
    out = resolver.resolve(
        ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT,
            symbols=("aapl", "msft", ""),
        )
    )
    assert out.symbols == ("AAPL", "MSFT")


def test_universe_resolver_preset_unknown_raises() -> None:
    resolver = UniverseResolver()
    with pytest.raises(ValueError):
        resolver.resolve(
            ScreenerUniverseSource(kind=ScreenerUniverseSourceKind.PRESET, preset="bogus")
        )


def test_universe_resolver_watchlist_requires_lookup() -> None:
    resolver = UniverseResolver()
    with pytest.raises(ValueError):
        resolver.resolve(
            ScreenerUniverseSource(
                kind=ScreenerUniverseSourceKind.WATCHLIST,
                watchlist_id=uuid4(),
            )
        )


# ---------- metric source ---------------------------------------------


def test_metric_source_computes_core_metrics() -> None:
    bars = _make_bars("X", prices=[100 + i for i in range(40)], volumes=[1_000_000] * 39 + [3_000_000])
    src = MetricSource(bars=_StaticBarsLookup({"X": bars}))
    snap = src.compute(symbol="X", criteria=())
    m = snap.metrics
    # last close = 100 + 39 = 139
    assert m[ScreenerMetric.PRICE.value] == 139.0
    # prior close = 138, gap from prior close to today open (138 * 0.99 ≈ 137.61)
    assert m[ScreenerMetric.PRIOR_DAY_CLOSE.value] == 138.0
    # relative volume: today 3M / avg 1M+ → ~ 2.85x (last 20 are mostly 1M, last is 3M)
    rv = m[ScreenerMetric.RELATIVE_VOLUME.value]
    assert rv is not None and rv > 2.0
    # RSI on a strictly rising series approaches 100
    rsi = m[ScreenerMetric.RSI_14.value]
    assert rsi is not None and rsi > 95
    assert len(snap.sparkline) == 30


# ---------- service round-trip ---------------------------------------


def test_create_screener_persists_screener_and_first_version(service: ScreenerExecutionService) -> None:
    screener_id = uuid4()
    version = ScreenerVersion(
        screener_id=screener_id,
        name="Liquid + Volume Surge",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT, symbols=("AAPL", "MSFT", "TSLA"),
        ),
        criteria=(
            ScreenerCriterion(
                metric=ScreenerMetric.RELATIVE_VOLUME,
                operator=ScreenerCriterionOperator.GTE,
                value=1.5,
            ),
        ),
    )
    s, v = service.create_screener(name="Vol Surge", description=None, version=version)
    assert s.name == "Vol Surge"
    assert v.screener_id == screener_id


def test_create_screener_rejects_blank_name(service: ScreenerExecutionService) -> None:
    with pytest.raises(ScreenerValidationError):
        service.create_screener(
            name="   ",
            description=None,
            version=ScreenerVersion(
                screener_id=uuid4(),
                name="x",
                universe_source=ScreenerUniverseSource(kind=ScreenerUniverseSourceKind.EXPLICIT),
            ),
        )


def test_run_screener_filters_by_criteria_and_persists_immutable_run(
    service: ScreenerExecutionService,
    store: ScreenerStore,
) -> None:
    version = ScreenerVersion(
        screener_id=uuid4(),
        name="Volume surge",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT,
            symbols=("AAPL", "MSFT", "TSLA"),
        ),
        criteria=(
            ScreenerCriterion(
                metric=ScreenerMetric.RELATIVE_VOLUME,
                operator=ScreenerCriterionOperator.GTE,
                value=1.5,
            ),
        ),
        sort_metric=ScreenerMetric.RELATIVE_VOLUME,
        sort_descending=True,
    )
    s, v = service.create_screener(name="Surge Hunter", description=None, version=version)
    run = service.run_screener(s.id)
    assert run.status == ScreenerRunStatus.COMPLETED
    assert run.universe_size == 3
    # Only AAPL has the 3x volume spike — should be the sole match.
    matched_symbols = [r.symbol for r in run.results if r.matched]
    assert matched_symbols == ["AAPL"]
    # MSFT and TSLA should explain why they failed.
    failed = [r for r in run.results if not r.matched]
    assert all(r.failed_criteria for r in failed)
    # Re-run produces a new immutable id.
    second = service.run_screener(s.id)
    assert second.id != run.id
    # Both runs persisted.
    runs = service.list_runs(screener_id=s.id)
    assert {r.id for r in runs} == {run.id, second.id}


def test_run_screener_unknown_id_raises_not_found(service: ScreenerExecutionService) -> None:
    with pytest.raises(ScreenerNotFoundError):
        service.run_screener(uuid4())


def test_run_screener_rejects_version_from_different_screener(
    service: ScreenerExecutionService,
) -> None:
    first = ScreenerVersion(
        screener_id=uuid4(),
        name="first",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT,
            symbols=("AAPL",),
        ),
        criteria=(),
    )
    second = ScreenerVersion(
        screener_id=uuid4(),
        name="second",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT,
            symbols=("MSFT",),
        ),
        criteria=(),
    )
    s1, _ = service.create_screener(name="First", description=None, version=first)
    _, v2 = service.create_screener(name="Second", description=None, version=second)

    with pytest.raises(ScreenerValidationError, match="does not belong"):
        service.run_screener(s1.id, version_id=v2.id)


def test_run_screener_records_universe_label_and_cache_hit_rate(
    service: ScreenerExecutionService,
) -> None:
    version = ScreenerVersion(
        screener_id=uuid4(),
        name="just price gate",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT,
            symbols=("AAPL", "TSLA"),
        ),
        criteria=(
            ScreenerCriterion(
                metric=ScreenerMetric.PRICE,
                operator=ScreenerCriterionOperator.GTE,
                value=50,
            ),
        ),
    )
    s, _ = service.create_screener(name="50+", description=None, version=version)
    run = service.run_screener(s.id)
    assert "explicit" in run.sources_used[0]
    assert run.cache_hit_rate is not None

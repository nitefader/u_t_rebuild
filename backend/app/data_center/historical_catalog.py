"""In-memory HistoricalDataSet catalog for Data Center (fixture-backed).

Doctrine: one reusable HistoricalDataSet → many HistoricalBars → many tool
usages. This module backs the read-only inspection API until persistence lands.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

QualityStatus = Literal["ok", "warning", "stale", "unknown"]


class HistoricalBar(BaseModel):
    """Single bar row aligned with operator grid (snake_case JSON)."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    vwap: float | None = None
    trade_count: int | None = None
    provider: str
    quality_status: QualityStatus
    bid: float | None = None
    ask: float | None = None
    spread: float | None = None
    source_feed: str | None = None
    adjusted_close: float | None = None
    corporate_action_flag: bool | None = None
    gap_flag: bool | None = None
    synthetic_bar_flag: bool | None = None


class DatasetUsageRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: str
    last_used_at: str
    note: str = ""


class HistoricalDatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    symbol: str
    timeframe: str
    provider: str
    adjustment_label: str
    bar_count: int
    coverage_start: str
    coverage_end: str
    aggregate_quality_status: QualityStatus


class HistoricalDatasetDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str
    symbol: str
    timeframe: str
    provider: str
    adjustment_label: str
    bar_count: int
    coverage_start: str
    coverage_end: str
    missing_bar_count: int
    warnings: list[str] = Field(default_factory=list)
    aggregate_quality_status: QualityStatus
    provider_decision_markdown: str
    quality_report_markdown: str
    usage_history: list[DatasetUsageRecord] = Field(default_factory=list)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_spy_daily_yahoo_adjusted(rng: random.Random) -> list[HistoricalBar]:
    """~80 US equity sessions of synthetic SPY daily bars."""
    bars: list[HistoricalBar] = []
    px = 448.0 + rng.random() * 4.0
    d = date(2025, 10, 1)
    end = date(2026, 1, 31)
    gap_days = {date(2025, 11, 10), date(2025, 12, 24)}  # synthetic "calendar holes" for warnings

    while d <= end:
        if d.weekday() >= 5:
            d += timedelta(days=1)
            continue
        dt = datetime.combine(d, time(21, 0), tzinfo=timezone.utc)  # regular-session synthetic UTC stamp
        move = rng.gauss(0, 1.1)
        o = px + rng.uniform(-0.35, 0.35)
        c = max(1.0, o + move)
        h = max(o, c) + abs(rng.gauss(0, 0.6))
        l = min(o, c) - abs(rng.gauss(0, 0.55))
        v = float(int(45_000_000 + rng.random() * 25_000_000))
        vwap = (h + l + c) / 3.0
        tc = int(120_000 + rng.random() * 80_000)
        adj = c * (1.0 + rng.uniform(-0.0008, 0.0008)) if rng.random() > 0.12 else c

        q: QualityStatus = "ok"
        if d in gap_days:
            q = "warning"
        if rng.random() < 0.02:
            q = "warning"

        corp = rng.random() < 0.015
        gap_flag = d in gap_days or rng.random() < 0.03
        synth = rng.random() < 0.005

        bars.append(
            HistoricalBar(
                timestamp=_iso(dt),
                open=round(o, 4),
                high=round(h, 4),
                low=round(l, 4),
                close=round(c, 4),
                volume=round(v, 2),
                vwap=round(vwap, 4),
                trade_count=tc,
                provider="yahoo",
                quality_status=q,
                source_feed="yahoo_equity_eod",
                adjusted_close=round(adj, 4),
                corporate_action_flag=corp,
                gap_flag=gap_flag,
                synthetic_bar_flag=synth,
            )
        )
        px = c
        d += timedelta(days=1)

    return bars


def _build_spy_1m_alpaca(rng: random.Random) -> list[HistoricalBar]:
    """Intraday slice with bid/ask/spread on each bar."""
    bars: list[HistoricalBar] = []
    start = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    px = 592.0
    for i in range(240):
        ts = start + timedelta(minutes=i)
        move = rng.gauss(0, 0.12)
        o = px + rng.uniform(-0.04, 0.04)
        c = max(0.01, o + move)
        h = max(o, c) + abs(rng.gauss(0, 0.05))
        l = min(o, c) - abs(rng.gauss(0, 0.05))
        spread = max(0.01, abs(rng.gauss(0.02, 0.008)))
        mid = (h + l + c) / 3.0
        bid = round(mid - spread / 2, 4)
        ask = round(mid + spread / 2, 4)
        v = float(int(8_000 + rng.random() * 35_000))
        vwap = (h + l + c) / 3.0
        bars.append(
            HistoricalBar(
                timestamp=_iso(ts),
                open=round(o, 4),
                high=round(h, 4),
                low=round(l, 4),
                close=round(c, 4),
                volume=round(v, 2),
                vwap=round(vwap, 4),
                trade_count=int(900 + rng.random() * 2200),
                provider="alpaca",
                quality_status="ok",
                bid=bid,
                ask=ask,
                spread=round(ask - bid, 6),
                source_feed="alpaca_sip",
            )
        )
        px = c
    return bars


_rng = random.Random(20260426)
_BARS_BY_ID: dict[str, list[HistoricalBar]] = {
    "spy_1d_yahoo_adjusted": _build_spy_daily_yahoo_adjusted(_rng),
    "spy_1m_alpaca_sip": _build_spy_1m_alpaca(random.Random(91)),
}

_METADATA: dict[str, dict[str, Any]] = {
    "spy_1d_yahoo_adjusted": {
        "symbol": "SPY",
        "timeframe": "1D",
        "provider": "yahoo",
        "adjustment_label": "Adjusted",
        "provider_decision_markdown": (
            "## Provider decision\n\n"
            "- **Primary**: Yahoo Finance EOD for US equities (adjusted series).\n"
            "- **Rationale**: Operator-grade backfill for strategy research before "
            "paid SIP; splits/dividends reflected in `adjusted_close`.\n"
            "- **Fallback**: None in fixture catalog; live stack will use resolver output.\n"
        ),
        "quality_report_markdown": (
            "## Quality report\n\n"
            "- Session stamps are **synthetic UTC** (fixture), not exchange official.\n"
            "- `gap_flag` marks modeled discontinuities for operator drill-down.\n"
            "- VWAP is **approximation** `(H+L+C)/3` — not exchange VWAP.\n"
        ),
        "usage_history": [
            DatasetUsageRecord(
                tool="Backtester",
                last_used_at="2026-01-20T18:22:10Z",
                note="Run #bt-demo-1044 (fixture reference)",
            ),
            DatasetUsageRecord(
                tool="Chart Lab",
                last_used_at="2026-01-18T14:05:00Z",
                note="Visual compare only — not canonical for this dataset",
            ),
        ],
        "warnings_template": (
            "Fixture data: not connected to a live vendor pull. "
            "Missing calendar bars in this slice are flagged for operator training."
        ),
    },
    "spy_1m_alpaca_sip": {
        "symbol": "SPY",
        "timeframe": "1m",
        "provider": "alpaca",
        "adjustment_label": "Unadjusted",
        "provider_decision_markdown": (
            "## Provider decision\n\n"
            "- **Primary**: Alpaca SIP minute aggregates.\n"
            "- **Rationale**: Intraday operator verification path; bid/ask mid anchored.\n"
        ),
        "quality_report_markdown": (
            "## Quality report\n\n"
            "- Each bar includes **bid/ask/spread** for microstructure sanity checks.\n"
            "- Fixture window is short (one synthetic session segment).\n"
        ),
        "usage_history": [
            DatasetUsageRecord(
                tool="Sim Lab",
                last_used_at="2026-01-16T16:40:22Z",
                note="Session #sim-demo-221 (fixture reference)",
            ),
        ],
        "warnings_template": "Fixture intraday slice; extend with real persistence for production.",
    },
}


_QUALITY_RANK: tuple[QualityStatus, ...] = ("ok", "unknown", "warning", "stale")


def _quality_rank(q: QualityStatus) -> int:
    return _QUALITY_RANK.index(q)


def _aggregate_quality(bars: list[HistoricalBar]) -> QualityStatus:
    worst: QualityStatus = "ok"
    for b in bars:
        if _quality_rank(b.quality_status) > _quality_rank(worst):
            worst = b.quality_status
    return worst


_PERSISTED_LOOKUP: Any = None


def configure_persistence(lookup: Any) -> None:
    """Register a callable returning persisted HistoricalDataSet payloads.

    The lookup must implement
    ``list_historical_datasets() -> tuple[dict, ...]`` and
    ``load_historical_dataset(dataset_id: str) -> dict | None``.
    """
    global _PERSISTED_LOOKUP
    _PERSISTED_LOOKUP = lookup


def _persisted_summaries() -> list[HistoricalDatasetSummary]:
    if _PERSISTED_LOOKUP is None:
        return []
    out: list[HistoricalDatasetSummary] = []
    for payload in _PERSISTED_LOOKUP.list_historical_datasets():
        out.append(
            HistoricalDatasetSummary(
                dataset_id=str(payload["dataset_id"]),
                symbol=str(payload["symbol"]).upper(),
                timeframe=str(payload["timeframe"]),
                provider=str(payload["provider"]),
                adjustment_label=str(payload.get("adjustment_policy", "Adjusted")),
                bar_count=int(payload.get("bar_count", 0)),
                coverage_start=str(payload["coverage_start"]),
                coverage_end=str(payload["coverage_end"]),
                aggregate_quality_status=str(payload.get("aggregate_quality_status", "ok")),  # type: ignore[arg-type]
            )
        )
    return out


def _persisted_detail(dataset_id: str) -> HistoricalDatasetDetail | None:
    if _PERSISTED_LOOKUP is None:
        return None
    payload = _PERSISTED_LOOKUP.load_historical_dataset(dataset_id)
    if payload is None:
        return None
    return HistoricalDatasetDetail(
        dataset_id=str(payload["dataset_id"]),
        symbol=str(payload["symbol"]).upper(),
        timeframe=str(payload["timeframe"]),
        provider=str(payload["provider"]),
        adjustment_label=str(payload.get("adjustment_policy", "Adjusted")),
        bar_count=int(payload.get("bar_count", 0)),
        coverage_start=str(payload["coverage_start"]),
        coverage_end=str(payload["coverage_end"]),
        missing_bar_count=0,
        warnings=list(payload.get("data_quality_warnings", [])),
        aggregate_quality_status=str(payload.get("aggregate_quality_status", "ok")),  # type: ignore[arg-type]
        provider_decision_markdown=(
            f"## Provider decision\n\n- **Primary**: {payload['provider']} (live ingest).\n"
            f"- **Adjustment policy**: {payload.get('adjustment_policy', 'split_dividend_adjusted')}.\n"
            f"- **Source request**: `{payload.get('source_request_parameters', {})}`\n"
        ),
        quality_report_markdown=(
            f"## Quality report\n\n- Ingested at {payload.get('ingested_at', '?')} (UTC).\n"
            f"- Timezone: {payload.get('timezone', 'UTC')}.\n"
            f"- Warnings: {len(payload.get('data_quality_warnings', []))}\n"
        ),
        usage_history=[],
    )


def _persisted_bars(dataset_id: str, offset: int, limit: int) -> tuple[list[HistoricalBar], int] | None:
    if _PERSISTED_LOOKUP is None:
        return None
    payload = _PERSISTED_LOOKUP.load_historical_dataset(dataset_id)
    if payload is None:
        return None
    raw_bars = list(payload.get("bars", []))
    bars = [
        HistoricalBar(
            timestamp=str(b["timestamp"]),
            open=float(b["open"]),
            high=float(b["high"]),
            low=float(b["low"]),
            close=float(b["close"]),
            volume=float(b.get("volume") or 0.0),
            provider=str(payload["provider"]),
            quality_status="ok",
        )
        for b in raw_bars
    ]
    total = len(bars)
    off = max(0, offset)
    lim = min(max(limit, 1), 500)
    return bars[off : off + lim], total


def list_dataset_summaries() -> list[HistoricalDatasetSummary]:
    out: list[HistoricalDatasetSummary] = []
    for dataset_id, meta in _METADATA.items():
        bars = _BARS_BY_ID[dataset_id]
        if not bars:
            continue
        out.append(
            HistoricalDatasetSummary(
                dataset_id=dataset_id,
                symbol=meta["symbol"],
                timeframe=meta["timeframe"],
                provider=meta["provider"],
                adjustment_label=meta["adjustment_label"],
                bar_count=len(bars),
                coverage_start=bars[0].timestamp,
                coverage_end=bars[-1].timestamp,
                aggregate_quality_status=_aggregate_quality(bars),
            )
        )
    out.extend(_persisted_summaries())
    return out


def _missing_bar_count(bars: list[HistoricalBar], timeframe: str) -> int:
    """Heuristic: bars explicitly flagged as gaps (fixture teaching signal)."""
    if timeframe.lower() in {"1d", "1day"}:
        return sum(1 for b in bars if b.gap_flag)
    return 0


def get_dataset_detail(dataset_id: str) -> HistoricalDatasetDetail | None:
    meta = _METADATA.get(dataset_id)
    bars = _BARS_BY_ID.get(dataset_id)
    if not meta or bars is None:
        return _persisted_detail(dataset_id)
    warnings = [meta["warnings_template"]]
    wcount = sum(1 for b in bars if b.quality_status == "warning")
    if wcount:
        warnings.append(f"{wcount} bar(s) carry quality_status=warning in this slice.")
    return HistoricalDatasetDetail(
        dataset_id=dataset_id,
        symbol=meta["symbol"],
        timeframe=meta["timeframe"],
        provider=meta["provider"],
        adjustment_label=meta["adjustment_label"],
        bar_count=len(bars),
        coverage_start=bars[0].timestamp,
        coverage_end=bars[-1].timestamp,
        missing_bar_count=_missing_bar_count(bars, meta["timeframe"]),
        warnings=warnings,
        aggregate_quality_status=_aggregate_quality(bars),
        provider_decision_markdown=meta["provider_decision_markdown"],
        quality_report_markdown=meta["quality_report_markdown"],
        usage_history=list(meta["usage_history"]),
    )


def get_dataset_bars(dataset_id: str, offset: int, limit: int) -> tuple[list[HistoricalBar], int] | None:
    bars = _BARS_BY_ID.get(dataset_id)
    if bars is None:
        return _persisted_bars(dataset_id, offset, limit)
    total = len(bars)
    off = max(0, offset)
    lim = min(max(limit, 1), 500)
    slice_ = bars[off : off + lim]
    return slice_, total

"""Metric sources for the Screener.

Two abstractions:

- ``UniverseResolver`` — given a ``ScreenerUniverseSource``, return the
  candidate symbol list before filtering. Pulls from the existing
  Watchlist service or built-in presets; never duplicates Watchlist
  storage.
- ``MetricSource`` — given a symbol + timeframe, compute the metric
  values needed to evaluate every requested ``ScreenerCriterion``.
  Uses the existing ``HistoricalBarIngestService`` so the cache-hit
  invariant holds (no double-fetch of the same historical window).

The Alpaca + market-data flow lives behind ``HistoricalBarIngestService``;
we don't import the Alpaca SDK directly here. That keeps the screener
boundary clean — sources -> ingest service -> Alpaca SDK.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import UUID

from backend.app.features import NormalizedBar

from .domain import (
    ScreenerCriterion,
    ScreenerExpression,
    ScreenerExpressionKind,
    ScreenerMetric,
    ScreenerUniverseSource,
    ScreenerUniverseSourceKind,
)
from .presets import resolve_preset


class WatchlistLookup(Protocol):
    """Read-only contract over the Watchlist service.

    The screener never mutates a watchlist — it expands it to symbols.
    """

    def get_watchlist_symbols(self, watchlist_id: UUID) -> tuple[str, ...]: ...


class HistoricalBarsLookup(Protocol):
    """Read-only contract over the Data Center bar cache.

    Returns bars for the requested symbol + timeframe + window, served
    from cache when present. Implementations wrap
    ``HistoricalBarIngestService`` so the cache-hit invariant holds.
    """

    def get_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> tuple[NormalizedBar, ...]: ...


class MarketListLookup(Protocol):
    """Read-only provider contract for Alpaca-style market lists."""

    def get_market_list_symbols(self, key: str, *, limit: int) -> "MarketListResult": ...


class AssetCapabilityLookup(Protocol):
    """Read-only provider contract for per-symbol Alpaca asset capabilities."""

    def get_asset_capabilities(self, symbol: str) -> "AssetCapabilitySnapshot | None": ...


@dataclass(frozen=True)
class UniverseResolutionResult:
    symbols: tuple[str, ...]
    source_label: str
    evidence: dict[str, object] | None = None


@dataclass(frozen=True)
class MarketListResult:
    key: str
    label: str
    symbols: tuple[str, ...]
    source: str
    freshness: dict[str, object]
    evidence: dict[str, object]


@dataclass(frozen=True)
class AssetCapabilitySnapshot:
    symbol: str
    name: str | None
    status: str | None
    tradable: bool | None
    fractionable: bool | None
    shortable: bool | None
    easy_to_borrow: bool | None
    exchange: str | None
    asset_class: str | None
    source: str = "alpaca_assets"
    unavailable_reason: str | None = None


class UniverseResolver:
    """Expand a ``ScreenerUniverseSource`` into the symbol list to scan."""

    def __init__(
        self,
        *,
        watchlists: WatchlistLookup | None = None,
        market_lists: MarketListLookup | None = None,
    ) -> None:
        self._watchlists = watchlists
        self._market_lists = market_lists

    def resolve(self, source: ScreenerUniverseSource) -> UniverseResolutionResult:
        if source.kind == ScreenerUniverseSourceKind.EXPLICIT:
            return UniverseResolutionResult(
                symbols=tuple(s.upper() for s in source.symbols if s),
                source_label=f"explicit ({len(source.symbols)} symbols)",
            )
        if source.kind == ScreenerUniverseSourceKind.PRESET:
            preset = source.preset or ""
            try:
                symbols = resolve_preset(preset)
            except KeyError as exc:
                raise ValueError(f"unknown preset: {preset}") from exc
            return UniverseResolutionResult(
                symbols=symbols,
                source_label=f"preset:{preset} ({len(symbols)} symbols)",
            )
        if source.kind == ScreenerUniverseSourceKind.WATCHLIST:
            if self._watchlists is None:
                raise ValueError("no Watchlist lookup provided")
            if source.watchlist_id is None:
                raise ValueError("watchlist source requires watchlist_id")
            symbols = self._watchlists.get_watchlist_symbols(source.watchlist_id)
            return UniverseResolutionResult(
                symbols=symbols,
                source_label=f"Watchlist ({len(symbols)} symbols)",
            )
        if source.kind == ScreenerUniverseSourceKind.MARKET_LIST:
            if self._market_lists is None:
                raise ValueError("no market-list provider available")
            key = source.market_list_key or source.preset or ""
            if not key:
                raise ValueError("market_list source requires market_list_key")
            # Alpaca's Screener endpoints cap `top` at 50. Keep the
            # provider request inside that hard limit and let Screener
            # `max_results` handle result-table sizing after evaluation.
            result = self._market_lists.get_market_list_symbols(key, limit=50)
            return UniverseResolutionResult(
                symbols=result.symbols,
                source_label=f"Market list: {result.label} ({len(result.symbols)} symbols)",
                evidence={**result.evidence, "freshness": result.freshness},
            )
        raise ValueError(f"unknown universe kind: {source.kind!r}")


# ---------------------------------------------------------------- metrics


@dataclass(frozen=True)
class MetricSnapshot:
    """All metrics computed for a single symbol on a single run."""

    symbol: str
    metrics: dict[str, bool | float | str | None]
    sparkline: tuple[float, ...]
    evidence: dict[str, object] | None = None


class MetricSource:
    """Compute the per-symbol metrics required by a Screener's criteria.

    The set of metrics requested is the union of every
    ``ScreenerCriterion.metric``; we always compute price + prior_day_close +
    avg_volume_20d so the result row carries enough context for the
    operator to interpret the table even when the screener has no
    explicit liquidity gate.
    """

    def __init__(
        self,
        *,
        bars: HistoricalBarsLookup,
        asset_capabilities: AssetCapabilityLookup | None = None,
    ) -> None:
        self._bars = bars
        self._asset_capabilities = asset_capabilities

    def compute(
        self,
        *,
        symbol: str,
        timeframe: str = "1d",
        criteria: tuple[ScreenerCriterion, ...] = (),
        as_of: datetime | None = None,
    ) -> MetricSnapshot:
        as_of = as_of or datetime.now(timezone.utc)
        metrics: dict[str, bool | float | str | None] = {}
        evidence: dict[str, object] = {}
        capability = self._asset_capabilities.get_asset_capabilities(symbol) if self._asset_capabilities else None
        if capability is not None:
            metrics.update(_capability_metrics(capability))
            evidence["asset_capability"] = {
                "source": capability.source,
                "status": capability.status,
                "exchange": capability.exchange,
                "asset_class": capability.asset_class,
                "unavailable_reason": capability.unavailable_reason,
            }
        # Pull ~60 trading days of daily bars so we can compute 20d-window
        # metrics + a 30-bar sparkline trail.
        start = as_of - timedelta(days=120)
        try:
            bars = self._bars.get_bars(
                symbol=symbol, timeframe=timeframe, start=start, end=as_of,
            )
        except Exception as exc:  # noqa: BLE001 — wrap into operator-readable failure
            return MetricSnapshot(
                symbol=symbol,
                metrics=metrics,
                sparkline=(),
                evidence={**evidence, "error": f"bar metrics unavailable: {exc}"},
            )
        if not bars:
            return MetricSnapshot(
                symbol=symbol,
                metrics=metrics,
                sparkline=(),
                evidence={**evidence, "error": "bar metrics unavailable: provider returned zero bars"},
            )

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        volumes = [b.volume for b in bars]
        last = bars[-1]
        prior = bars[-2] if len(bars) >= 2 else last
        last_window = bars[-20:] if len(bars) >= 20 else bars
        avg_volume_20d = sum(b.volume for b in last_window) / max(1, len(last_window))

        metrics.update(
            {
                ScreenerMetric.PRICE.value: last.close,
                ScreenerMetric.PRIOR_DAY_CLOSE.value: prior.close,
                ScreenerMetric.AVG_VOLUME_20D.value: avg_volume_20d,
                ScreenerMetric.RELATIVE_VOLUME.value: (
                    last.volume / avg_volume_20d if avg_volume_20d > 0 else None
                ),
                ScreenerMetric.GAP_PCT.value: _pct_change(prior.close, last.open),
                ScreenerMetric.CHANGE_PCT.value: _pct_change(prior.close, last.close),
                ScreenerMetric.PRIOR_DAY_RANGE_PCT.value: _range_pct(prior),
                ScreenerMetric.RSI_14.value: _rsi(closes, length=14),
                ScreenerMetric.ATR_14_PCT.value: _atr_pct(highs, lows, closes, length=14),
            }
        )
        evidence["bar_count"] = len(bars)
        # Sparkline = last 30 closes (or fewer when the bar history is short).
        sparkline = tuple(closes[-30:])
        return MetricSnapshot(symbol=symbol, metrics=metrics, sparkline=sparkline, evidence=evidence)


def flatten_expression_criteria(expression: ScreenerExpression | None) -> tuple[ScreenerCriterion, ...]:
    if expression is None:
        return ()
    if expression.kind == ScreenerExpressionKind.CRITERION:
        return (expression.criterion,) if expression.criterion is not None else ()
    criteria: list[ScreenerCriterion] = []
    for child in expression.children:
        criteria.extend(flatten_expression_criteria(child))
    return tuple(criteria)


def _capability_metrics(capability: AssetCapabilitySnapshot) -> dict[str, bool | str | None]:
    active = capability.status.lower() == "active" if capability.status else None
    return {
        ScreenerMetric.BROKER_TRADABLE.value: capability.tradable,
        ScreenerMetric.BROKER_FRACTIONABLE.value: capability.fractionable,
        ScreenerMetric.BROKER_SHORTABLE.value: capability.shortable,
        ScreenerMetric.BROKER_EASY_TO_BORROW.value: capability.easy_to_borrow,
        ScreenerMetric.BROKER_ACTIVE.value: active,
        ScreenerMetric.BROKER_EXCHANGE.value: capability.exchange,
        ScreenerMetric.BROKER_ASSET_CLASS.value: capability.asset_class,
        ScreenerMetric.BROKER_NAME.value: capability.name,
    }


class AlpacaAssetCapabilityLookup:
    """Adapter for Alpaca Trading Assets.

    Accepts any client with ``get_asset(symbol)`` or ``get_all_assets(...)`` so
    tests can use fakes and production can use alpaca-py ``TradingClient``.
    """

    def __init__(self, client: Any) -> None:
        self._client = client
        self._cache: dict[str, AssetCapabilitySnapshot | None] = {}

    def get_asset_capabilities(self, symbol: str) -> AssetCapabilitySnapshot | None:
        normalized = symbol.upper()
        if normalized in self._cache:
            return self._cache[normalized]
        try:
            raw = self._fetch_asset(normalized)
        except Exception as exc:  # noqa: BLE001
            snapshot = AssetCapabilitySnapshot(
                symbol=normalized,
                name=None,
                status=None,
                tradable=None,
                fractionable=None,
                shortable=None,
                easy_to_borrow=None,
                exchange=None,
                asset_class=None,
                unavailable_reason=str(exc),
            )
            self._cache[normalized] = snapshot
            return snapshot
        snapshot = _asset_snapshot(raw, symbol=normalized)
        self._cache[normalized] = snapshot
        return snapshot

    def _fetch_asset(self, symbol: str) -> Any:
        if hasattr(self._client, "get_asset"):
            return self._client.get_asset(symbol)
        if hasattr(self._client, "get_all_assets"):
            for asset in self._client.get_all_assets():
                payload = _object_to_dict(asset)
                if str(payload.get("symbol", "")).upper() == symbol:
                    return asset
        raise RuntimeError(f"Alpaca asset {symbol} not found")


class AlpacaMarketListLookup:
    """Adapter for Alpaca Screener market lists."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def get_market_list_symbols(self, key: str, *, limit: int) -> MarketListResult:
        normalized = key.strip().lower().replace("-", "_")
        if normalized in {"day_gainers", "day_losers"}:
            response = self._market_movers(limit=limit)
            side = "gainers" if normalized == "day_gainers" else "losers"
            rows = _extract_rows(response, side)
            label = "Day Gainers" if side == "gainers" else "Day Losers"
        elif normalized in {"most_active", "most_actives"}:
            response = self._most_actives(limit=limit)
            rows = _extract_rows(response, "most_actives", "most_actives_by_volume", "most_actives_by_trades")
            label = "Most Active"
        else:
            raise ValueError(f"unsupported Alpaca market list: {key}")
        symbols = tuple(dict.fromkeys(_row_symbol(row) for row in rows if _row_symbol(row)))[:limit]
        return MarketListResult(
            key=normalized,
            label=label,
            symbols=symbols,
            source="alpaca_screener",
            freshness={"cadence": "real-time SIP when available", "provider": "Alpaca"},
            evidence={"provider": "alpaca", "source": "alpaca_screener", "row_count": len(rows)},
        )

    def _market_movers(self, *, limit: int) -> Any:
        if hasattr(self._client, "get_market_movers"):
            return self._client.get_market_movers(_request_object("MarketMoversRequest", market_type="stocks", top=limit))
        if hasattr(self._client, "market_movers"):
            return self._client.market_movers(market_type="stocks", top=limit)
        raise RuntimeError("Alpaca screener client does not expose market movers")

    def _most_actives(self, *, limit: int) -> Any:
        if hasattr(self._client, "get_most_actives"):
            return self._client.get_most_actives(_request_object("MostActivesRequest", top=limit))
        if hasattr(self._client, "most_actives"):
            return self._client.most_actives(top=limit)
        raise RuntimeError("Alpaca screener client does not expose most actives")


def _request_object(class_name: str, **kwargs: object) -> object:
    try:
        from alpaca.data.requests import MarketMoversRequest, MostActivesRequest
    except ImportError:
        return dict(kwargs)
    mapping = {
        "MarketMoversRequest": MarketMoversRequest,
        "MostActivesRequest": MostActivesRequest,
    }
    request_class = mapping[class_name]
    return request_class(**kwargs)


def _extract_rows(response: Any, *keys: str) -> tuple[Any, ...]:
    payload = _object_to_dict(response)
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list | tuple):
            return tuple(rows)
    data = payload.get("data")
    if isinstance(data, dict):
        for key in keys:
            rows = data.get(key)
            if isinstance(rows, list | tuple):
                return tuple(rows)
    if isinstance(response, list | tuple):
        return tuple(response)
    return ()


def _row_symbol(row: Any) -> str:
    payload = _object_to_dict(row)
    return str(payload.get("symbol", "")).upper()


def _asset_snapshot(raw: Any, *, symbol: str) -> AssetCapabilitySnapshot:
    payload = _object_to_dict(raw)
    status = _enum_text(payload.get("status"))
    return AssetCapabilitySnapshot(
        symbol=symbol,
        name=_optional_text(payload.get("name")),
        status=status,
        tradable=_optional_bool(payload.get("tradable")),
        fractionable=_optional_bool(payload.get("fractionable")),
        shortable=_optional_bool(payload.get("shortable")),
        easy_to_borrow=_optional_bool(payload.get("easy_to_borrow")),
        exchange=_enum_text(payload.get("exchange")),
        asset_class=_enum_text(payload.get("asset_class") or payload.get("class")),
    )


def _object_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    keys = (
        "symbol",
        "name",
        "status",
        "tradable",
        "fractionable",
        "shortable",
        "easy_to_borrow",
        "exchange",
        "asset_class",
        "class",
        "gainers",
        "losers",
        "most_actives",
    )
    return {key: getattr(value, key) for key in keys if hasattr(value, key)}


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _enum_text(value)
    return text if text else None


def _enum_text(value: Any) -> str | None:
    if value is None:
        return None
    raw = getattr(value, "value", value)
    return str(raw)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


# ---------------------------------------------------------------- math


def _pct_change(base: float, current: float) -> float | None:
    if base is None or base == 0:
        return None
    return ((current - base) / base) * 100.0


def _range_pct(bar: NormalizedBar) -> float | None:
    if bar.open == 0:
        return None
    return ((bar.high - bar.low) / bar.open) * 100.0


def _rsi(closes: list[float], *, length: int = 14) -> float | None:
    if len(closes) < length + 1:
        return None
    gains: list[float] = []
    losses: list[float] = []
    for prev, curr in zip(closes[-length - 1 : -1], closes[-length:]):
        change = curr - prev
        if change >= 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-change)
    avg_gain = sum(gains) / length
    avg_loss = sum(losses) / length
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr_pct(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    *,
    length: int = 14,
) -> float | None:
    if len(closes) < length + 1:
        return None
    trs: list[float] = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    last_window = trs[-length:]
    atr = sum(last_window) / length
    last_close = closes[-1]
    if last_close == 0:
        return None
    return (atr / last_close) * 100.0

"""HistoricalBarIngestService — populate Data Center on demand from Alpaca / Yahoo.

Cache-hit invariant: a request matching ``(provider, symbol, timeframe,
[start, end] ⊆ stored window, adjustment_policy)`` MUST be served from Data
Center with zero provider calls. Only a true gap (missing range, stricter
adjustment policy) triggers a fetch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from backend.app.broker_accounts.models import BrokerAccountValidationStatus
from backend.app.domain._base import utc_now
from backend.app.features import NormalizedBar


AdjustmentPolicy = Literal["split_dividend_adjusted", "split_only", "raw"]
ProviderName = Literal["alpaca", "yahoo"]


@dataclass(frozen=True)
class HistoricalBarIngestRequest:
    provider: ProviderName
    symbol: str
    timeframe: str
    start: datetime
    end: datetime
    adjustment_policy: AdjustmentPolicy = "split_dividend_adjusted"


@dataclass(frozen=True)
class HistoricalBarIngestResult:
    dataset_id: UUID
    bars: tuple[NormalizedBar, ...]
    fetched_from_provider: bool
    data_quality_warnings: tuple[str, ...]


class HistoricalBarSource(Protocol):
    """Adapter contract: pull bars from one external provider."""

    name: str

    def fetch(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjustment_policy: AdjustmentPolicy,
    ) -> tuple[tuple[NormalizedBar, ...], dict[str, Any]]:
        """Return (bars, source_request_parameters_for_audit)."""
        ...


class HistoricalDatasetStore(Protocol):
    """Persistence contract for HistoricalDataSet rows + bar payloads."""

    def find_historical_dataset(
        self,
        *,
        provider: str,
        symbol: str,
        timeframe: str,
        adjustment_policy: str,
    ) -> dict[str, Any] | None: ...

    def save_historical_dataset(self, payload: dict[str, Any], *, dataset_id: str) -> None: ...

    def list_historical_datasets(self) -> tuple[dict[str, Any], ...]: ...


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_bar(
    *,
    raw: dict[str, Any],
    symbol: str,
    timeframe: str,
) -> NormalizedBar:
    timestamp = raw["timestamp"]
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return NormalizedBar(
        symbol=symbol.upper(),
        timeframe=timeframe,
        timestamp=_ensure_utc(timestamp),
        open=float(raw["open"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        volume=float(raw.get("volume") or 0.0),
    )


def _bars_to_payload(bars: tuple[NormalizedBar, ...]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": bar.timestamp.isoformat(),
            "open": bar.open,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for bar in bars
    ]


def _payload_to_bars(payload: list[dict[str, Any]], *, symbol: str, timeframe: str) -> tuple[NormalizedBar, ...]:
    return tuple(
        _normalize_bar(raw=raw, symbol=symbol, timeframe=timeframe) for raw in payload
    )


def _dedupe_bars(bars: tuple[NormalizedBar, ...]) -> tuple[NormalizedBar, ...]:
    by_key: dict[tuple[str, str, datetime], NormalizedBar] = {}
    for bar in bars:
        by_key[(bar.symbol.upper(), bar.timeframe, _ensure_utc(bar.timestamp))] = bar
    return tuple(by_key[key] for key in sorted(by_key, key=lambda item: (item[2], item[0], item[1])))


class HistoricalBarIngestService:
    """Cache-aware fetch + persist for Data Center historical bars.

    The service guarantees cache-hit zero-call: a re-request matching the
    canonical key (provider, symbol, timeframe, [start, end] ⊆ stored window,
    adjustment_policy) is served from Data Center without contacting the
    provider.
    """

    def __init__(
        self,
        *,
        store: HistoricalDatasetStore,
        sources: dict[str, HistoricalBarSource],
        clock: Any = None,
    ) -> None:
        self._store = store
        self._sources = sources
        self._clock = clock or utc_now

    def ensure_bars(self, request: HistoricalBarIngestRequest) -> HistoricalBarIngestResult:
        if request.start >= request.end:
            raise ValueError("start must be before end")

        existing = self._store.find_historical_dataset(
            provider=request.provider,
            symbol=request.symbol,
            timeframe=request.timeframe,
            adjustment_policy=request.adjustment_policy,
        )
        requested_start = _ensure_utc(request.start)
        requested_end = _ensure_utc(request.end)

        if existing is not None:
            stored_start = datetime.fromisoformat(str(existing["coverage_start"]).replace("Z", "+00:00"))
            stored_end = datetime.fromisoformat(str(existing["coverage_end"]).replace("Z", "+00:00"))
            stored_start = _ensure_utc(stored_start)
            stored_end = _ensure_utc(stored_end)
            existing_bars = _payload_to_bars(
                list(existing.get("bars", [])),
                symbol=request.symbol,
                timeframe=request.timeframe,
            )
            if stored_start <= requested_start and stored_end >= requested_end:
                window_bars = tuple(
                    bar for bar in existing_bars
                    if requested_start <= _ensure_utc(bar.timestamp) <= requested_end
                )
                return HistoricalBarIngestResult(
                    dataset_id=UUID(str(existing["dataset_id"])),
                    bars=window_bars,
                    fetched_from_provider=False,
                    data_quality_warnings=tuple(existing.get("data_quality_warnings", ())),
                )

        source = self._sources.get(request.provider)
        if source is None:
            raise ValueError(f"no adapter registered for provider '{request.provider}'")

        existing_bars = ()
        existing_warnings: tuple[str, ...] = ()
        fetch_windows: tuple[tuple[datetime, datetime], ...] = ((requested_start, requested_end),)
        if existing is not None:
            existing_bars = _payload_to_bars(
                list(existing.get("bars", [])),
                symbol=request.symbol,
                timeframe=request.timeframe,
            )
            existing_warnings = tuple(existing.get("data_quality_warnings", ()))
            stored_start = _ensure_utc(
                datetime.fromisoformat(str(existing["coverage_start"]).replace("Z", "+00:00"))
            )
            stored_end = _ensure_utc(
                datetime.fromisoformat(str(existing["coverage_end"]).replace("Z", "+00:00"))
            )
            gaps: list[tuple[datetime, datetime]] = []
            if requested_start < stored_start:
                gaps.append((requested_start, stored_start))
            if requested_end > stored_end:
                gaps.append((stored_end, requested_end))
            fetch_windows = tuple(gaps)

        fetched_bars: list[NormalizedBar] = []
        source_requests: list[dict[str, Any]] = []
        for fetch_start, fetch_end in fetch_windows:
            if fetch_start >= fetch_end:
                continue
            raw_bars, source_request_parameters = source.fetch(
                symbol=request.symbol,
                timeframe=request.timeframe,
                start=fetch_start,
                end=fetch_end,
                adjustment_policy=request.adjustment_policy,
            )
            fetched_bars.extend(raw_bars)
            source_requests.append(source_request_parameters)

        merged_bars = _dedupe_bars((*existing_bars, *tuple(fetched_bars)))
        warnings = tuple(dict.fromkeys((*existing_warnings, *self._detect_warnings(merged_bars))))
        dataset_id = UUID(str(existing["dataset_id"])) if existing is not None else uuid4()
        coverage_start = (
            min((_ensure_utc(b.timestamp) for b in merged_bars), default=requested_start)
        )
        coverage_end = (
            max((_ensure_utc(b.timestamp) for b in merged_bars), default=requested_end)
        )
        payload = {
            "dataset_id": str(dataset_id),
            "provider": request.provider,
            "symbol": request.symbol.upper(),
            "timeframe": request.timeframe,
            "adjustment_policy": request.adjustment_policy,
            "timezone": "UTC",
            "ingested_at": self._clock().isoformat()
            if callable(self._clock)
            else utc_now().isoformat(),
            "source_request_parameters": source_requests[0] if len(source_requests) == 1 else {"gap_requests": source_requests},
            "data_quality_warnings": list(warnings),
            "coverage_start": coverage_start.isoformat(),
            "coverage_end": coverage_end.isoformat(),
            "bar_count": len(merged_bars),
            "aggregate_quality_status": "warning" if warnings else "ok",
            "bars": _bars_to_payload(merged_bars),
        }
        self._store.save_historical_dataset(payload, dataset_id=str(dataset_id))
        window_bars = tuple(
            bar for bar in merged_bars
            if requested_start <= _ensure_utc(bar.timestamp) <= requested_end
        )
        return HistoricalBarIngestResult(
            dataset_id=dataset_id,
            bars=window_bars,
            fetched_from_provider=True,
            data_quality_warnings=tuple(warnings),
        )

    @staticmethod
    def _detect_warnings(bars: tuple[NormalizedBar, ...]) -> tuple[str, ...]:
        warnings: list[str] = []
        if not bars:
            warnings.append("provider_returned_zero_bars")
            return tuple(warnings)
        for bar in bars:
            if bar.high < bar.low:
                warnings.append(f"invalid_bar_high_lt_low_at_{bar.timestamp.isoformat()}")
            if bar.volume is not None and bar.volume < 0:
                warnings.append(f"negative_volume_at_{bar.timestamp.isoformat()}")
        return tuple(warnings)


class AlpacaBarsSource:
    """Bars adapter for Alpaca historical aggregate API."""

    name = "alpaca"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def fetch(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjustment_policy: AdjustmentPolicy,
    ) -> tuple[tuple[NormalizedBar, ...], dict[str, Any]]:
        if self._client is None:
            raise RuntimeError(
                "AlpacaBarsSource requires an injected client; configure via runtime context"
            )
        adjustment = {
            "split_dividend_adjusted": "all",
            "split_only": "split",
            "raw": "raw",
        }.get(adjustment_policy, "all")
        timeframe_alpaca = _to_alpaca_timeframe(timeframe)
        raw_response = _fetch_alpaca_bars(
            self._client,
            symbol=symbol.upper(),
            timeframe=timeframe,
            start=start,
            end=end,
            adjustment=adjustment,
        )
        bars = tuple(
            _normalize_bar(raw=row, symbol=symbol, timeframe=timeframe)
            for row in _alpaca_response_rows(raw_response, symbol=symbol.upper())
        )
        params = {
            "endpoint": f"v2/stocks/{symbol.upper()}/bars",
            "timeframe": timeframe_alpaca,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "adjustment": adjustment,
        }
        return bars, params


def alpaca_bars_source_from_runtime(store: Any) -> AlpacaBarsSource:
    """Build an Alpaca historical bars source from the operator's saved Account.

    Broker credentials remain per-Account. This helper only reads a validated
    Alpaca Account's encrypted credentials to construct the historical market
    data client; it does not submit orders or touch broker truth.
    """

    client = _alpaca_historical_client_from_runtime(store)
    return AlpacaBarsSource(client=client)


class YahooBarsSource:
    """Bars adapter for Yahoo Finance via yfinance."""

    name = "yahoo"

    def __init__(self, downloader: Any | None = None) -> None:
        self._downloader = downloader

    def fetch(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        adjustment_policy: AdjustmentPolicy,
    ) -> tuple[tuple[NormalizedBar, ...], dict[str, Any]]:
        if self._downloader is None:
            try:
                import yfinance as yf  # type: ignore

                self._downloader = yf.download
            except ImportError as exc:
                raise RuntimeError(
                    "YahooBarsSource requires the optional yfinance package"
                ) from exc

        interval = _to_yahoo_interval(timeframe)
        auto_adjust = adjustment_policy == "split_dividend_adjusted"
        df = self._downloader(
            tickers=symbol.upper(),
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            interval=interval,
            auto_adjust=auto_adjust,
            progress=False,
        )
        bars: list[NormalizedBar] = []
        if df is not None and not df.empty:
            # yfinance >= 0.2 returns a MultiIndex on `columns` even for a
            # single ticker (e.g. `('Open', 'SPY')`), so `row["Open"]` resolves
            # to a Series rather than a scalar and `float(row["Open"])` raises
            # `TypeError: float() argument must be ... not 'Series'`. Flatten
            # to a single-level index so the scalar lookups below work across
            # yfinance versions.
            try:
                import pandas as pd  # type: ignore

                if isinstance(df.columns, pd.MultiIndex):
                    df = df.copy()
                    df.columns = df.columns.get_level_values(0)
            except ImportError:
                pass
            for index, row in df.iterrows():
                ts = index.to_pydatetime() if hasattr(index, "to_pydatetime") else index
                bars.append(
                    NormalizedBar(
                        symbol=symbol.upper(),
                        timeframe=timeframe,
                        timestamp=_ensure_utc(ts),
                        open=float(row["Open"]),
                        high=float(row["High"]),
                        low=float(row["Low"]),
                        close=float(row["Close"]),
                        volume=float(row.get("Volume", 0) or 0),
                    )
                )
        params = {
            "tickers": symbol.upper(),
            "start": start.strftime("%Y-%m-%d"),
            "end": end.strftime("%Y-%m-%d"),
            "interval": interval,
            "auto_adjust": auto_adjust,
        }
        return tuple(bars), params


def _to_alpaca_timeframe(timeframe: str) -> str:
    mapping = {"1m": "1Min", "5m": "5Min", "15m": "15Min", "1h": "1Hour", "1d": "1Day"}
    return mapping.get(timeframe, timeframe)


def _fetch_alpaca_bars(
    client: Any,
    *,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    adjustment: str,
) -> Any:
    if hasattr(client, "get_stock_bars"):
        request = _alpaca_stock_bars_request(
            symbol=symbol,
            timeframe=timeframe,
            start=start,
            end=end,
            adjustment=adjustment,
        )
        return client.get_stock_bars(request)
    return client.get_bars(
        symbol=symbol,
        timeframe=_to_alpaca_timeframe(timeframe),
        start=start.isoformat(),
        end=end.isoformat(),
        adjustment=adjustment,
    )


def _alpaca_stock_bars_request(
    *,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    adjustment: str,
) -> Any:
    try:
        from alpaca.data.enums import Adjustment
        from alpaca.data.requests import StockBarsRequest
    except ImportError as exc:  # pragma: no cover - optional SDK boundary.
        raise RuntimeError("alpaca-py data SDK is required for Alpaca historical bars") from exc
    adjustment_enum = {
        "all": Adjustment.ALL,
        "split": Adjustment.SPLIT,
        "raw": Adjustment.RAW,
    }.get(adjustment, Adjustment.ALL)
    return StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=_to_alpaca_sdk_timeframe(timeframe),
        start=start,
        end=end,
        adjustment=adjustment_enum,
    )


def _to_alpaca_sdk_timeframe(timeframe: str) -> Any:
    try:
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    except ImportError as exc:  # pragma: no cover - optional SDK boundary.
        raise RuntimeError("alpaca-py data SDK is required for Alpaca historical bars") from exc
    mapping = {
        "1m": TimeFrame.Minute,
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "1h": TimeFrame.Hour,
        "1d": TimeFrame.Day,
    }
    return mapping.get(timeframe, TimeFrame.Day)


def _alpaca_response_rows(response: Any, *, symbol: str) -> tuple[dict[str, Any], ...]:
    if isinstance(response, dict):
        bars = response.get("bars")
        if isinstance(bars, list):
            return tuple(dict(row) for row in bars)
        symbol_rows = response.get(symbol)
        if isinstance(symbol_rows, list):
            return tuple(_alpaca_bar_to_row(row) for row in symbol_rows)
        data = response.get("data")
        if isinstance(data, dict):
            return tuple(_alpaca_bar_to_row(row) for row in data.get(symbol, ()))
    data = getattr(response, "data", None)
    if isinstance(data, dict):
        return tuple(_alpaca_bar_to_row(row) for row in data.get(symbol, ()))
    if isinstance(response, (list, tuple)):
        return tuple(_alpaca_bar_to_row(row) for row in response)
    return ()


def _alpaca_bar_to_row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "model_dump"):
        payload = row.model_dump()
    elif hasattr(row, "dict"):
        payload = row.dict()
    else:
        payload = {
            key: getattr(row, key)
            for key in ("timestamp", "open", "high", "low", "close", "volume")
            if hasattr(row, key)
        }
    return {
        "timestamp": _first_present(payload, "timestamp", "t"),
        "open": _first_present(payload, "open", "o"),
        "high": _first_present(payload, "high", "h"),
        "low": _first_present(payload, "low", "l"),
        "close": _first_present(payload, "close", "c"),
        "volume": _first_present(payload, "volume", "v", default=0),
    }


def _first_present(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def _alpaca_historical_client_from_runtime(store: Any) -> Any | None:
    credential_store = _broker_credential_store()
    for account in store.list_broker_accounts():
        if account.provider != "alpaca":
            continue
        if account.is_archived or account.needs_credentials:
            continue
        if account.validation_status != BrokerAccountValidationStatus.VALID:
            continue
        try:
            api_key, api_secret = credential_store.get(account.id)
        except Exception:
            continue
        return _build_alpaca_historical_client(api_key=api_key, api_secret=api_secret)
    return None


def _broker_credential_store() -> Any:
    from backend.app.broker_accounts.credential_store import create_broker_credential_store_from_environment

    return create_broker_credential_store_from_environment()


def _build_alpaca_historical_client(*, api_key: str, api_secret: str) -> Any:
    try:
        from alpaca.data.historical import StockHistoricalDataClient
    except ImportError as exc:  # pragma: no cover - optional SDK boundary.
        raise RuntimeError("alpaca-py data SDK is required for Alpaca historical bars") from exc
    return StockHistoricalDataClient(api_key, api_secret)


def _to_yahoo_interval(timeframe: str) -> str:
    mapping = {"1m": "1m", "5m": "5m", "15m": "15m", "1h": "60m", "1d": "1d"}
    return mapping.get(timeframe, timeframe)

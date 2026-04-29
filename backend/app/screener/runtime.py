"""Composition roots for the Screener service."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from uuid import UUID

from backend.app.config.runtime_paths import get_runtime_db_path
from backend.app.data_center.historical_catalog import configure_persistence
from backend.app.features import NormalizedBar
from backend.app.persistence import SQLiteRuntimeStore

from .service import ScreenerExecutionService
from .sources import (
    AlpacaAssetCapabilityLookup,
    AlpacaMarketListLookup,
    HistoricalBarsLookup,
    MarketListLookup,
    MetricSource,
    UniverseResolver,
    WatchlistLookup,
)
from .store import ScreenerStore


def _runtime_db_path() -> Path:
    return get_runtime_db_path()


def _runtime_store() -> SQLiteRuntimeStore:
    store = SQLiteRuntimeStore(_runtime_db_path())
    configure_persistence(store)
    return store


def create_screener_service_from_environment() -> ScreenerExecutionService:
    """Build the Screener service against the real runtime stores.

    Screener production runs are Alpaca-first. They pull bars through the
    Data Center cache and do not use Yahoo scraping as a hidden fallback.
    """

    store = ScreenerStore(db_path=_runtime_db_path())
    universe = UniverseResolver(
        watchlists=_RuntimeWatchlistLookup(),
        market_lists=_runtime_market_list_lookup(),
    )
    metrics = MetricSource(
        bars=_RuntimeHistoricalBarsLookup(),
        asset_capabilities=_runtime_asset_lookup(),
    )
    return ScreenerExecutionService(
        store=store,
        universe_resolver=universe,
        metric_source=metrics,
    )


class _RuntimeWatchlistLookup:
    """Implements the screener's WatchlistLookup against WatchlistService."""

    def get_watchlist_symbols(self, watchlist_id: UUID) -> tuple[str, ...]:
        from backend.app.watchlists.runtime_service import (
            create_watchlist_service_from_environment,
        )

        service = create_watchlist_service_from_environment()
        response = service.get_watchlist(watchlist_id)
        latest = service.latest_snapshot(watchlist_id)
        symbols = latest.symbols if latest is not None else response.watchlist.static_symbols
        return tuple(s.upper() for s in symbols if s)


class _RuntimeHistoricalBarsLookup:
    """Implements HistoricalBarsLookup via the Data Center cache."""

    def get_bars(
        self,
        *,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> tuple[NormalizedBar, ...]:
        from backend.app.api.routes.data_center import (
            alpaca_bars_source_from_runtime,
        )
        from backend.app.data_center.ingest_service import (
            HistoricalBarIngestRequest,
            HistoricalBarIngestService,
        )

        store = _runtime_store()
        sources: dict[str, object] = {"alpaca": alpaca_bars_source_from_runtime(store)}
        ingest = HistoricalBarIngestService(store=store, sources=sources)  # type: ignore[arg-type]
        result = ingest.ensure_bars(
            HistoricalBarIngestRequest(
                provider="alpaca",
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
            )
        )
        return tuple(result.bars)


def _runtime_market_list_lookup() -> MarketListLookup | None:
    try:
        client = _alpaca_screener_client_from_runtime()
    except Exception:
        return None
    return AlpacaMarketListLookup(client)


def _runtime_asset_lookup() -> AlpacaAssetCapabilityLookup | None:
    try:
        client = _alpaca_trading_client_from_runtime()
    except Exception:
        return None
    return AlpacaAssetCapabilityLookup(client)


def _alpaca_screener_client_from_runtime() -> object:
    api_key, api_secret, _paper = _validated_alpaca_credentials()
    try:
        from alpaca.data.historical.screener import ScreenerClient
    except ImportError as exc:  # pragma: no cover - optional SDK boundary.
        raise RuntimeError("alpaca-py screener client is required for Alpaca market lists") from exc
    return ScreenerClient(api_key=api_key, secret_key=api_secret)


def _alpaca_trading_client_from_runtime() -> object:
    api_key, api_secret, paper = _validated_alpaca_credentials()
    try:
        from alpaca.trading.client import TradingClient
    except ImportError as exc:  # pragma: no cover - optional SDK boundary.
        raise RuntimeError("alpaca-py trading client is required for Alpaca assets") from exc
    return TradingClient(api_key, api_secret, paper=paper)


def _validated_alpaca_credentials() -> tuple[str, str, bool]:
    from backend.app.broker_accounts.credential_store import (
        create_broker_credential_store_from_environment,
    )
    from backend.app.broker_accounts.models import BrokerAccountValidationStatus
    from backend.app.domain import TradingMode

    store = _runtime_store()
    credential_store = create_broker_credential_store_from_environment()
    for account in store.list_broker_accounts():
        if account.provider != "alpaca":
            continue
        if account.is_archived or account.needs_credentials:
            continue
        if account.validation_status != BrokerAccountValidationStatus.VALID:
            continue
        api_key, api_secret = credential_store.get(account.id)
        return api_key, api_secret, account.mode == TradingMode.BROKER_PAPER
    raise RuntimeError("no validated Alpaca account credentials available")

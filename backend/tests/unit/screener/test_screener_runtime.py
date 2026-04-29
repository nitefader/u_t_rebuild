from __future__ import annotations

from uuid import uuid4

from backend.app.broker_accounts.models import BrokerAccountValidationStatus
from backend.app.domain import TradingMode
from backend.app.screener import runtime
from backend.app.screener.domain import ScreenerUniverseSource, ScreenerUniverseSourceKind
from backend.app.screener.sources import MarketListResult, UniverseResolver


class _Account:
    id = uuid4()
    provider = "alpaca"
    mode = TradingMode.BROKER_PAPER
    is_archived = False
    needs_credentials = False
    validation_status = BrokerAccountValidationStatus.VALID


class _Store:
    def list_broker_accounts(self):
        return (_Account(),)


class _CredentialStore:
    def get(self, account_id):
        return ("api-key", "api-secret")


def test_validated_alpaca_credentials_use_runtime_store(monkeypatch) -> None:
    """Regression: Screener runtime must not import a stale DataCenterStore symbol."""

    monkeypatch.setattr(runtime, "_runtime_store", lambda: _Store())
    monkeypatch.setattr(
        "backend.app.broker_accounts.credential_store.create_broker_credential_store_from_environment",
        lambda: _CredentialStore(),
    )

    assert runtime._validated_alpaca_credentials() == ("api-key", "api-secret", True)


class _MarketLists:
    limit: int | None = None

    def get_market_list_symbols(self, key: str, *, limit: int) -> MarketListResult:
        self.limit = limit
        return MarketListResult(
            key=key,
            label="Day Gainers",
            symbols=("AAPL",),
            source="alpaca_screener",
            freshness={"provider": "Alpaca"},
            evidence={"provider": "alpaca"},
        )


def test_market_list_universe_stays_inside_alpaca_top_limit() -> None:
    lookup = _MarketLists()
    resolver = UniverseResolver(market_lists=lookup)

    result = resolver.resolve(
        ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.MARKET_LIST,
            market_list_key="day_gainers",
        )
    )

    assert lookup.limit == 50
    assert result.symbols == ("AAPL",)

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from backend.app.deployments import (
    DeploymentLifecycleStatus,
    DeploymentService,
    DeploymentWriteRequest,
)
from backend.app.deployments.persistence import DeploymentRepository
from backend.app.domain import (
    StrategyVersion,
)
from backend.app.features import NormalizedBar
from backend.app.screener.domain import (
    ScreenerCriterion,
    ScreenerCriterionOperator,
    ScreenerExpression,
    ScreenerExpressionKind,
    ScreenerMetric,
    ScreenerUniverseSource,
    ScreenerUniverseSourceKind,
    ScreenerVersion,
)
from backend.app.screener.fields import api_field_definitions
from backend.app.screener.service import ScreenerExecutionService, ScreenerValidationError
from backend.app.screener.sources import (
    AlpacaAssetCapabilityLookup,
    AlpacaMarketListLookup,
    AssetCapabilitySnapshot,
    HistoricalBarsLookup,
    MetricSource,
    UniverseResolver,
)
from backend.app.screener.store import ScreenerStore
from backend.app.screener.templates import version_from_template
from backend.app.watchlists import WatchlistKind, WatchlistService, WatchlistWriteRequest
from backend.app.watchlists.models import Watchlist, WatchlistDynamicRules
from backend.app.watchlists.persistence import WatchlistRepository


def _bars(symbol: str, *, last_volume: float = 3_000_000) -> tuple[NormalizedBar, ...]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        NormalizedBar(
            symbol=symbol,
            timeframe="1d",
            timestamp=base + timedelta(days=index),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=last_volume if index == 39 else 1_000_000,
        )
        for index in range(40)
    )


class _Bars(HistoricalBarsLookup):
    def get_bars(self, *, symbol, timeframe, start, end):  # noqa: D401, ARG002
        return _bars(symbol, last_volume=3_000_000 if symbol == "AAPL" else 500_000)


class _FailingBars(HistoricalBarsLookup):
    def get_bars(self, *, symbol, timeframe, start, end):  # noqa: D401, ARG002
        raise RuntimeError("Data Center bars unavailable")


class _AssetClient:
    def get_asset(self, symbol: str):
        return {
            "symbol": symbol,
            "name": f"{symbol} Corp",
            "status": "active",
            "tradable": True,
            "fractionable": symbol == "AAPL",
            "shortable": symbol != "TSLA",
            "easy_to_borrow": symbol == "AAPL",
            "exchange": "NASDAQ",
            "asset_class": "us_equity",
        }


class _FailingAssetClient:
    def get_asset(self, symbol: str):  # noqa: D401, ARG002
        raise RuntimeError("Alpaca asset API unavailable")


class _MarketListClient:
    def get_market_movers(self, request):  # noqa: D401, ARG002
        return {"gainers": [{"symbol": "AAPL"}, {"symbol": "TSLA"}], "losers": [{"symbol": "MSFT"}]}

    def get_most_actives(self, request):  # noqa: D401, ARG002
        return {"most_actives": [{"symbol": "AAPL"}, {"symbol": "MSFT"}]}


class _MutableAssetCapabilities:
    def __init__(self) -> None:
        self.fractionable_symbols = {"AAPL"}

    def get_asset_capabilities(self, symbol: str) -> AssetCapabilitySnapshot:
        return AssetCapabilitySnapshot(
            symbol=symbol,
            name=f"{symbol} Corp",
            status="active",
            tradable=True,
            fractionable=symbol in self.fractionable_symbols,
            shortable=symbol != "TSLA",
            easy_to_borrow=symbol == "AAPL",
            exchange="NASDAQ",
            asset_class="us_equity",
        )


@dataclass(frozen=True)
class _DynamicResolution:
    symbols: tuple[str, ...]
    note: str | None
    source_run_id: UUID | None
    source_label: str | None
    evidence: dict[str, object]


class _ScreenerBackedResolver:
    def __init__(self, service: ScreenerExecutionService) -> None:
        self._service = service

    def refresh(self, watchlist: Watchlist) -> _DynamicResolution:
        rules = watchlist.dynamic_rules
        if rules is None or rules.screener_id is None or rules.screener_version_id is None:
            raise RuntimeError("dynamic watchlist requires a concrete ScreenerVersion")
        run = self._service.run_screener(
            rules.screener_id,
            version_id=rules.screener_version_id,
            run_kind="refresh",
        )
        return _DynamicResolution(
            symbols=tuple(row.symbol for row in run.results if row.matched),
            note=f"Refreshed from Screener run {run.id}",
            source_run_id=run.id,
            source_label=f"Screener refresh: {watchlist.name}",
            evidence={
                "source_type": "screener_version",
                "screener_id": str(rules.screener_id),
                "screener_version_id": str(rules.screener_version_id),
                "matched_count": run.matched_count,
                "sources_used": run.sources_used,
            },
        )


class _DeploymentRefs:
    def __init__(self, repo: DeploymentRepository) -> None:
        self._repo = repo

    def active_deployment_names_for_watchlist(self, watchlist_id: UUID) -> tuple[str, ...]:
        names: list[str] = []
        for deployment in self._repo.list_deployments():
            if watchlist_id not in deployment.watchlist_ids:
                continue
            if deployment.lifecycle_status in {
                DeploymentLifecycleStatus.ACTIVE,
                DeploymentLifecycleStatus.PAUSED,
            }:
                names.append(deployment.name)
        return tuple(names)


def _service(tmp_path: Path) -> ScreenerExecutionService:
    return ScreenerExecutionService(
        store=ScreenerStore(db_path=tmp_path / "screener.db"),
        universe_resolver=UniverseResolver(market_lists=AlpacaMarketListLookup(_MarketListClient())),
        metric_source=MetricSource(
            bars=_Bars(),
            asset_capabilities=AlpacaAssetCapabilityLookup(_AssetClient()),
        ),
    )


def test_field_registry_includes_alpaca_capability_fields() -> None:
    keys = {field["key"] for field in api_field_definitions()}
    assert {
        "broker.tradable",
        "broker.fractionable",
        "broker.shortable",
        "broker.easy_to_borrow",
        "broker.active",
        "broker.exchange",
        "broker.asset_class",
    } <= keys


def test_alpaca_market_list_lookup_normalizes_movers_and_most_active() -> None:
    lookup = AlpacaMarketListLookup(_MarketListClient())
    assert lookup.get_market_list_symbols("day_gainers", limit=10).symbols == ("AAPL", "TSLA")
    assert lookup.get_market_list_symbols("most_active", limit=10).symbols == ("AAPL", "MSFT")


def test_alpaca_capability_evidence_survives_bar_metric_failure(tmp_path: Path) -> None:
    service = ScreenerExecutionService(
        store=ScreenerStore(db_path=tmp_path / "screener.db"),
        universe_resolver=UniverseResolver(),
        metric_source=MetricSource(
            bars=_FailingBars(),
            asset_capabilities=AlpacaAssetCapabilityLookup(_AssetClient()),
        ),
    )
    version = ScreenerVersion(
        screener_id=uuid4(),
        name="Tradable AAPL",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT,
            symbols=("AAPL",),
        ),
        criteria=(
            ScreenerCriterion(
                metric=ScreenerMetric.BROKER_TRADABLE,
                operator=ScreenerCriterionOperator.EQ,
                value=True,
                label="Tradable at Alpaca",
            ),
        ),
    )
    screener, _ = service.create_screener(name="Tradable AAPL", description=None, version=version)

    run = service.run_screener(screener.id)
    row = run.results[0]

    assert row.symbol == "AAPL"
    assert row.metrics["broker.tradable"] is True
    assert row.matched is True
    assert not any("not tradable" in reason for reason in row.blocked_reasons)
    assert "bar metrics unavailable: Data Center bars unavailable" == row.evidence["error"]
    assert row.evidence["asset_capability"]["unavailable_reason"] is None  # type: ignore[index]


def test_unavailable_alpaca_capability_evidence_is_not_reported_as_false(tmp_path: Path) -> None:
    service = ScreenerExecutionService(
        store=ScreenerStore(db_path=tmp_path / "screener.db"),
        universe_resolver=UniverseResolver(),
        metric_source=MetricSource(
            bars=_Bars(),
            asset_capabilities=AlpacaAssetCapabilityLookup(_FailingAssetClient()),
        ),
    )
    version = ScreenerVersion(
        screener_id=uuid4(),
        name="Tradable evidence",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.EXPLICIT,
            symbols=("AAPL",),
        ),
        criteria=(
            ScreenerCriterion(
                metric=ScreenerMetric.BROKER_TRADABLE,
                operator=ScreenerCriterionOperator.EQ,
                value=True,
                label="Tradable at Alpaca",
            ),
        ),
    )
    screener, _ = service.create_screener(name="Tradable evidence", description=None, version=version)

    run = service.run_screener(screener.id)
    row = run.results[0]

    assert row.metrics["broker.tradable"] is None
    assert row.blocked_reasons == ("Alpaca tradability evidence unavailable",)
    assert not any("asset is not tradable at Alpaca" in reason for reason in row.blocked_reasons)
    assert row.evidence["asset_capability"]["unavailable_reason"] == "Alpaca asset API unavailable"  # type: ignore[index]


def test_expression_engine_supports_nested_any_and_broker_capability(tmp_path: Path) -> None:
    service = _service(tmp_path)
    expression = ScreenerExpression(
        kind=ScreenerExpressionKind.ALL,
        children=(
            ScreenerExpression(
                kind=ScreenerExpressionKind.ANY,
                children=(
                    ScreenerExpression(
                        kind=ScreenerExpressionKind.CRITERION,
                        criterion=ScreenerCriterion(
                            metric=ScreenerMetric.RELATIVE_VOLUME,
                            operator=ScreenerCriterionOperator.GTE,
                            value=2,
                            label="Relative volume at least 2x",
                        ),
                    ),
                    ScreenerExpression(
                        kind=ScreenerExpressionKind.CRITERION,
                        criterion=ScreenerCriterion(
                            metric=ScreenerMetric.CHANGE_PCT,
                            operator=ScreenerCriterionOperator.GTE,
                            value=1,
                        ),
                    ),
                ),
            ),
            ScreenerExpression(
                kind=ScreenerExpressionKind.CRITERION,
                criterion=ScreenerCriterion(
                    metric=ScreenerMetric.BROKER_FRACTIONABLE,
                    operator=ScreenerCriterionOperator.EQ,
                    value=True,
                    label="Fractionable at Alpaca",
                ),
            ),
        ),
    )
    version = ScreenerVersion(
        screener_id=uuid4(),
        name="Fractionable mover",
        universe_source=ScreenerUniverseSource(
            kind=ScreenerUniverseSourceKind.MARKET_LIST,
            market_list_key="day_gainers",
        ),
        expression=expression,
        sort_metric=ScreenerMetric.RELATIVE_VOLUME,
    )
    screener, _ = service.create_screener(name="Fractionable mover", description=None, version=version)

    run = service.run_screener(screener.id)

    assert [row.symbol for row in run.results if row.matched] == ["AAPL"]
    tsla = next(row for row in run.results if row.symbol == "TSLA")
    assert "asset is not fractionable at Alpaca" in tsla.blocked_reasons
    assert run.sources_used[0].startswith("Market list: Day Gainers")
    assert run.source_evidence["provider"] == "alpaca"


def test_unsupported_operator_for_boolean_field_fails_before_run(tmp_path: Path) -> None:
    service = _service(tmp_path)
    version = ScreenerVersion(
        screener_id=uuid4(),
        name="Bad capability",
        universe_source=ScreenerUniverseSource(kind=ScreenerUniverseSourceKind.EXPLICIT, symbols=("AAPL",)),
        criteria=(
            ScreenerCriterion(
                metric=ScreenerMetric.BROKER_FRACTIONABLE,
                operator=ScreenerCriterionOperator.GTE,
                value=True,
            ),
        ),
    )

    with pytest.raises(ScreenerValidationError):
        service.create_screener(name="Bad capability", description=None, version=version)


def test_rerun_diff_archive_and_safe_delete(tmp_path: Path) -> None:
    service = _service(tmp_path)
    version = ScreenerVersion(
        screener_id=uuid4(),
        name="RVOL",
        universe_source=ScreenerUniverseSource(kind=ScreenerUniverseSourceKind.EXPLICIT, symbols=("AAPL", "MSFT")),
        criteria=(
            ScreenerCriterion(
                metric=ScreenerMetric.RELATIVE_VOLUME,
                operator=ScreenerCriterionOperator.GTE,
                value=2,
            ),
        ),
    )
    screener, _ = service.create_screener(name="RVOL", description=None, version=version)
    first = service.run_screener(screener.id)
    second = service.rerun(first.id)
    diff = service.diff_runs(second.id, against_run_id=first.id)

    assert second.id != first.id
    assert second.parent_run_id == first.id
    assert diff["stayed"] == ("AAPL",)
    archived = service.archive_screener(screener.id)
    assert archived.status == "archived"
    with pytest.raises(ScreenerValidationError):
        service.delete_screener(screener.id)


def test_step10_backend_flow_keeps_screener_watchlist_deployment_and_exit_boundaries(
    tmp_path: Path,
) -> None:
    assets = _MutableAssetCapabilities()
    screener_service = ScreenerExecutionService(
        store=ScreenerStore(db_path=tmp_path / "screener.db"),
        universe_resolver=UniverseResolver(market_lists=AlpacaMarketListLookup(_MarketListClient())),
        metric_source=MetricSource(bars=_Bars(), asset_capabilities=assets),
    )
    deployment_repo = DeploymentRepository(tmp_path / "runtime.db")
    watchlists = WatchlistService(
        repository=WatchlistRepository(tmp_path / "runtime.db"),
        dynamic_resolver=_ScreenerBackedResolver(screener_service),
        reference_lookup=_DeploymentRefs(deployment_repo),
    )

    template_version = version_from_template("day_gainers", screener_id=uuid4())
    screener, template_version = screener_service.create_screener(
        name="Day Gainers",
        description=template_version.description,
        version=template_version,
        tags=template_version.tags,
    )
    market_list_run = screener_service.run_screener(screener.id, version_id=template_version.id)
    assert [row.symbol for row in market_list_run.results if row.matched] == ["AAPL", "TSLA"]
    assert market_list_run.source_evidence["provider"] == "alpaca"

    assert template_version.expression is not None
    edited_expression = ScreenerExpression(
        kind=ScreenerExpressionKind.ALL,
        children=(
            *template_version.expression.children,
            ScreenerExpression(
                kind=ScreenerExpressionKind.CRITERION,
                criterion=ScreenerCriterion(
                    metric=ScreenerMetric.BROKER_FRACTIONABLE,
                    operator=ScreenerCriterionOperator.EQ,
                    value=True,
                    label="Fractionable at Alpaca",
                ),
            ),
        ),
    )
    edited_version = screener_service.add_version(
        screener.id,
        name="Day Gainers - Fractionable",
        version_payload=template_version.model_copy(
            update={
                "name": "Day Gainers - Fractionable",
                "expression": edited_expression,
            }
        ),
    )
    filtered_run = screener_service.run_screener(screener.id, version_id=edited_version.id)
    assert [row.symbol for row in filtered_run.results if row.matched] == ["AAPL"]
    assert next(row for row in filtered_run.results if row.symbol == "TSLA").blocked_reasons == (
        "asset is not fractionable at Alpaca",
    )

    static_watchlist = watchlists.create_watchlist(
        WatchlistWriteRequest(
            name="Day Gainers Fractionable Static",
            kind=WatchlistKind.STATIC,
            static_symbols=tuple(row.symbol for row in filtered_run.results if row.matched),
        )
    )
    static_snapshot = watchlists.take_snapshot(static_watchlist.watchlist_id)
    assert static_snapshot.symbols == ("AAPL",)
    assert static_snapshot.source_label == "Static Watchlist"

    dynamic_watchlist = watchlists.create_watchlist(
        WatchlistWriteRequest(
            name="Day Gainers Fractionable Dynamic",
            kind=WatchlistKind.DYNAMIC,
            dynamic_rules=WatchlistDynamicRules(
                source_type="screener_version",
                screener_id=screener.id,
                screener_version_id=edited_version.id,
                refresh_policy="manual",
                approval_policy="operator_review",
            ),
        )
    )
    first_dynamic_snapshot = watchlists.take_snapshot(dynamic_watchlist.watchlist_id)
    assert first_dynamic_snapshot.symbols == ("AAPL",)
    assert first_dynamic_snapshot.source_run_id is not None
    assert first_dynamic_snapshot.evidence["source_type"] == "screener_version"

    assets.fractionable_symbols.add("TSLA")
    rerun = screener_service.rerun(filtered_run.id)
    diff = screener_service.diff_runs(rerun.id, against_run_id=filtered_run.id)
    assert diff["added"] == ("TSLA",)
    assert diff["stayed"] == ("AAPL",)

    refreshed_dynamic_snapshot = watchlists.take_snapshot(dynamic_watchlist.watchlist_id)
    assert refreshed_dynamic_snapshot.symbols == ("AAPL", "TSLA")
    assert refreshed_dynamic_snapshot.added_symbols == ("TSLA",)
    assert refreshed_dynamic_snapshot.stayed_symbols == ("AAPL",)

    deployment_service = DeploymentService(repository=deployment_repo)
    strategy_version_v4_id = uuid4()
    deployment = deployment_service.create_deployment(
        DeploymentWriteRequest(
            name="Day Gainers Fractionable Deployment",
            strategy_version_v4_id=strategy_version_v4_id,
            watchlist_ids=(dynamic_watchlist.watchlist_id,),
            subscribed_account_ids=(uuid4(),),
        )
    )
    started = deployment_service.start(deployment.deployment_id, reason="operator approved entry universe")
    assert started.lifecycle_status == DeploymentLifecycleStatus.ACTIVE
    assert started.strategy_version_v4_id == strategy_version_v4_id
    assert started.watchlist_ids == (dynamic_watchlist.watchlist_id,)
    assert "symbols" not in StrategyVersion.model_fields

    with pytest.raises(RuntimeError, match="active deployments reference"):
        watchlists.archive_watchlist(dynamic_watchlist.watchlist_id)

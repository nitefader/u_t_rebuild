"""End-to-end: catalog + pipeline registry + resolver produce real pipeline_id.

Phase 1 §11.5 exit-gate evidence: a Deployment can declare feature demand,
resolve a pipeline, and attach data demand without direct provider calls.
"""

from __future__ import annotations

from backend.app.market_data import (
    DataConsumer,
    DataIntent,
    DataIntentMode,
    DataPurpose,
    MarketDataPipelineRegistry,
    MarketDataPipelineWrite,
    MarketDataServiceCatalog,
    MarketDataServiceWrite,
    Provider,
    ResolveMarketDataRequest,
    ResolverDecision,
    SelectionStrategy,
    Timeframe,
)


def _approve_via_validator():
    """Build a fake validator that always passes (mimics a successful validate)."""
    from backend.app.market_data.validation import (
        MarketDataProviderValidator,
        MarketDataValidationResult,
    )
    from backend.app.market_data import (
        MarketDataValidationStatus,
        alpaca_capabilities,
        yahoo_capabilities,
    )

    class AlwaysValid(MarketDataProviderValidator):
        def validate(self, *, provider, has_api_key, has_api_secret, api_key=None, api_secret=None):
            caps = yahoo_capabilities() if provider == Provider.YAHOO else alpaca_capabilities()
            return MarketDataValidationResult(MarketDataValidationStatus.VALID, "ok", caps)

    return AlwaysValid()


def test_catalog_plus_registry_resolver_e2e_returns_real_pipeline_id(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(
        store_path=tmp_path / "catalog.json",
        validator=_approve_via_validator(),
    )
    registry = MarketDataPipelineRegistry(store_path=tmp_path / "pipelines.json")

    yahoo_service = catalog.create_service(MarketDataServiceWrite(name="Yahoo Historical", provider=Provider.YAHOO))
    catalog.validate_service(yahoo_service.id)

    yahoo_pipeline = registry.create_pipeline(
        MarketDataPipelineWrite(display_name="Yahoo Historical Pipeline", provider=Provider.YAHOO)
    )
    registry.set_default_for_provider(yahoo_pipeline.id)

    intent = DataIntent(
        consumer=DataConsumer.BACKTEST,
        mode=DataIntentMode.REPLAY,
        symbols=["SPY", "AAPL", "MSFT"],
        timeframe=Timeframe.D1,
        purpose=DataPurpose.BACKTEST,
    )
    result = catalog.resolve(
        ResolveMarketDataRequest(intent=intent, selection_strategy=SelectionStrategy.AUTO),
        pipeline_registry=registry,
    )

    assert result.decision == ResolverDecision.SELECTED
    assert len(result.per_symbol_rows) == 3
    expected_pipeline_id = str(yahoo_pipeline.id)
    for row in result.per_symbol_rows:
        assert row.selected_provider == Provider.YAHOO
        assert row.pipeline_id == expected_pipeline_id


def test_catalog_resolve_without_registry_leaves_pipeline_id_null(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(
        store_path=tmp_path / "catalog.json",
        validator=_approve_via_validator(),
    )
    yahoo_service = catalog.create_service(MarketDataServiceWrite(name="Yahoo", provider=Provider.YAHOO))
    catalog.validate_service(yahoo_service.id)

    intent = DataIntent(
        consumer=DataConsumer.BACKTEST,
        mode=DataIntentMode.REPLAY,
        symbols=["SPY"],
        timeframe=Timeframe.D1,
        purpose=DataPurpose.BACKTEST,
    )
    result = catalog.resolve(
        ResolveMarketDataRequest(intent=intent, selection_strategy=SelectionStrategy.AUTO)
    )

    assert result.decision == ResolverDecision.SELECTED
    assert result.per_symbol_rows[0].pipeline_id is None


def test_resolver_falls_back_to_null_when_registry_has_no_default_for_provider(tmp_path) -> None:
    catalog = MarketDataServiceCatalog(
        store_path=tmp_path / "catalog.json",
        validator=_approve_via_validator(),
    )
    registry = MarketDataPipelineRegistry(store_path=tmp_path / "pipelines.json")

    catalog.validate_service(
        catalog.create_service(MarketDataServiceWrite(name="Yahoo", provider=Provider.YAHOO)).id
    )
    # Pipeline created but never set as default
    registry.create_pipeline(MarketDataPipelineWrite(display_name="Yahoo", provider=Provider.YAHOO))

    intent = DataIntent(
        consumer=DataConsumer.BACKTEST,
        mode=DataIntentMode.REPLAY,
        symbols=["SPY"],
        timeframe=Timeframe.D1,
        purpose=DataPurpose.BACKTEST,
    )
    result = catalog.resolve(
        ResolveMarketDataRequest(intent=intent, selection_strategy=SelectionStrategy.AUTO),
        pipeline_registry=registry,
    )

    assert result.decision == ResolverDecision.SELECTED
    assert result.per_symbol_rows[0].pipeline_id is None  # graceful degradation

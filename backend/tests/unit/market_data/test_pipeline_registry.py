from __future__ import annotations

import pytest

from backend.app.domain import TradingMode
from backend.app.market_data import (
    MarketDataPipeline,
    MarketDataPipelineRegistry,
    MarketDataPipelineWrite,
    PipelineRegistryError,
    PipelineStatus,
    Provider,
)


def _registry(tmp_path):
    return MarketDataPipelineRegistry(store_path=tmp_path / "pipelines.json")


def test_create_pipeline_uses_provider_capability_profile_when_no_capabilities_supplied(tmp_path) -> None:
    reg = _registry(tmp_path)
    pipeline = reg.create_pipeline(MarketDataPipelineWrite(display_name="Alpaca Premium", provider=Provider.ALPACA))
    assert pipeline.provider == Provider.ALPACA
    assert pipeline.status == PipelineStatus.ACTIVE
    assert pipeline.capabilities.supports_streaming is True
    assert pipeline.is_default_for_provider is False


def test_create_pipeline_accepts_explicit_capabilities(tmp_path) -> None:
    from backend.app.market_data import MarketDataCapabilities

    caps = MarketDataCapabilities(supports_historical=True, supports_daily=True)
    reg = _registry(tmp_path)
    pipeline = reg.create_pipeline(
        MarketDataPipelineWrite(display_name="Custom", provider=Provider.FUTURE, capabilities=caps)
    )
    assert pipeline.capabilities == caps


def test_set_default_for_provider_un_sets_other_pipelines_for_same_provider(tmp_path) -> None:
    reg = _registry(tmp_path)
    p1 = reg.create_pipeline(MarketDataPipelineWrite(display_name="Alpaca A", provider=Provider.ALPACA))
    p2 = reg.create_pipeline(MarketDataPipelineWrite(display_name="Alpaca B", provider=Provider.ALPACA))

    reg.set_default_for_provider(p1.id)
    assert reg.get_pipeline(p1.id).is_default_for_provider is True
    assert reg.get_pipeline(p2.id).is_default_for_provider is False

    reg.set_default_for_provider(p2.id)
    assert reg.get_pipeline(p1.id).is_default_for_provider is False
    assert reg.get_pipeline(p2.id).is_default_for_provider is True


def test_set_default_does_not_affect_other_providers(tmp_path) -> None:
    reg = _registry(tmp_path)
    alpaca = reg.create_pipeline(MarketDataPipelineWrite(display_name="Alpaca", provider=Provider.ALPACA))
    yahoo = reg.create_pipeline(MarketDataPipelineWrite(display_name="Yahoo", provider=Provider.YAHOO))

    reg.set_default_for_provider(alpaca.id)
    reg.set_default_for_provider(yahoo.id)

    assert reg.get_pipeline(alpaca.id).is_default_for_provider is True
    assert reg.get_pipeline(yahoo.id).is_default_for_provider is True


def test_disabled_pipeline_cannot_be_set_default(tmp_path) -> None:
    reg = _registry(tmp_path)
    pipeline = reg.create_pipeline(MarketDataPipelineWrite(display_name="X", provider=Provider.ALPACA))
    reg.disable_pipeline(pipeline.id)
    with pytest.raises(PipelineRegistryError, match="disabled pipeline"):
        reg.set_default_for_provider(pipeline.id)


def test_disable_clears_default_flag(tmp_path) -> None:
    reg = _registry(tmp_path)
    pipeline = reg.create_pipeline(MarketDataPipelineWrite(display_name="X", provider=Provider.ALPACA))
    reg.set_default_for_provider(pipeline.id)
    disabled = reg.disable_pipeline(pipeline.id)
    assert disabled.status == PipelineStatus.DISABLED
    assert disabled.is_default_for_provider is False


def test_lookup_default_for_provider_ignores_disabled(tmp_path) -> None:
    reg = _registry(tmp_path)
    pipeline = reg.create_pipeline(MarketDataPipelineWrite(display_name="X", provider=Provider.ALPACA))
    reg.set_default_for_provider(pipeline.id)
    assert reg.lookup_default_for_provider(Provider.ALPACA) == str(pipeline.id)
    reg.disable_pipeline(pipeline.id)
    assert reg.lookup_default_for_provider(Provider.ALPACA) is None


def test_lookup_returns_none_when_no_default_for_provider(tmp_path) -> None:
    reg = _registry(tmp_path)
    reg.create_pipeline(MarketDataPipelineWrite(display_name="X", provider=Provider.ALPACA))
    # No set_default called.
    assert reg.lookup_default_for_provider(Provider.ALPACA) is None
    assert reg.lookup_default_for_provider(Provider.YAHOO) is None


def test_persistence_round_trip(tmp_path) -> None:
    store = tmp_path / "pipelines.json"
    reg = MarketDataPipelineRegistry(store_path=store)
    pipeline = reg.create_pipeline(
        MarketDataPipelineWrite(
            display_name="Alpaca Premium",
            provider=Provider.ALPACA,
            trading_mode=TradingMode.BROKER_PAPER,
        )
    )
    reg.set_default_for_provider(pipeline.id)

    reloaded = MarketDataPipelineRegistry(store_path=store)
    assert reloaded.lookup_default_for_provider(Provider.ALPACA) == str(pipeline.id)
    survivor = reloaded.get_pipeline(pipeline.id)
    assert survivor.trading_mode == TradingMode.BROKER_PAPER
    assert survivor.is_default_for_provider is True


def test_pipeline_rejects_non_broker_trading_mode() -> None:
    with pytest.raises(ValueError, match="BROKER mode"):
        MarketDataPipeline(display_name="bad", provider=Provider.ALPACA, trading_mode=TradingMode.CHART_LAB_BATCH)


def test_pipeline_write_rejects_non_broker_trading_mode() -> None:
    with pytest.raises(ValueError, match="BROKER mode"):
        MarketDataPipelineWrite(display_name="bad", provider=Provider.ALPACA, trading_mode=TradingMode.SIM_LAB_HISTORICAL)


def test_pipeline_accepts_none_trading_mode_for_vendor_only() -> None:
    """Yahoo and other vendor-only pipelines have no broker credential tie."""
    pipeline = MarketDataPipeline(display_name="Yahoo", provider=Provider.YAHOO, trading_mode=None)
    assert pipeline.trading_mode is None


def test_unknown_pipeline_id_raises(tmp_path) -> None:
    reg = _registry(tmp_path)
    from uuid import uuid4

    with pytest.raises(PipelineRegistryError, match="unknown pipeline"):
        reg.get_pipeline(uuid4())


# ---------------------------------------------------------------------------
# Round 2: service_id FK + (service_id, trading_mode, data_feed) invariant
# ---------------------------------------------------------------------------


def test_pipeline_carries_service_id_and_data_feed_when_supplied(tmp_path) -> None:
    from uuid import uuid4

    reg = _registry(tmp_path)
    service_id = uuid4()
    pipeline = reg.create_pipeline(
        MarketDataPipelineWrite(
            display_name="Alpaca paper SIP",
            provider=Provider.ALPACA,
            service_id=service_id,
            data_feed="sip",
            trading_mode=TradingMode.BROKER_PAPER,
        )
    )
    assert pipeline.service_id == service_id
    assert pipeline.data_feed == "sip"


def test_pipeline_data_feed_defaults_to_iex(tmp_path) -> None:
    reg = _registry(tmp_path)
    pipeline = reg.create_pipeline(MarketDataPipelineWrite(display_name="Alpaca", provider=Provider.ALPACA))
    assert pipeline.data_feed == "iex"


def test_create_pipeline_rejects_duplicate_service_mode_feed_when_existing_active(tmp_path) -> None:
    from uuid import uuid4

    reg = _registry(tmp_path)
    service_id = uuid4()
    reg.create_pipeline(
        MarketDataPipelineWrite(
            display_name="Alpaca paper IEX",
            provider=Provider.ALPACA,
            service_id=service_id,
            data_feed="iex",
            trading_mode=TradingMode.BROKER_PAPER,
        )
    )
    with pytest.raises(PipelineRegistryError, match="duplicate active streams"):
        reg.create_pipeline(
            MarketDataPipelineWrite(
                display_name="Same identity duplicate",
                provider=Provider.ALPACA,
                service_id=service_id,
                data_feed="iex",
                trading_mode=TradingMode.BROKER_PAPER,
            )
        )


def test_create_pipeline_allows_different_data_feed_for_same_service(tmp_path) -> None:
    """Two pipelines on the same Alpaca account can run simultaneously on different feeds."""
    from uuid import uuid4

    reg = _registry(tmp_path)
    service_id = uuid4()
    iex = reg.create_pipeline(
        MarketDataPipelineWrite(
            display_name="IEX",
            provider=Provider.ALPACA,
            service_id=service_id,
            data_feed="iex",
            trading_mode=TradingMode.BROKER_PAPER,
        )
    )
    sip = reg.create_pipeline(
        MarketDataPipelineWrite(
            display_name="SIP",
            provider=Provider.ALPACA,
            service_id=service_id,
            data_feed="sip",
            trading_mode=TradingMode.BROKER_PAPER,
        )
    )
    assert iex.data_feed != sip.data_feed


def test_disabled_pipeline_does_not_block_re_creation_for_same_identity(tmp_path) -> None:
    from uuid import uuid4

    reg = _registry(tmp_path)
    service_id = uuid4()
    first = reg.create_pipeline(
        MarketDataPipelineWrite(
            display_name="A",
            provider=Provider.ALPACA,
            service_id=service_id,
            data_feed="iex",
            trading_mode=TradingMode.BROKER_PAPER,
        )
    )
    reg.disable_pipeline(first.id)
    # After disable, creating a new active pipeline for the same identity is allowed.
    second = reg.create_pipeline(
        MarketDataPipelineWrite(
            display_name="A2",
            provider=Provider.ALPACA,
            service_id=service_id,
            data_feed="iex",
            trading_mode=TradingMode.BROKER_PAPER,
        )
    )
    assert second.id != first.id


def test_pipeline_with_no_service_id_is_exempt_from_invariant(tmp_path) -> None:
    """Legacy / vendor-only pipelines (no service_id) don't dedup against each other."""
    reg = _registry(tmp_path)
    a = reg.create_pipeline(
        MarketDataPipelineWrite(display_name="Vendor A", provider=Provider.YAHOO, trading_mode=None)
    )
    b = reg.create_pipeline(
        MarketDataPipelineWrite(display_name="Vendor B", provider=Provider.YAHOO, trading_mode=None)
    )
    assert a.id != b.id


def test_attach_service_id_backfills_legacy_pipeline(tmp_path) -> None:
    from uuid import uuid4

    reg = _registry(tmp_path)
    legacy = reg.create_pipeline(
        MarketDataPipelineWrite(display_name="Legacy", provider=Provider.ALPACA, trading_mode=TradingMode.BROKER_PAPER)
    )
    assert legacy.service_id is None
    service_id = uuid4()
    updated = reg.attach_service_id(legacy.id, service_id)
    assert updated.service_id == service_id


def test_attach_service_id_enforces_invariant(tmp_path) -> None:
    """Backfilling can't create a duplicate active stream identity."""
    from uuid import uuid4

    reg = _registry(tmp_path)
    service_id = uuid4()
    reg.create_pipeline(
        MarketDataPipelineWrite(
            display_name="Existing",
            provider=Provider.ALPACA,
            service_id=service_id,
            data_feed="iex",
            trading_mode=TradingMode.BROKER_PAPER,
        )
    )
    legacy = reg.create_pipeline(
        MarketDataPipelineWrite(display_name="Legacy", provider=Provider.ALPACA, trading_mode=TradingMode.BROKER_PAPER)
    )
    with pytest.raises(PipelineRegistryError, match="duplicate active streams"):
        reg.attach_service_id(legacy.id, service_id)

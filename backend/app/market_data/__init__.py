"""Market data provider boundary — adapters, resolver, catalog, and contracts.

Per plan_review.md Section I (FINAL) and final_roadmap §9, this is the canonical
bucket for market-data services and the resolver. The deprecated ``app.services``
bucket has been removed; all market-data concerns live here.

Trading mode (``TradingMode``) is intentionally absent from this bucket —
mode is owned exclusively by ``BrokerAccount``.
"""

from .alpaca import (
    AlpacaMarketDataAdapter,
    AlpacaMarketDataError,
    MarketDataStreamRunner,
    MarketDataSubscription,
)
from .stream_hub import MarketDataStreamHub, MarketDataStreamHubError
from .capability_profiles import ProviderCapabilityProfile, provider_capability_profile
from .catalog import (
    MarketDataCatalogError,
    MarketDataCatalogSnapshot,
    MarketDataServiceCatalog,
    ResolveMarketDataRequest,
)
from .pipeline import (
    MarketDataPipeline,
    MarketDataPipelineList,
    MarketDataPipelineWrite,
    PipelineStatus,
)
from .pipeline_registry import (
    MarketDataPipelineRegistry,
    PipelineRegistryError,
    PipelineRegistrySnapshot,
)
from .data_intent import (
    DataConsumer,
    DataIntent,
    DataIntentMode,
    DataPurpose,
    DataTolerance,
    Timeframe,
)
from .models import (
    MASKED_SECRET,
    MarketDataServiceList,
    MarketDataServiceRecord,
    MarketDataServiceWrite,
    MarketDataValidationStatus,
)
from .resolver import (
    RESOLVER_VERSION,
    CostClass,
    InvocationContext,
    LatencyClass,
    MarketDataCapabilities,
    MarketDataServiceConfig,
    PerSymbolResolution,
    Provider,
    RejectedCandidate,
    ResolverDecision,
    ResolverRejectionCode,
    ResolverResult,
    ResolverSelectionCode,
    SelectionStrategy,
    ServiceStatus,
    ServiceType,
    alpaca_market_data_service,
    resolve_market_data_service,
    yahoo_market_data_service,
)
from .runtime import create_market_data_catalog_from_environment, create_pipeline_registry_from_environment
from .validation import (
    MarketDataProviderValidator,
    MarketDataValidationResult,
    alpaca_capabilities,
    yahoo_capabilities,
)

__all__ = [
    "AlpacaMarketDataAdapter",
    "AlpacaMarketDataError",
    "CostClass",
    "DataConsumer",
    "DataIntent",
    "DataIntentMode",
    "DataPurpose",
    "DataTolerance",
    "InvocationContext",
    "LatencyClass",
    "MASKED_SECRET",
    "MarketDataCapabilities",
    "MarketDataCatalogError",
    "MarketDataCatalogSnapshot",
    "MarketDataPipeline",
    "MarketDataPipelineList",
    "MarketDataPipelineRegistry",
    "MarketDataPipelineWrite",
    "MarketDataProviderValidator",
    "MarketDataServiceCatalog",
    "MarketDataServiceConfig",
    "MarketDataServiceList",
    "MarketDataServiceRecord",
    "MarketDataServiceWrite",
    "MarketDataStreamHub",
    "MarketDataStreamHubError",
    "MarketDataStreamRunner",
    "MarketDataSubscription",
    "MarketDataValidationResult",
    "MarketDataValidationStatus",
    "PerSymbolResolution",
    "PipelineRegistryError",
    "PipelineRegistrySnapshot",
    "PipelineStatus",
    "Provider",
    "ProviderCapabilityProfile",
    "RESOLVER_VERSION",
    "RejectedCandidate",
    "ResolveMarketDataRequest",
    "ResolverDecision",
    "ResolverRejectionCode",
    "ResolverResult",
    "ResolverSelectionCode",
    "SelectionStrategy",
    "ServiceStatus",
    "ServiceType",
    "Timeframe",
    "alpaca_capabilities",
    "alpaca_market_data_service",
    "create_market_data_catalog_from_environment",
    "create_pipeline_registry_from_environment",
    "provider_capability_profile",
    "resolve_market_data_service",
    "yahoo_capabilities",
    "yahoo_market_data_service",
]

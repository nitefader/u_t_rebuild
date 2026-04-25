"""AI provider boundary — catalog, validation, and provider records.

Per plan_review.md A3 / Section I, AI providers live under their own bucket
and never share API surface, providers, or capability tags with market data.
"""

from .catalog import (
    AIProviderCatalog,
    AIProviderCatalogError,
    AIProviderCatalogSnapshot,
)
from .providers import (
    MASKED_SECRET,
    AICapabilityLabel,
    AIProvider,
    AIProviderStatus,
    AIServiceList,
    AIServiceRecord,
    AIServiceType,
    AIServiceWrite,
    AIValidationStatus,
)
from .runtime import create_ai_provider_catalog_from_environment
from .validation import AIProviderValidator, AIValidationResult

__all__ = [
    "AICapabilityLabel",
    "AIProvider",
    "AIProviderCatalog",
    "AIProviderCatalogError",
    "AIProviderCatalogSnapshot",
    "AIProviderStatus",
    "AIProviderValidator",
    "AIServiceList",
    "AIServiceRecord",
    "AIServiceType",
    "AIServiceWrite",
    "AIValidationResult",
    "AIValidationStatus",
    "MASKED_SECRET",
    "create_ai_provider_catalog_from_environment",
]

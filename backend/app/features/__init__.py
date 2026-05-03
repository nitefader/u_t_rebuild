"""Canonical feature identity and registry contracts."""

from .bar_builder import (
    INPUT_TIMEFRAME,
    INTRADAY_SUPPORTED,
    SESSION_SUPPORTED,
    SUPPORTED_TIMEFRAMES,
    BarBuilder,
    BarBuilderError,
    BarBuilderRegistry,
)
from .calendar import (
    FixtureCalendar,
    MarketCalendar,
    NYSECalendar,
    SessionWindow,
    half_day_session,
    regular_session,
)
from .frames import FeatureAvailability, FeatureFrame, FeatureFrameSet, FeatureSnapshot, FeatureValue, NormalizedBar
from .hydration import (
    FeatureHydrationBarsRequest,
    FeatureHydrationBarsSource,
    FeatureHydrationBlocker,
    FeatureHydrationRequest,
    FeatureHydrationResult,
    FeatureHydrationService,
)
from .incremental import (
    FeatureCache,
    IncrementalFeatureEngine,
    IncrementalFeatureEngineError,
    IncrementalFeatureUpdate,
    UnsupportedBatchFeatureError,
)
from .key import canonical_params_json, canonicalize_params, make_feature_key
from .parser import FeatureParseError, parse_feature_expression, parse_params
from .planner import (
    FeatureDataRequirement,
    FeaturePlan,
    FeaturePlanError,
    ResolvedDeploymentComponents,
    build_feature_refs_plan,
    build_feature_plan,
    build_strategy_only_feature_plan,
    collect_feature_refs,
)
from .port import FeatureEnginePort
from .registry import FEATURE_REGISTRY, FeatureRegistry, FeatureRegistryEntry, registry
from .spec import CANONICAL_TIMEFRAMES, FeatureNamespace, FeatureScope, FeatureSpec, FeatureValidationError
from .subscription_manager import (
    PipelineResolver,
    SubscriptionChange,
    SubscriptionDelta,
    SubscriptionEntry,
    SubscriptionManager,
)

__all__ = [
    "CANONICAL_TIMEFRAMES",
    "FEATURE_REGISTRY",
    "INPUT_TIMEFRAME",
    "INTRADAY_SUPPORTED",
    "SESSION_SUPPORTED",
    "SUPPORTED_TIMEFRAMES",
    "BarBuilder",
    "BarBuilderError",
    "BarBuilderRegistry",
    "FixtureCalendar",
    "MarketCalendar",
    "NYSECalendar",
    "SessionWindow",
    "half_day_session",
    "regular_session",
    "FeatureAvailability",
    "FeatureCache",
    "FeatureDataRequirement",
    "FeatureEnginePort",
    "FeatureFrame",
    "FeatureFrameSet",
    "FeatureHydrationBarsRequest",
    "FeatureHydrationBarsSource",
    "FeatureHydrationBlocker",
    "FeatureHydrationRequest",
    "FeatureHydrationResult",
    "FeatureHydrationService",
    "FeatureNamespace",
    "FeatureParseError",
    "FeaturePlan",
    "FeaturePlanError",
    "FeatureRegistry",
    "FeatureRegistryEntry",
    "FeatureScope",
    "FeatureSnapshot",
    "FeatureSpec",
    "FeatureValidationError",
    "FeatureValue",
    "IncrementalFeatureEngine",
    "IncrementalFeatureEngineError",
    "IncrementalFeatureUpdate",
    "NormalizedBar",
    "PipelineResolver",
    "ResolvedDeploymentComponents",
    "SubscriptionChange",
    "SubscriptionDelta",
    "SubscriptionEntry",
    "SubscriptionManager",
    "UnsupportedBatchFeatureError",
    "build_feature_refs_plan",
    "build_feature_plan",
    "build_strategy_only_feature_plan",
    "canonical_params_json",
    "canonicalize_params",
    "collect_feature_refs",
    "make_feature_key",
    "parse_feature_expression",
    "parse_params",
    "registry",
]

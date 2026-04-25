"""Canonical feature identity and registry contracts."""

from .bar_builder import (
    INPUT_TIMEFRAME,
    SUPPORTED_TIMEFRAMES,
    BarBuilder,
    BarBuilderError,
    BarBuilderRegistry,
)
from .batch import BatchFeatureEngine, BatchFeatureEngineError, UnsupportedBatchFeatureError
from .frames import FeatureAvailability, FeatureFrame, FeatureFrameSet, FeatureSnapshot, FeatureValue, NormalizedBar
from .incremental import FeatureCache, IncrementalFeatureEngine, IncrementalFeatureEngineError, IncrementalFeatureUpdate
from .key import canonical_params_json, canonicalize_params, make_feature_key
from .parser import FeatureParseError, parse_feature_expression, parse_params
from .planner import (
    FeatureDataRequirement,
    FeaturePlan,
    FeaturePlanError,
    ResolvedProgramComponents,
    build_feature_plan,
    collect_feature_refs,
)
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
    "SUPPORTED_TIMEFRAMES",
    "BarBuilder",
    "BarBuilderError",
    "BarBuilderRegistry",
    "BatchFeatureEngine",
    "BatchFeatureEngineError",
    "FeatureAvailability",
    "FeatureCache",
    "FeatureDataRequirement",
    "FeatureFrame",
    "FeatureFrameSet",
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
    "ResolvedProgramComponents",
    "SubscriptionChange",
    "SubscriptionDelta",
    "SubscriptionEntry",
    "SubscriptionManager",
    "UnsupportedBatchFeatureError",
    "build_feature_plan",
    "canonical_params_json",
    "canonicalize_params",
    "collect_feature_refs",
    "make_feature_key",
    "parse_feature_expression",
    "parse_params",
    "registry",
]

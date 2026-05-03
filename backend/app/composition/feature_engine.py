from __future__ import annotations

from backend.app.features.port import FeatureEnginePort


_MISSING = object()


def register_feature_engine(state: object, engine: FeatureEnginePort) -> FeatureEnginePort:
    if getattr(state, "feature_engine", _MISSING) is not _MISSING:
        raise ValueError("feature_engine already registered")
    setattr(state, "feature_engine", engine)
    return engine

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.composition.feature_engine import register_feature_engine
from backend.app.features import IncrementalFeatureEngine


def test_register_feature_engine_sets_state() -> None:
    state = SimpleNamespace()
    engine = IncrementalFeatureEngine()

    registered = register_feature_engine(state, engine)

    assert registered is engine
    assert state.feature_engine is engine


def test_registering_feature_engine_twice_raises() -> None:
    state = SimpleNamespace()
    register_feature_engine(state, IncrementalFeatureEngine())

    with pytest.raises(ValueError, match="feature_engine already registered"):
        register_feature_engine(state, IncrementalFeatureEngine())

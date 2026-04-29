from __future__ import annotations

from backend.app.research.regimes import RegimeClassifier


def test_regime_classifier_is_deterministic_and_cached_per_symbol_timeframe_window() -> None:
    classifier = RegimeClassifier()
    window = (100.0, 101.0, 102.0, 103.0, 104.0)

    first = classifier.classify(symbol="spy", timeframe="1d", bar_window=window)
    second = classifier.classify(symbol="SPY", timeframe="1d", bar_window=window)

    assert first is second
    assert classifier.cache_size == 1
    assert first.symbol == "SPY"
    assert first.label in {"bull", "bear", "sideways", "volatile", "trending"}
    assert 0.55 <= first.confidence <= 0.99


def test_regime_classifier_separates_bear_and_volatile_windows() -> None:
    classifier = RegimeClassifier()

    bear = classifier.classify(symbol="QQQ", timeframe="1d", bar_window=(100, 98, 96, 94, 92))
    volatile = classifier.classify(symbol="QQQ", timeframe="1d", bar_window=(100, 110, 90, 112, 88))

    assert bear.label == "bear"
    assert volatile.label == "volatile"

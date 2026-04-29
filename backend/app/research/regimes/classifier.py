from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from statistics import pstdev


REGIME_LABELS = ("bull", "bear", "sideways", "volatile", "trending")


@dataclass(frozen=True)
class RegimeClassification:
    symbol: str
    timeframe: str
    bar_window: tuple[float, ...]
    label: str
    confidence: float


class RegimeClassifier:
    """Classify price windows with a deterministic in-memory cache."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str, tuple[float, ...]], RegimeClassification] = {}

    @property
    def cache_size(self) -> int:
        return len(self._cache)

    def classify(self, *, symbol: str, timeframe: str, bar_window: tuple[float, ...]) -> RegimeClassification:
        if not bar_window:
            raise ValueError("regime classifier requires at least one bar")
        normalized_symbol = symbol.strip().upper()
        normalized_window = tuple(round(float(value), 6) for value in bar_window)
        key = (normalized_symbol, timeframe, normalized_window)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        label, confidence = _classify_window(normalized_window)
        classification = RegimeClassification(
            symbol=normalized_symbol,
            timeframe=timeframe,
            bar_window=normalized_window,
            label=label,
            confidence=confidence,
        )
        self._cache[key] = classification
        return classification


def _classify_window(window: tuple[float, ...]) -> tuple[str, float]:
    if len(window) < 2:
        return ("sideways", 0.55)
    start = window[0]
    end = window[-1]
    drift = 0.0 if start == 0 else (end - start) / start
    returns = [
        0.0 if previous == 0 else (current - previous) / previous
        for previous, current in zip(window, window[1:])
    ]
    volatility = pstdev(returns) if len(returns) > 1 else 0.0
    if volatility >= 0.03:
        return ("volatile", _confidence(volatility, scale=0.08))
    if drift >= 0.025:
        return ("bull", _confidence(drift, scale=0.08))
    if drift <= -0.025:
        return ("bear", _confidence(abs(drift), scale=0.08))
    if abs(drift) >= 0.012:
        return ("trending", _confidence(abs(drift), scale=0.04))
    return ("sideways", _stable_confidence(window))


def _confidence(value: float, *, scale: float) -> float:
    return round(min(0.99, max(0.55, 0.55 + value / scale * 0.4)), 4)


def _stable_confidence(window: tuple[float, ...]) -> float:
    digest = sha256(",".join(str(value) for value in window).encode("utf-8")).hexdigest()
    offset = int(digest[:2], 16) / 255 * 0.1
    return round(0.6 + offset, 4)

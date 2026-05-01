"""Canonical timeframe identifiers bound to DSL timeframed features."""

from __future__ import annotations

# Fixed product order — used when expanding timeframe-variable prefixes for
# static feature catalogs / preload keys.
CANONICAL_TIMEFRAMES_ORDER: tuple[str, ...] = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")

CANONICAL_TIMEFRAMES: frozenset[str] = frozenset(CANONICAL_TIMEFRAMES_ORDER)

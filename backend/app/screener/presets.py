"""Built-in universe presets — small hardcoded lists for V1.

Operator-facing names match the v2 mockup (`Liquid Large Caps`,
`High-Volume ETFs`, etc.). Lists deliberately stay small (≤50 symbols)
so a Screener run completes within seconds even when each symbol triggers
a fresh data-cache read.
"""

from __future__ import annotations

from collections.abc import Mapping


PRESET_LIQUID_LARGE_CAPS: tuple[str, ...] = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD",
    "AVGO", "CRM", "ORCL", "ADBE", "NFLX", "INTC", "QCOM", "PYPL",
    "DIS", "BAC", "JPM", "WFC", "GS", "MS", "C", "AXP",
    "V", "MA", "WMT", "HD", "COST", "TGT", "MCD", "SBUX",
    "KO", "PEP", "PG", "JNJ", "PFE", "MRK", "ABBV", "LLY",
    "XOM", "CVX", "COP",
)

PRESET_HIGH_VOLUME_ETFS: tuple[str, ...] = (
    "SPY", "QQQ", "IWM", "DIA", "VTI", "VOO", "TLT", "HYG",
    "GLD", "SLV", "USO", "UNG", "XLF", "XLK", "XLE", "XLV",
    "XLI", "XLY", "XLP", "ARKK", "TQQQ", "SQQQ",
)

PRESET_MAGNIFICENT_SEVEN: tuple[str, ...] = (
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA",
)


PRESETS: Mapping[str, tuple[str, ...]] = {
    "liquid_large_caps": PRESET_LIQUID_LARGE_CAPS,
    "high_volume_etfs": PRESET_HIGH_VOLUME_ETFS,
    "magnificent_seven": PRESET_MAGNIFICENT_SEVEN,
}


def list_presets() -> tuple[dict[str, object], ...]:
    """Return preset metadata for the operator picker."""
    return tuple(
        {
            "key": key,
            "label": _readable(key),
            "symbol_count": len(syms),
            "sample_symbols": list(syms[:6]),
        }
        for key, syms in PRESETS.items()
    )


def _readable(key: str) -> str:
    return " ".join(part.capitalize() for part in key.split("_"))


def resolve_preset(name: str) -> tuple[str, ...]:
    """Return symbols for a preset name. Raises KeyError when missing."""
    if name not in PRESETS:
        raise KeyError(f"unknown screener preset: {name!r}")
    return PRESETS[name]

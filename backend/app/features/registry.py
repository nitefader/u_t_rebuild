from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .key import canonicalize_params
from .spec import FeatureNamespace, FeatureScope, FeatureSpec, FeatureValidationError


WarmupFn = Callable[[dict[str, Any]], int]


def no_warmup(_: dict[str, Any]) -> int:
    return 0


def length_warmup(params: dict[str, Any]) -> int:
    return max(int(params["length"]) * 3, int(params["length"]))


def exact_length_warmup(params: dict[str, Any]) -> int:
    return int(params["length"])


def macd_warmup(params: dict[str, Any]) -> int:
    fast = int(params.get("fast_length", 12))
    slow = int(params.get("slow_length", 26))
    signal = int(params.get("signal_length", 9))
    return max(fast, slow) * 3 + signal


def supertrend_warmup(params: dict[str, Any]) -> int:
    return int(params["length"]) * 3


def swing_warmup(params: dict[str, Any]) -> int:
    return int(params["lookback"]) * 2 + 1


def support_resistance_warmup(params: dict[str, Any]) -> int:
    return max(int(params.get("lookback", 50)), int(params.get("pivot_strength", 3)) * 2 + 1)


def chikou_warmup(params: dict[str, Any]) -> int:
    return int(params.get("displacement", 26))


def ichimoku_double_warmup(params: dict[str, Any]) -> int:
    return int(params["length"])


@dataclass(frozen=True)
class FeatureRegistryEntry:
    kind: str
    namespace: FeatureNamespace
    scope: FeatureScope
    source: str
    description: str
    allowed_params: frozenset[str] = field(default_factory=frozenset)
    default_params: dict[str, Any] = field(default_factory=dict)
    supported_timeframes: frozenset[str] = field(
        default_factory=lambda: frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"})
    )
    supported_consumers: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "backtest",
                "chart_lab",
                "live",
                "optimization",
                "paper",
                "portfolio_governor",
                "runtime",
                "sim_replay",
                "sim_stream",
                "walk_forward",
            }
        )
    )
    supported_modes: frozenset[str] = field(default_factory=lambda: frozenset({"batch_replay"}))
    warmup: WarmupFn = no_warmup
    version: str = "v1"
    instrument_class: str = "equity"

    def normalized_params(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = {**self.default_params, **(params or {})}
        unknown = set(merged) - set(self.allowed_params)
        if unknown:
            raise FeatureValidationError(f"unsupported params for feature '{self.kind}': {sorted(unknown)}")
        return canonicalize_params(merged)


def _entry(
    kind: str,
    namespace: FeatureNamespace,
    scope: FeatureScope,
    source: str,
    description: str,
    *,
    allowed_params: set[str] | None = None,
    default_params: dict[str, Any] | None = None,
    warmup: WarmupFn = no_warmup,
    instrument_class: str = "equity",
) -> FeatureRegistryEntry:
    return FeatureRegistryEntry(
        kind=kind,
        namespace=namespace,
        scope=scope,
        source=source,
        description=description,
        allowed_params=frozenset(allowed_params or set()),
        default_params=default_params or {},
        warmup=warmup,
        instrument_class=instrument_class,
    )


PRICE_FEATURES = {
    name: _entry(name, FeatureNamespace.PRICE, FeatureScope.SYMBOL, name, f"{name} price field")
    for name in ["open", "high", "low", "close", "volume"]
}

TECHNICAL_FEATURES = {
    "sma": _entry(
        "sma",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "close",
        "Simple moving average",
        allowed_params={"length"},
        default_params={"length": 20},
        warmup=exact_length_warmup,
    ),
    "ema": _entry(
        "ema",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "close",
        "Exponential moving average",
        allowed_params={"length"},
        default_params={"length": 20},
        warmup=length_warmup,
    ),
    "rsi": _entry(
        "rsi",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "close",
        "Relative strength index",
        allowed_params={"length"},
        default_params={"length": 14},
        warmup=length_warmup,
    ),
    "atr": _entry(
        "atr",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hlc",
        "Average true range",
        allowed_params={"length"},
        default_params={"length": 14},
        warmup=length_warmup,
    ),
    "vwap": _entry(
        "vwap",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hlcv",
        "Volume-weighted average price",
        allowed_params={"session"},
        default_params={"session": "regular"},
    ),
    "highest": _entry(
        "highest",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "high",
        "Highest value over a completed lookback window",
        allowed_params={"length", "source"},
        default_params={"length": 20, "source": "high"},
        warmup=exact_length_warmup,
    ),
    "lowest": _entry(
        "lowest",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "low",
        "Lowest value over a completed lookback window",
        allowed_params={"length", "source"},
        default_params={"length": 20, "source": "low"},
        warmup=exact_length_warmup,
    ),
    "down_streak": _entry(
        "down_streak",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "close",
        "Consecutive down-day count (resets to 0 when a bar closes >= prior close)",
    ),
    "ibs": _entry(
        "ibs",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hlc",
        "Internal Bar Strength: (close - low) / (high - low)",
    ),
    "roc": _entry(
        "roc",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "close",
        "Rate of change: (close[t] - close[t-length]) / close[t-length]",
        allowed_params={"length"},
        default_params={"length": 10},
        warmup=exact_length_warmup,
    ),
    "swing_high": _entry(
        "swing_high",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "high",
        "Confirmed swing-high pivot value over +/- lookback bars (k-bar deferred)",
        allowed_params={"lookback"},
        default_params={"lookback": 5},
        warmup=swing_warmup,
    ),
    "swing_low": _entry(
        "swing_low",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "low",
        "Confirmed swing-low pivot value over +/- lookback bars (k-bar deferred)",
        allowed_params={"lookback"},
        default_params={"lookback": 5},
        warmup=swing_warmup,
    ),
    "fvg_up": _entry(
        "fvg_up",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hl",
        "Fair-Value-Gap (up): low[t] - high[t-2] when low[t] > high[t-2]; 0 otherwise",
        allowed_params={"min_size_pct"},
        default_params={"min_size_pct": 0.0},
    ),
    "fvg_down": _entry(
        "fvg_down",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hl",
        "Fair-Value-Gap (down): low[t-2] - high[t] when low[t-2] > high[t]; 0 otherwise",
        allowed_params={"min_size_pct"},
        default_params={"min_size_pct": 0.0},
    ),
    "supertrend": _entry(
        "supertrend",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hlc",
        "Supertrend trend line (ATR-based recurrence)",
        allowed_params={"length", "multiplier"},
        default_params={"length": 10, "multiplier": 3.0},
        warmup=supertrend_warmup,
    ),
    "tenkan_sen": _entry(
        "tenkan_sen",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hl",
        "Ichimoku Tenkan-sen (Conversion Line): (highest(high, length) + lowest(low, length)) / 2",
        allowed_params={"length"},
        default_params={"length": 9},
        warmup=ichimoku_double_warmup,
    ),
    "kijun_sen": _entry(
        "kijun_sen",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hl",
        "Ichimoku Kijun-sen (Base Line): (highest(high, length) + lowest(low, length)) / 2",
        allowed_params={"length"},
        default_params={"length": 26},
        warmup=ichimoku_double_warmup,
    ),
    "senkou_a": _entry(
        "senkou_a",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hl",
        "Ichimoku Senkou A cloud-edge basis (tenkan + kijun)/2 — NO forward displacement (deferred)",
        allowed_params={"tenkan_length", "kijun_length"},
        default_params={"tenkan_length": 9, "kijun_length": 26},
        warmup=lambda p: max(int(p.get("tenkan_length", 9)), int(p.get("kijun_length", 26))),
    ),
    "senkou_b": _entry(
        "senkou_b",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "hl",
        "Ichimoku Senkou B cloud-edge basis (highest+lowest over length)/2 — NO forward displacement (deferred)",
        allowed_params={"length"},
        default_params={"length": 52},
        warmup=ichimoku_double_warmup,
    ),
    "chikou_span": _entry(
        "chikou_span",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "close",
        "Ichimoku Chikou Span: close shifted backward N bars (so close[t-N] aligns to t)",
        allowed_params={"displacement"},
        default_params={"displacement": 26},
        warmup=chikou_warmup,
    ),
    "macd": _entry(
        "macd",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "close",
        "MACD: 'line'=EMA(fast)-EMA(slow); 'signal'=EMA(line, signal_length); 'histogram'=line-signal",
        allowed_params={"fast_length", "slow_length", "signal_length", "output"},
        default_params={"fast_length": 12, "slow_length": 26, "signal_length": 9, "output": "line"},
        warmup=macd_warmup,
    ),
    "support": _entry(
        "support",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "low",
        "Pivot-clustered support level (output_index=0 nearest below; higher index = further away)",
        allowed_params={"lookback", "pivot_strength", "level_count", "cluster_pct", "output_index"},
        default_params={"lookback": 50, "pivot_strength": 3, "level_count": 3, "cluster_pct": 0.25, "output_index": 0},
        warmup=support_resistance_warmup,
    ),
    "resistance": _entry(
        "resistance",
        FeatureNamespace.TECHNICAL,
        FeatureScope.SYMBOL,
        "high",
        "Pivot-clustered resistance level (output_index=0 nearest above; higher index = further away)",
        allowed_params={"lookback", "pivot_strength", "level_count", "cluster_pct", "output_index"},
        default_params={"lookback": 50, "pivot_strength": 3, "level_count": 3, "cluster_pct": 0.25, "output_index": 0},
        warmup=support_resistance_warmup,
    ),
}

SESSION_FEATURES = {
    name: _entry(name, FeatureNamespace.SESSION, FeatureScope.SESSION, "session", description, allowed_params=params, default_params=defaults)
    for name, description, params, defaults in [
        ("session_state", "Current exchange session state", set(), {}),
        ("regular_session_high_so_far", "Current regular-session high so far", set(), {}),
        ("regular_session_low_so_far", "Current regular-session low so far", set(), {}),
        (
            "opening_range_high",
            "Opening range high after the configured window is complete",
            {"session", "window_minutes"},
            {"session": "regular", "window_minutes": 15},
        ),
        (
            "opening_range_low",
            "Opening range low after the configured window is complete",
            {"session", "window_minutes"},
            {"session": "regular", "window_minutes": 15},
        ),
        (
            "opening_range_mid",
            "Opening range midpoint after the configured window is complete",
            {"session", "window_minutes"},
            {"session": "regular", "window_minutes": 15},
        ),
        (
            "opening_range_width",
            "Opening range width after the configured window is complete",
            {"session", "window_minutes"},
            {"session": "regular", "window_minutes": 15},
        ),
        (
            "opening_range_width_pct",
            "Opening range width percentage after the configured window is complete",
            {"session", "window_minutes"},
            {"session": "regular", "window_minutes": 15},
        ),
        (
            "opening_range_complete",
            "Whether the opening range window is complete",
            {"session", "window_minutes"},
            {"session": "regular", "window_minutes": 15},
        ),
        ("prior_day_high", "Previous completed trading day high", set(), {}),
        ("prior_day_low", "Previous completed trading day low", set(), {}),
        ("prior_day_close", "Previous completed trading day close", set(), {}),
        ("gap_pct", "Current session gap percentage versus previous close", set(), {}),
    ]
}

PORTFOLIO_FEATURES = {
    name: _entry(name, FeatureNamespace.PORTFOLIO, FeatureScope.PORTFOLIO, "portfolio", description, instrument_class="portfolio_state")
    for name, description in [
        ("gross_exposure_pct", "Portfolio gross exposure percentage"),
        ("net_exposure_pct", "Portfolio net exposure percentage"),
        ("open_risk_pct", "Open portfolio risk percentage"),
        ("pending_open_risk_pct", "Pending open risk percentage"),
        ("symbol_concentration_pct", "Symbol concentration percentage"),
        ("new_open_slots_remaining", "Remaining new open slots"),
        ("broker_sync_stale", "Whether broker sync is stale"),
        ("global_kill_active", "Whether global kill is active"),
        ("account_pause_active", "Whether account pause is active"),
        ("deployment_pause_active", "Whether deployment pause is active"),
    ]
}

FEATURE_REGISTRY: dict[str, FeatureRegistryEntry] = {
    **PRICE_FEATURES,
    **TECHNICAL_FEATURES,
    **SESSION_FEATURES,
    **PORTFOLIO_FEATURES,
}


class FeatureRegistry:
    def __init__(self, entries: dict[str, FeatureRegistryEntry] | None = None) -> None:
        self._entries = entries or FEATURE_REGISTRY

    def get(self, kind: str) -> FeatureRegistryEntry:
        normalized = kind.strip().lower()
        try:
            return self._entries[normalized]
        except KeyError as exc:
            raise FeatureValidationError(f"unsupported feature '{kind}'") from exc

    def create_spec(
        self,
        *,
        kind: str,
        timeframe: str,
        params: dict[str, Any] | None = None,
        lookback: int = 0,
        shift: int = 0,
    ) -> FeatureSpec:
        entry = self.get(kind)
        normalized_params = entry.normalized_params(params)
        if timeframe not in entry.supported_timeframes:
            raise FeatureValidationError(f"feature '{entry.kind}' does not support timeframe '{timeframe}'")
        return FeatureSpec(
            kind=entry.kind,
            namespace=entry.namespace,
            timeframe=timeframe,
            source=entry.source,
            params=normalized_params,
            lookback=lookback,
            shift=shift,
            scope=entry.scope,
            version=entry.version,
        )

    def require_consumer_support(self, kind: str, consumer: str) -> None:
        entry = self.get(kind)
        if consumer not in entry.supported_consumers:
            raise FeatureValidationError(f"feature '{kind}' is not supported by consumer '{consumer}'")

    def warmup_bars(self, spec: FeatureSpec) -> int:
        entry = self.get(spec.kind)
        return entry.warmup(dict(spec.params))

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "kind": entry.kind,
                "namespace": entry.namespace.value,
                "scope": entry.scope.value,
                "source": entry.source,
                "description": entry.description,
                "allowed_params": sorted(entry.allowed_params),
                "default_params": entry.default_params,
                "supported_timeframes": sorted(entry.supported_timeframes),
                "supported_consumers": sorted(entry.supported_consumers),
                "supported_modes": sorted(entry.supported_modes),
                "instrument_class": entry.instrument_class,
                "version": entry.version,
            }
            for entry in sorted(self._entries.values(), key=lambda item: item.kind)
        ]


registry = FeatureRegistry()

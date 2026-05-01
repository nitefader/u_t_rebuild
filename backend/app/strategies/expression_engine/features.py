"""Feature catalog for the expression engine.

FeatureSpec describes a single feature (arity, args, return type, etc.).
FeatureCatalog is a lookup table keyed by fully-qualified names like
"5m.ema", "session.is_open", "bar.close".

default_catalog() returns a FeatureCatalog seeded with all 50+ features
from the v4 palette.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class FeatureSpec:
    """Describes one feature in the catalog."""
    name: str                               # "ema"
    namespace: str                          # "" for tf-features; "session"/"orb"/"prior_day"/"bar" for non-tf
    is_timeframed: bool
    arity: int                              # number of positional args; 0 for zero-arity; -1 for variadic
    arg_names: tuple[str, ...]
    arg_defaults: tuple[float | int, ...]
    return_type: str                        # "float" or "bool"
    description: str
    category: str = "other"                 # "trend"|"momentum"|"volatility"|"volume"|"bb"|"time"|"bar"


class FeatureCatalog:
    """Immutable lookup table of FeatureSpec entries.

    Keys:
      - Timeframed features:  "<name>"  (lookup ignores timeframe; validator checks later)
      - Non-tf features:      "<namespace>.<name>"  e.g. "session.is_open"
    """

    def __init__(self, specs: list[FeatureSpec]) -> None:
        self._by_key: dict[str, FeatureSpec] = {}
        for spec in specs:
            key = self._make_key(spec)
            self._by_key[key] = spec

    @staticmethod
    def _make_key(spec: FeatureSpec) -> str:
        if spec.is_timeframed:
            return spec.name
        if spec.namespace:
            return f"{spec.namespace}.{spec.name}"
        return spec.name

    def get(self, key: str) -> FeatureSpec | None:
        """Look up by key.  Examples: "ema", "session.is_open", "orb.high", "bar.close"."""
        return self._by_key.get(key)

    def all(self) -> list[FeatureSpec]:
        """Return all registered FeatureSpec instances."""
        return list(self._by_key.values())

    def __iter__(self) -> Iterator[FeatureSpec]:
        return iter(self._by_key.values())


def default_catalog() -> FeatureCatalog:
    """Return the canonical v4 feature catalog with all 50+ features."""

    def tf(
        name: str,
        arity: int,
        arg_names: tuple[str, ...],
        arg_defaults: tuple[float | int, ...],
        return_type: str = "float",
        description: str = "",
        category: str = "other",
    ) -> FeatureSpec:
        return FeatureSpec(
            name=name,
            namespace="",
            is_timeframed=True,
            arity=arity,
            arg_names=arg_names,
            arg_defaults=arg_defaults,
            return_type=return_type,
            description=description,
            category=category,
        )

    def nontf(
        name: str,
        namespace: str,
        arity: int,
        arg_names: tuple[str, ...],
        arg_defaults: tuple[float | int, ...],
        return_type: str = "float",
        description: str = "",
        category: str = "other",
    ) -> FeatureSpec:
        return FeatureSpec(
            name=name,
            namespace=namespace,
            is_timeframed=False,
            arity=arity,
            arg_names=arg_names,
            arg_defaults=arg_defaults,
            return_type=return_type,
            description=description,
            category=category,
        )

    specs: list[FeatureSpec] = [
        # ---------------------------------------------------------------
        # Trend (timeframed)
        # ---------------------------------------------------------------
        tf("ema",              1, ("period",),             (9,),       description="Exponential moving average",              category="trend"),
        tf("sma",              1, ("period",),             (20,),      description="Simple moving average",                   category="trend"),
        tf("wma",              1, ("period",),             (20,),      description="Weighted moving average",                 category="trend"),
        tf("hma",              1, ("period",),             (14,),      description="Hull moving average",                     category="trend"),
        tf("vwap",             0, (),                       (),         description="Volume-weighted average price",           category="trend"),
        tf("supertrend",       2, ("period", "mult"),      (10, 3),    description="Supertrend indicator",                    category="trend"),
        tf("donchian_high",    1, ("period",),             (20,),      description="Donchian channel upper band",             category="trend"),
        tf("donchian_low",     1, ("period",),             (20,),      description="Donchian channel lower band",             category="trend"),
        tf("ichimoku_tenkan",  0, (),                       (),         description="Ichimoku Tenkan-sen (conversion line)",  category="trend"),
        tf("ichimoku_kijun",   0, (),                       (),         description="Ichimoku Kijun-sen (base line)",         category="trend"),

        # ---------------------------------------------------------------
        # Momentum (timeframed)
        # ---------------------------------------------------------------
        tf("rsi",              1, ("period",),             (14,),      description="Relative strength index",                 category="momentum"),
        tf("macd_line",        3, ("fast", "slow", "signal"), (12, 26, 9), description="MACD line",                          category="momentum"),
        tf("macd_signal",      3, ("fast", "slow", "signal"), (12, 26, 9), description="MACD signal line",                   category="momentum"),
        tf("macd_hist",        3, ("fast", "slow", "signal"), (12, 26, 9), description="MACD histogram",                     category="momentum"),
        tf("cci",              1, ("period",),             (20,),      description="Commodity channel index",                 category="momentum"),
        tf("stoch_k",          2, ("period", "smooth"),    (14, 3),    description="Stochastic %K",                          category="momentum"),
        tf("stoch_d",          2, ("period", "smooth"),    (14, 3),    description="Stochastic %D",                          category="momentum"),
        tf("roc",              1, ("period",),             (10,),      description="Rate of change",                         category="momentum"),
        tf("williams_r",       1, ("period",),             (14,),      description="Williams %R",                            category="momentum"),

        # ---------------------------------------------------------------
        # Volatility (timeframed)
        # ---------------------------------------------------------------
        tf("atr",              1, ("period",),             (14,),      description="Average true range",                     category="volatility"),
        tf("true_range",       0, (),                       (),         description="Current true range",                     category="volatility"),
        tf("natr",             1, ("period",),             (14,),      description="Normalised ATR",                         category="volatility"),
        tf("historical_vol",   1, ("period",),             (20,),      description="Historical volatility",                  category="volatility"),

        # ---------------------------------------------------------------
        # Volume (timeframed)
        # ---------------------------------------------------------------
        tf("volume",           0, (),                       (),         description="Current bar volume",                     category="volume"),
        tf("volume_sma",       1, ("period",),             (20,),      description="Volume simple moving average",           category="volume"),
        tf("rvol",             1, ("period",),             (20,),      description="Relative volume",                        category="volume"),
        tf("obv",              0, (),                       (),         description="On-balance volume",                      category="volume"),
        tf("cmf",              1, ("period",),             (20,),      description="Chaikin money flow",                     category="volume"),
        tf("mfi",              1, ("period",),             (14,),      description="Money flow index",                       category="volume"),

        # ---------------------------------------------------------------
        # Bollinger / Keltner (timeframed)
        # ---------------------------------------------------------------
        tf("bb_upper",         2, ("period", "std"),       (20, 2),    description="Bollinger upper band",                   category="bb"),
        tf("bb_lower",         2, ("period", "std"),       (20, 2),    description="Bollinger lower band",                   category="bb"),
        tf("bb_middle",        1, ("period",),             (20,),      description="Bollinger middle band",                  category="bb"),
        tf("bb_width",         2, ("period", "std"),       (20, 2),    description="Bollinger band width",                   category="bb"),
        tf("kc_upper",         2, ("period", "mult"),      (20, 2),    description="Keltner channel upper band",             category="bb"),
        tf("kc_lower",         2, ("period", "mult"),      (20, 2),    description="Keltner channel lower band",             category="bb"),

        # ---------------------------------------------------------------
        # Bar OHLCV fields (timeframed; also accessible via bar[-N].field)
        # ---------------------------------------------------------------
        tf("close",            0, (),                       (),         description="Close price",                            category="bar"),
        tf("open",             0, (),                       (),         description="Open price",                             category="bar"),
        tf("high",             0, (),                       (),         description="High price",                             category="bar"),
        tf("low",              0, (),                       (),         description="Low price",                              category="bar"),
        tf("range",            0, (),                       (),         description="High - Low range",                       category="bar"),
        tf("body",             0, (),                       (),         description="|Close - Open| body size",               category="bar"),
        tf("is_doji",          0, (),                       (),         return_type="bool", description="True if candle is a doji", category="bar"),

        # ---------------------------------------------------------------
        # Session namespace (non-timeframed)
        # ---------------------------------------------------------------
        nontf("is_open",              "session", 0, (), (), return_type="bool",  description="True if market session is open",          category="time"),
        nontf("minutes_since_open",   "session", 0, (), (), return_type="float", description="Minutes elapsed since session open",       category="time"),
        nontf("minutes_to_close",     "session", 0, (), (), return_type="float", description="Minutes remaining until session close",    category="time"),
        nontf("is_power_hour",        "session", 0, (), (), return_type="bool",  description="True if currently in power hour",         category="time"),

        # ---------------------------------------------------------------
        # ORB namespace (non-timeframed)
        # ---------------------------------------------------------------
        nontf("high",   "orb", 1, ("window",), (15,), return_type="float", description="Opening range high",  category="bar"),
        nontf("low",    "orb", 1, ("window",), (15,), return_type="float", description="Opening range low",   category="bar"),
        nontf("range",  "orb", 1, ("window",), (15,), return_type="float", description="Opening range width", category="bar"),

        # ---------------------------------------------------------------
        # Prior-day namespace (non-timeframed, zero-arity)
        # ---------------------------------------------------------------
        nontf("high",  "prior_day", 0, (), (), return_type="float", description="Previous session high",  category="bar"),
        nontf("low",   "prior_day", 0, (), (), return_type="float", description="Previous session low",   category="bar"),
        nontf("close", "prior_day", 0, (), (), return_type="float", description="Previous session close", category="bar"),

        # ---------------------------------------------------------------
        # Bar namespace (non-timeframed; bar[-N].field uses these specs)
        # ---------------------------------------------------------------
        nontf("close", "bar", 0, (), (), return_type="float", description="Bar lookback close", category="bar"),
        nontf("open",  "bar", 0, (), (), return_type="float", description="Bar lookback open",  category="bar"),
        nontf("high",  "bar", 0, (), (), return_type="float", description="Bar lookback high",  category="bar"),
        nontf("low",   "bar", 0, (), (), return_type="float", description="Bar lookback low",   category="bar"),
        nontf("range", "bar", 0, (), (), return_type="float", description="Bar lookback range", category="bar"),
        nontf("body",  "bar", 0, (), (), return_type="float", description="Bar lookback body",  category="bar"),
    ]

    return FeatureCatalog(specs)

"""Operator-facing Screener templates and Alpaca market-list definitions."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .domain import (
    ScreenerCriterion,
    ScreenerCriterionOperator,
    ScreenerExpression,
    ScreenerExpressionKind,
    ScreenerMetric,
    ScreenerUniverseSource,
    ScreenerUniverseSourceKind,
    ScreenerVersion,
)


@dataclass(frozen=True)
class ScreenerTemplateDefinition:
    key: str
    label: str
    category: str
    description: str
    universe_source: ScreenerUniverseSource
    expression: ScreenerExpression
    sort_metric: ScreenerMetric | None
    sort_descending: bool = True
    timeframe: str = "1d"
    tags: tuple[str, ...] = ()

    def to_api(self) -> dict[str, object]:
        payload = asdict(self)
        payload["universe_source"] = self.universe_source.model_dump(mode="json")
        payload["expression"] = self.expression.model_dump(mode="json")
        payload["sort_metric"] = self.sort_metric.value if self.sort_metric is not None else None
        return payload


@dataclass(frozen=True)
class MarketListDefinition:
    key: str
    label: str
    category: str
    provider: str
    description: str
    source: str

    def to_api(self) -> dict[str, object]:
        return asdict(self)


def _criterion(
    metric: ScreenerMetric,
    operator: ScreenerCriterionOperator,
    value: bool | float | str,
    *,
    value_max: float | None = None,
    label: str | None = None,
) -> ScreenerExpression:
    return ScreenerExpression(
        kind=ScreenerExpressionKind.CRITERION,
        criterion=ScreenerCriterion(
            metric=metric,
            operator=operator,
            value=value,
            value_max=value_max,
            label=label,
        ),
    )


def _all(*children: ScreenerExpression) -> ScreenerExpression:
    return ScreenerExpression(kind=ScreenerExpressionKind.ALL, children=children)


def _market_source(key: str) -> ScreenerUniverseSource:
    return ScreenerUniverseSource(kind=ScreenerUniverseSourceKind.MARKET_LIST, market_list_key=key)


def _preset_source(key: str) -> ScreenerUniverseSource:
    return ScreenerUniverseSource(kind=ScreenerUniverseSourceKind.PRESET, preset=key)


MARKET_LISTS: tuple[MarketListDefinition, ...] = (
    MarketListDefinition(
        key="day_gainers",
        label="Day Gainers",
        category="Market Movers",
        provider="alpaca",
        source="alpaca_screener.market_movers.gainers",
        description="Top Alpaca stock gainers for the current market session.",
    ),
    MarketListDefinition(
        key="day_losers",
        label="Day Losers",
        category="Market Movers",
        provider="alpaca",
        source="alpaca_screener.market_movers.losers",
        description="Top Alpaca stock losers for the current market session.",
    ),
    MarketListDefinition(
        key="most_active",
        label="Most Active",
        category="Day Trading",
        provider="alpaca",
        source="alpaca_screener.most_actives",
        description="Most active Alpaca stocks by volume.",
    ),
)


TEMPLATES: tuple[ScreenerTemplateDefinition, ...] = (
    ScreenerTemplateDefinition(
        key="day_gainers",
        label="Day Gainers",
        category="Market Movers",
        description="Start from Alpaca day gainers and keep liquid, tradable names.",
        universe_source=_market_source("day_gainers"),
        expression=_all(
            _criterion(ScreenerMetric.BROKER_TRADABLE, ScreenerCriterionOperator.EQ, True),
            _criterion(ScreenerMetric.AVG_VOLUME_20D, ScreenerCriterionOperator.GTE, 500_000),
        ),
        sort_metric=ScreenerMetric.CHANGE_PCT,
        tags=("market_movers", "day_trading"),
    ),
    ScreenerTemplateDefinition(
        key="day_losers",
        label="Day Losers",
        category="Market Movers",
        description="Start from Alpaca day losers and keep liquid, tradable names.",
        universe_source=_market_source("day_losers"),
        expression=_all(
            _criterion(ScreenerMetric.BROKER_TRADABLE, ScreenerCriterionOperator.EQ, True),
            _criterion(ScreenerMetric.AVG_VOLUME_20D, ScreenerCriterionOperator.GTE, 500_000),
        ),
        sort_metric=ScreenerMetric.CHANGE_PCT,
        sort_descending=False,
        tags=("market_movers", "day_trading"),
    ),
    ScreenerTemplateDefinition(
        key="most_active",
        label="Most Active",
        category="Day Trading",
        description="Alpaca most-active stocks with tradability evidence.",
        universe_source=_market_source("most_active"),
        expression=_all(_criterion(ScreenerMetric.BROKER_TRADABLE, ScreenerCriterionOperator.EQ, True)),
        sort_metric=ScreenerMetric.RELATIVE_VOLUME,
        tags=("day_trading", "liquidity"),
    ),
    ScreenerTemplateDefinition(
        key="high_relative_volume",
        label="High Relative Volume",
        category="Day Trading",
        description="Liquid large caps trading at elevated relative volume.",
        universe_source=_preset_source("liquid_large_caps"),
        expression=_all(
            _criterion(ScreenerMetric.RELATIVE_VOLUME, ScreenerCriterionOperator.GTE, 2.0),
            _criterion(ScreenerMetric.AVG_VOLUME_20D, ScreenerCriterionOperator.GTE, 1_000_000),
            _criterion(ScreenerMetric.BROKER_TRADABLE, ScreenerCriterionOperator.EQ, True),
        ),
        sort_metric=ScreenerMetric.RELATIVE_VOLUME,
        tags=("day_trading", "relative_volume"),
    ),
    ScreenerTemplateDefinition(
        key="fractionable_momentum",
        label="Fractionable Momentum",
        category="Broker Capability",
        description="Fractionable names with positive momentum and healthy liquidity.",
        universe_source=_preset_source("liquid_large_caps"),
        expression=_all(
            _criterion(ScreenerMetric.BROKER_FRACTIONABLE, ScreenerCriterionOperator.EQ, True),
            _criterion(ScreenerMetric.CHANGE_PCT, ScreenerCriterionOperator.GTE, 1.0),
            _criterion(ScreenerMetric.AVG_VOLUME_20D, ScreenerCriterionOperator.GTE, 500_000),
        ),
        sort_metric=ScreenerMetric.CHANGE_PCT,
        tags=("broker_capability", "momentum"),
    ),
    ScreenerTemplateDefinition(
        key="shortable_fade_candidates",
        label="Shortable Fade Candidates",
        category="Broker Capability",
        description="Shortable, easy-to-borrow names extended to the upside.",
        universe_source=_preset_source("liquid_large_caps"),
        expression=_all(
            _criterion(ScreenerMetric.BROKER_SHORTABLE, ScreenerCriterionOperator.EQ, True),
            _criterion(ScreenerMetric.BROKER_EASY_TO_BORROW, ScreenerCriterionOperator.EQ, True),
            _criterion(ScreenerMetric.RSI_14, ScreenerCriterionOperator.GTE, 70),
            _criterion(ScreenerMetric.RELATIVE_VOLUME, ScreenerCriterionOperator.GTE, 1.5),
        ),
        sort_metric=ScreenerMetric.RSI_14,
        tags=("broker_capability", "shortable"),
    ),
    ScreenerTemplateDefinition(
        key="liquid_large_caps",
        label="Liquid Large Caps",
        category="Swing",
        description="Large-cap universe with baseline liquidity.",
        universe_source=_preset_source("liquid_large_caps"),
        expression=_all(_criterion(ScreenerMetric.AVG_VOLUME_20D, ScreenerCriterionOperator.GTE, 1_000_000)),
        sort_metric=ScreenerMetric.AVG_VOLUME_20D,
        tags=("swing", "liquidity"),
    ),
    ScreenerTemplateDefinition(
        key="high_volume_etfs",
        label="High Volume ETFs",
        category="Swing",
        description="High-volume ETF universe.",
        universe_source=_preset_source("high_volume_etfs"),
        expression=_all(_criterion(ScreenerMetric.AVG_VOLUME_20D, ScreenerCriterionOperator.GTE, 500_000)),
        sort_metric=ScreenerMetric.AVG_VOLUME_20D,
        tags=("etf", "liquidity"),
    ),
)


def list_templates() -> tuple[dict[str, object], ...]:
    return tuple(template.to_api() for template in TEMPLATES)


def list_market_lists() -> tuple[dict[str, object], ...]:
    return tuple(definition.to_api() for definition in MARKET_LISTS)


def get_template(key: str) -> ScreenerTemplateDefinition:
    normalized = key.strip().lower().replace("-", "_")
    for template in TEMPLATES:
        if template.key == normalized:
            return template
    raise KeyError(f"unknown screener template: {key}")


def version_from_template(
    key: str,
    *,
    screener_id,
    name: str | None = None,
) -> ScreenerVersion:
    template = get_template(key)
    return ScreenerVersion(
        screener_id=screener_id,
        name=name or template.label,
        description=template.description,
        universe_source=template.universe_source,
        criteria=(),
        expression=template.expression,
        timeframe=template.timeframe,  # type: ignore[arg-type]
        sort_metric=template.sort_metric,
        sort_descending=template.sort_descending,
        tags=template.tags,
    )

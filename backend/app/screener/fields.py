"""Typed field registry for Screener expressions.

The registry is operator-facing metadata, not runtime strategy logic. It tells
the UI and validator which fields can be used, how they are computed, and how
to fail when a provider cannot supply them.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from .domain import ScreenerCriterionOperator, ScreenerMetric


class ScreenerFieldType(StrEnum):
    NUMBER = "number"
    BOOLEAN = "boolean"
    STRING = "string"


@dataclass(frozen=True)
class ScreenerFieldDefinition:
    key: str
    label: str
    value_type: ScreenerFieldType
    unit: str | None
    sources: tuple[str, ...]
    cadence: str
    unavailable_behavior: str
    supported_operators: tuple[ScreenerCriterionOperator, ...]

    def to_api(self) -> dict[str, object]:
        payload = asdict(self)
        payload["value_type"] = self.value_type.value
        payload["supported_operators"] = tuple(op.value for op in self.supported_operators)
        return payload


NUMERIC_OPERATORS = (
    ScreenerCriterionOperator.GTE,
    ScreenerCriterionOperator.GT,
    ScreenerCriterionOperator.LTE,
    ScreenerCriterionOperator.LT,
    ScreenerCriterionOperator.BETWEEN,
    ScreenerCriterionOperator.EQ,
)
EQUALITY_OPERATORS = (ScreenerCriterionOperator.EQ,)


FIELD_DEFINITIONS: dict[ScreenerMetric, ScreenerFieldDefinition] = {
    ScreenerMetric.PRICE: ScreenerFieldDefinition(
        key=ScreenerMetric.PRICE.value,
        label="Last price",
        value_type=ScreenerFieldType.NUMBER,
        unit="$",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.AVG_VOLUME_20D: ScreenerFieldDefinition(
        key=ScreenerMetric.AVG_VOLUME_20D.value,
        label="Average volume (20d)",
        value_type=ScreenerFieldType.NUMBER,
        unit="shares",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.RELATIVE_VOLUME: ScreenerFieldDefinition(
        key=ScreenerMetric.RELATIVE_VOLUME.value,
        label="Relative volume",
        value_type=ScreenerFieldType.NUMBER,
        unit="x",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.GAP_PCT: ScreenerFieldDefinition(
        key=ScreenerMetric.GAP_PCT.value,
        label="Gap from prior close",
        value_type=ScreenerFieldType.NUMBER,
        unit="%",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.CHANGE_PCT: ScreenerFieldDefinition(
        key=ScreenerMetric.CHANGE_PCT.value,
        label="Change from prior close",
        value_type=ScreenerFieldType.NUMBER,
        unit="%",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.RSI_14: ScreenerFieldDefinition(
        key=ScreenerMetric.RSI_14.value,
        label="RSI(14)",
        value_type=ScreenerFieldType.NUMBER,
        unit="0..100",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.ATR_14_PCT: ScreenerFieldDefinition(
        key=ScreenerMetric.ATR_14_PCT.value,
        label="ATR(14) as percent of price",
        value_type=ScreenerFieldType.NUMBER,
        unit="%",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.PRIOR_DAY_CLOSE: ScreenerFieldDefinition(
        key=ScreenerMetric.PRIOR_DAY_CLOSE.value,
        label="Prior day close",
        value_type=ScreenerFieldType.NUMBER,
        unit="$",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.PRIOR_DAY_RANGE_PCT: ScreenerFieldDefinition(
        key=ScreenerMetric.PRIOR_DAY_RANGE_PCT.value,
        label="Prior day range",
        value_type=ScreenerFieldType.NUMBER,
        unit="%",
        sources=("data_center.bar_cache", "computed_from_bars"),
        cadence="per run",
        unavailable_behavior="symbol fails this criterion with metric unavailable",
        supported_operators=NUMERIC_OPERATORS,
    ),
    ScreenerMetric.BROKER_TRADABLE: ScreenerFieldDefinition(
        key=ScreenerMetric.BROKER_TRADABLE.value,
        label="Tradable at Alpaca",
        value_type=ScreenerFieldType.BOOLEAN,
        unit=None,
        sources=("alpaca_assets",),
        cadence="per run",
        unavailable_behavior="symbol fails closed for broker-capability criteria",
        supported_operators=EQUALITY_OPERATORS,
    ),
    ScreenerMetric.BROKER_FRACTIONABLE: ScreenerFieldDefinition(
        key=ScreenerMetric.BROKER_FRACTIONABLE.value,
        label="Fractionable at Alpaca",
        value_type=ScreenerFieldType.BOOLEAN,
        unit=None,
        sources=("alpaca_assets",),
        cadence="per run",
        unavailable_behavior="symbol fails closed for broker-capability criteria",
        supported_operators=EQUALITY_OPERATORS,
    ),
    ScreenerMetric.BROKER_SHORTABLE: ScreenerFieldDefinition(
        key=ScreenerMetric.BROKER_SHORTABLE.value,
        label="Shortable at Alpaca",
        value_type=ScreenerFieldType.BOOLEAN,
        unit=None,
        sources=("alpaca_assets",),
        cadence="per run",
        unavailable_behavior="symbol fails closed for broker-capability criteria",
        supported_operators=EQUALITY_OPERATORS,
    ),
    ScreenerMetric.BROKER_EASY_TO_BORROW: ScreenerFieldDefinition(
        key=ScreenerMetric.BROKER_EASY_TO_BORROW.value,
        label="Easy to borrow at Alpaca",
        value_type=ScreenerFieldType.BOOLEAN,
        unit=None,
        sources=("alpaca_assets",),
        cadence="per run",
        unavailable_behavior="symbol fails closed for broker-capability criteria",
        supported_operators=EQUALITY_OPERATORS,
    ),
    ScreenerMetric.BROKER_ACTIVE: ScreenerFieldDefinition(
        key=ScreenerMetric.BROKER_ACTIVE.value,
        label="Active Alpaca asset",
        value_type=ScreenerFieldType.BOOLEAN,
        unit=None,
        sources=("alpaca_assets",),
        cadence="per run",
        unavailable_behavior="symbol fails closed for broker-capability criteria",
        supported_operators=EQUALITY_OPERATORS,
    ),
    ScreenerMetric.BROKER_EXCHANGE: ScreenerFieldDefinition(
        key=ScreenerMetric.BROKER_EXCHANGE.value,
        label="Alpaca exchange",
        value_type=ScreenerFieldType.STRING,
        unit=None,
        sources=("alpaca_assets",),
        cadence="per run",
        unavailable_behavior="symbol fails closed for broker-capability criteria",
        supported_operators=EQUALITY_OPERATORS,
    ),
    ScreenerMetric.BROKER_ASSET_CLASS: ScreenerFieldDefinition(
        key=ScreenerMetric.BROKER_ASSET_CLASS.value,
        label="Alpaca asset class",
        value_type=ScreenerFieldType.STRING,
        unit=None,
        sources=("alpaca_assets",),
        cadence="per run",
        unavailable_behavior="symbol fails closed for broker-capability criteria",
        supported_operators=EQUALITY_OPERATORS,
    ),
    ScreenerMetric.BROKER_NAME: ScreenerFieldDefinition(
        key=ScreenerMetric.BROKER_NAME.value,
        label="Company name",
        value_type=ScreenerFieldType.STRING,
        unit=None,
        sources=("alpaca_assets",),
        cadence="per run",
        unavailable_behavior="left blank when unavailable",
        supported_operators=EQUALITY_OPERATORS,
    ),
}


def list_field_definitions() -> tuple[ScreenerFieldDefinition, ...]:
    return tuple(FIELD_DEFINITIONS[field] for field in ScreenerMetric)


def get_field_definition(field: ScreenerMetric) -> ScreenerFieldDefinition:
    return FIELD_DEFINITIONS[field]


def api_field_definitions() -> tuple[dict[str, object], ...]:
    return tuple(definition.to_api() for definition in list_field_definitions())

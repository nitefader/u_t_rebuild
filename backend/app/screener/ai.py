"""Deterministic advisory composer for Screener drafts.

This module is deliberately not a runtime mutator. It compiles a prompt into a
visible typed draft plus assumptions/unsupported clauses. The caller decides
whether to save or run anything.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .domain import (
    ScreenerCriterion,
    ScreenerCriterionOperator,
    ScreenerExpression,
    ScreenerExpressionKind,
    ScreenerMetric,
    ScreenerUniverseSource,
    ScreenerUniverseSourceKind,
)
from .templates import get_template


class ScreenerAIInterpretRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1)
    operator_session_id: str | None = None


class ScreenerAIInterpretResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    advisory_only: bool = True
    suggested_template_keys: tuple[str, ...] = ()
    universe_source: ScreenerUniverseSource
    expression: ScreenerExpression
    assumptions: tuple[str, ...] = ()
    unsupported_clauses: tuple[str, ...] = ()
    audit_preview: dict[str, object] = Field(default_factory=dict)


def interpret_screener_prompt(request: ScreenerAIInterpretRequest) -> ScreenerAIInterpretResponse:
    prompt = request.prompt.strip()
    lowered = prompt.lower()
    assumptions: list[str] = ["AI output is advisory only; operator must approve before saving or running."]
    unsupported: list[str] = []

    template_key = _template_for_prompt(lowered)
    template = get_template(template_key)
    children = list(template.expression.children)
    universe_source = template.universe_source

    if "fractionable" in lowered:
        children.append(_criterion(ScreenerMetric.BROKER_FRACTIONABLE, True, "Fractionable at Alpaca"))
    if "tradable" in lowered:
        children.append(_criterion(ScreenerMetric.BROKER_TRADABLE, True, "Tradable at Alpaca"))
    if "shortable" in lowered:
        children.append(_criterion(ScreenerMetric.BROKER_SHORTABLE, True, "Shortable at Alpaca"))
    if "easy to borrow" in lowered or "etb" in lowered:
        children.append(_criterion(ScreenerMetric.BROKER_EASY_TO_BORROW, True, "Easy to borrow at Alpaca"))
    if "under $30" in lowered or "under 30" in lowered:
        children.append(_numeric(ScreenerMetric.PRICE, ScreenerCriterionOperator.LT, 30, "Price under $30"))
    if "under $50" in lowered or "under 50" in lowered:
        children.append(_numeric(ScreenerMetric.PRICE, ScreenerCriterionOperator.LT, 50, "Price under $50"))
    if "rvol over 3" in lowered or "relative volume over 3" in lowered:
        children.append(_numeric(ScreenerMetric.RELATIVE_VOLUME, ScreenerCriterionOperator.GTE, 3, "Relative volume at least 3x"))
    elif "rvol" in lowered or "relative volume" in lowered:
        children.append(_numeric(ScreenerMetric.RELATIVE_VOLUME, ScreenerCriterionOperator.GTE, 2, "Relative volume at least 2x"))
    if "52-week" in lowered or "52 week" in lowered:
        unsupported.append("52-week high/low templates require a longer high/low registry field; using liquid momentum proxy.")
    if "earnings" in lowered:
        unsupported.append("Earnings-window filters are not available in the Alpaca-first provider pack yet.")
    if "premarket" in lowered:
        assumptions.append("Premarket intent is interpreted as a market-list/template start; session-specific gap fields need provider session evidence.")

    if not children:
        children = list(template.expression.children)
    expression = ScreenerExpression(kind=ScreenerExpressionKind.ALL, children=tuple(children))

    return ScreenerAIInterpretResponse(
        suggested_template_keys=(template.key,),
        universe_source=universe_source,
        expression=expression,
        assumptions=tuple(dict.fromkeys(assumptions)),
        unsupported_clauses=tuple(dict.fromkeys(unsupported)),
        audit_preview={
            "prompt": prompt,
            "operator_session_id": request.operator_session_id,
            "mutation": "none",
            "compiled_to": "typed_screener_expression",
        },
    )


def _template_for_prompt(prompt: str) -> str:
    if "most active" in prompt:
        return "most_active"
    if "loser" in prompt or "gap down" in prompt:
        return "day_losers"
    if "shortable" in prompt or "fade" in prompt:
        return "shortable_fade_candidates"
    if "fractionable" in prompt:
        return "fractionable_momentum"
    if "relative volume" in prompt or "rvol" in prompt:
        return "high_relative_volume"
    return "day_gainers"


def _criterion(metric: ScreenerMetric, expected: bool, label: str) -> ScreenerExpression:
    return ScreenerExpression(
        kind=ScreenerExpressionKind.CRITERION,
        criterion=ScreenerCriterion(
            metric=metric,
            operator=ScreenerCriterionOperator.EQ,
            value=expected,
            label=label,
        ),
    )


def _numeric(
    metric: ScreenerMetric,
    operator: ScreenerCriterionOperator,
    value: float,
    label: str,
) -> ScreenerExpression:
    return ScreenerExpression(
        kind=ScreenerExpressionKind.CRITERION,
        criterion=ScreenerCriterion(metric=metric, operator=operator, value=value, label=label),
    )

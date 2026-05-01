"""Validate that every entry expression in the frontend starter strategies
parses and validates cleanly against the v4 expression engine catalog.

The expressions are kept in sync with frontend/src/strategy_ide_v4/starterStrategies.ts.
Any change to starter expressions must keep both files consistent.
"""
from __future__ import annotations

import pytest

from backend.app.strategies.expression_engine import (
    ParseError,
    ValidationError,
    default_catalog,
    parse,
    validate,
)


# ---------------------------------------------------------------------------
# Canonical entry expressions from the 10 starter strategies
# ---------------------------------------------------------------------------

STARTER_EXPRESSIONS: list[tuple[str, str]] = [
    # (strategy_id, expression_text)
    (
        "rsi-mean-reversion",
        "1d.rsi(14) < 30 AND 1d.close > 1d.sma(50)",
    ),
    (
        "low-ibs-bounce",
        "(1d.close - 1d.low) / 1d.range < 0.2 AND 1d.close > 1d.sma(200)",
    ),
    (
        "ema-trend-pullback",
        "1d.ema(20) > 1d.ema(50) AND 1d.close crosses_above 1d.ema(20)",
    ),
    (
        "supertrend-trend-follow-long",
        "1h.close crosses_above 1h.supertrend(10, 3)",
    ),
    (
        "supertrend-trend-follow-short",
        "1h.close crosses_below 1h.supertrend(10, 3)",
    ),
    (
        "donchian-breakout",
        "1d.close > 1d.donchian_high(20)",
    ),
    (
        "vwap-reclaim",
        "5m.close crosses_above 5m.vwap() AND session.minutes_since_open < 90",
    ),
    (
        "orb",
        "5m.close > orb.high(30) AND session.is_open",
    ),
    (
        "macd-cross",
        "1h.macd_line(12, 26, 9) crosses_above 1h.macd_signal(12, 26, 9) AND 1h.close > 1h.ema(50)",
    ),
    (
        "bb-breakout",
        "1d.close > 1d.bb_upper(20, 2) AND 1d.bb_width(20, 2) > 0.02",
    ),
    (
        "prior-day-high-breakout",
        "5m.close > prior_day.high AND 5m.rvol(20) > 1.5 AND session.minutes_since_open < 120",
    ),
]


@pytest.mark.parametrize("strategy_id,expression", STARTER_EXPRESSIONS, ids=[x[0] for x in STARTER_EXPRESSIONS])
def test_starter_expression_parses_and_validates(strategy_id: str, expression: str) -> None:
    """Each starter expression must parse without error and validate against the default catalog."""
    catalog = default_catalog()

    try:
        ast = parse(expression)
    except ParseError as exc:
        pytest.fail(f"[{strategy_id}] ParseError: {exc}")

    try:
        validate(ast, catalog)
    except ValidationError as exc:
        pytest.fail(f"[{strategy_id}] ValidationError: {exc}")

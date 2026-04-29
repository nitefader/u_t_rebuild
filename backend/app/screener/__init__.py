"""Screener — versioned, criteria-driven symbol discovery.

A Screener is a saved set of criteria (price range, average volume, RSI,
gap%, relative volume, etc.) that runs against a Universe Source
(an existing Watchlist, an explicit symbol list, or a built-in preset)
and returns a ranked set of matching symbols.

Doctrine guards (per Nanyel's standard in ``AGENTS.md``):

- The Screener is a **discovery / research surface**. It NEVER deploys a
  Strategy, attaches an Account, submits a broker order, or claims live
  readiness. Its only outputs are saved screener configs and immutable
  ``ScreenerRun`` records.
- It does NOT own broker truth. Every metric pulled from Alpaca / market
  data flows through the existing ``HistoricalBarIngestService`` cache so
  the cache-hit invariant holds for the same symbol/timeframe/window.
- It does NOT mutate Watchlists. The "save matched symbols as a
  Watchlist" action POSTs to the existing ``WatchlistService`` like any
  other operator action — Screener writes nothing into the Watchlist
  store directly.
- Strategy → Deployment → Account ownership is unchanged: a Screener
  result can be USED by a Strategy's Universe selection but never
  embedded inside a Strategy.
"""

from .domain import (
    Screener,
    ScreenerCriterion,
    ScreenerCriterionOperator,
    ScreenerExpression,
    ScreenerExpressionKind,
    ScreenerMetric,
    ScreenerResultRow,
    ScreenerRun,
    ScreenerRunStatus,
    ScreenerUniverseSource,
    ScreenerUniverseSourceKind,
    ScreenerVersion,
)
from .service import (
    ScreenerExecutionService,
    ScreenerNotFoundError,
    ScreenerSourceError,
    ScreenerValidationError,
)
from .store import ScreenerStore

__all__ = [
    "Screener",
    "ScreenerCriterion",
    "ScreenerCriterionOperator",
    "ScreenerExpression",
    "ScreenerExpressionKind",
    "ScreenerExecutionService",
    "ScreenerMetric",
    "ScreenerNotFoundError",
    "ScreenerResultRow",
    "ScreenerRun",
    "ScreenerRunStatus",
    "ScreenerSourceError",
    "ScreenerStore",
    "ScreenerUniverseSource",
    "ScreenerUniverseSourceKind",
    "ScreenerValidationError",
    "ScreenerVersion",
]

/**
 * Canonical timeframe strings — must stay aligned with backend
 * CANONICAL_TIMEFRAMES_ORDER (expression_engine.timeframes).
 */
export const CANONICAL_TIMEFRAMES = [
  "1m",
  "5m",
  "15m",
  "30m",
  "1h",
  "4h",
  "1d",
] as const;

export type CanonicalTimeframe = (typeof CANONICAL_TIMEFRAMES)[number];

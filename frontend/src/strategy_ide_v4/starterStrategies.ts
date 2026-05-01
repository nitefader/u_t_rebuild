/**
 * starterStrategies — curated registry of 10 archetype StrategyVersionV4Draft shapes.
 *
 * Each entry ships with:
 *   - edge_type / best_on / why_it_works — "About this strategy" block
 *   - tags (horizon, direction, timeframe, regime, hold)
 *   - details (7 keys: entry, stop, target, runner, logical_exit, time_constraints, risk_sizing)
 *   - draft — a valid StrategyVersionV4Draft; every entry expression uses only
 *     features present in the v4 catalog
 *   - suggested_controls / suggested_execution_plan — operator hints
 */

import type { StrategyVersionV4Draft } from "@/api/schemas/strategiesV4";

type HorizonTag = "scalping" | "intraday" | "swing" | "position";
type DirectionTag = "long" | "short" | "both";

export interface StarterStrategyTags {
  horizon: HorizonTag;
  direction: DirectionTag;
  timeframe: string;
  regime: string;
  hold: string;
}

export interface StarterStrategyDetails {
  entry: string;
  stop: string;
  target: string;
  runner: string;
  logical_exit: string;
  time_constraints: string;
  risk_sizing: string;
}

export interface StarterStrategy {
  id: string;
  name: string;
  description: string;
  edge_type: string;
  best_on: string;
  why_it_works: string;
  tags: StarterStrategyTags;
  details: StarterStrategyDetails;
  draft: StrategyVersionV4Draft;
  suggested_controls: string;
  suggested_execution_plan: string;
}

function uid(): string {
  return crypto.randomUUID();
}

export const STARTER_STRATEGIES: StarterStrategy[] = [
  // 1 — RSI Mean Reversion
  {
    id: "rsi-mean-reversion",
    name: "RSI Mean Reversion",
    description: "Long when RSI(14) < 30 in an uptrend confirmed by SMA(50). Targets 2R.",
    edge_type: "Mean reversion",
    best_on: "Liquid ETFs and large-cap equities on daily bars",
    why_it_works:
      "Temporary oversold readings in an established uptrend historically resolve to the upside as short sellers cover and buyers re-enter near value.",
    tags: { horizon: "swing", direction: "long", timeframe: "1d", regime: "range", hold: "2–5 days" },
    details: {
      entry: "RSI(14) < 30 AND close > SMA(50) — daily oversold in an uptrend",
      stop: "2% below entry",
      target: "4% above entry (2R)",
      runner: "None — full exit at first target",
      logical_exit: "RSI crosses above 50 before target is reached",
      time_constraints: "Regular session only; avoid earnings days",
      risk_sizing: "1–2% of account per trade; reduce size in high-volatility regimes",
    },
    draft: {
      name: "RSI Mean Reversion",
      description: "Long when RSI(14) < 30 in an uptrend (close > SMA(50)).",
      identity: { tags: ["swing", "mean-reversion"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: { expression_text: "1d.rsi(14) < 30 AND 1d.close > 1d.sma(50)" },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "%", simple_value: 2.0 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "target",
          size_pct: 1.0,
          target_type: "%",
          target_value: 4.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "opposite_cross", params: {} }],
        short: [],
      },
    },
    suggested_controls:
      "Timeframe: 1d. Session: regular only. Disable power-hour trading. Day restrictions: avoid Monday entries.",
    suggested_execution_plan:
      "Market entry. Day order. No bracket — single-leg exit at target.",
  },

  // 2 — Low IBS Bounce  (IBS = (close - low) / range; replaces old ibs() call)
  {
    id: "low-ibs-bounce",
    name: "Low IBS Bounce",
    description:
      "Long when price closes near the day's low (IBS proxy < 0.2) and above SMA(200).",
    edge_type: "Mean reversion",
    best_on: "S&P 500 stocks and index ETFs on daily bars",
    why_it_works:
      "A close near the low of the day signals intraday selling exhaustion. In a structural uptrend the selling pressure typically reverses the next session.",
    tags: { horizon: "swing", direction: "long", timeframe: "1d", regime: "range", hold: "1–3 days" },
    details: {
      entry: "(close - low) / range < 0.2 AND close > SMA(200) — closed near low in uptrend",
      stop: "1.5% below entry",
      target: "3% above entry",
      runner: "None — full exit at target",
      logical_exit: "Price closes above prior-day high before target",
      time_constraints: "Regular session only; skip during earnings blackout",
      risk_sizing: "1% of account; position count cap of 3 concurrent",
    },
    draft: {
      name: "Low IBS Bounce",
      description:
        "Long when price closes near the day's low (IBS proxy < 0.2) and above SMA(200).",
      identity: { tags: ["swing", "mean-reversion", "ibs-proxy"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: {
          expression_text:
            "(1d.close - 1d.low) / 1d.range < 0.2 AND 1d.close > 1d.sma(200)",
        },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "%", simple_value: 1.5 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "target",
          size_pct: 1.0,
          target_type: "%",
          target_value: 3.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: { long: [], short: [] },
    },
    suggested_controls:
      "Timeframe: 1d. Max 3 concurrent positions. Earnings blackout enabled.",
    suggested_execution_plan: "Market entry at next open. Day order. No bracket.",
  },

  // 3 — EMA Trend Pullback
  {
    id: "ema-trend-pullback",
    name: "EMA Trend Pullback",
    description:
      "Long when EMA(20) > EMA(50) and price crosses back above EMA(20) after a pullback.",
    edge_type: "Trend following with mean-reversion entry timing",
    best_on: "Trending equities and sector ETFs on daily or 1h bars",
    why_it_works:
      "Fast-above-slow EMA confirms a trending regime. Entering on the pullback to EMA(20) provides better risk/reward than chasing breakouts.",
    tags: { horizon: "swing", direction: "long", timeframe: "1d", regime: "trend", hold: "3–10 days" },
    details: {
      entry: "EMA(20) > EMA(50) AND close crosses above EMA(20)",
      stop: "1.5× ATR(14) below entry",
      target: "3× ATR(14) above entry (partial)",
      runner: "50% rides with trailing ATR(2) stop after first target",
      logical_exit: "Close below EMA(20) for second consecutive bar",
      time_constraints: "No restriction; works across sessions",
      risk_sizing: "1–2% per trade; scale to 2% when ADX confirms strong trend",
    },
    draft: {
      name: "EMA Trend Pullback",
      description: "Long when EMA(20) > EMA(50) and price crosses back above EMA(20).",
      identity: { tags: ["swing", "trend", "pullback"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: {
          expression_text:
            "1d.ema(20) > 1d.ema(50) AND 1d.close crosses_above 1d.ema(20)",
        },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "ATR", simple_value: 1.5 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "target",
          size_pct: 0.5,
          target_type: "ATR",
          target_value: 3.0,
          on_fill_action: { kind: "be_exact" },
        },
        {
          id: uid(),
          position: 2,
          kind: "runner",
          size_pct: 0.5,
          target_type: "trail-ATR",
          target_value: 2.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "opposite_cross", params: {} }],
        short: [],
      },
    },
    suggested_controls:
      "Timeframe: 1d. Allowed directions: long. No day-of-week restrictions.",
    suggested_execution_plan:
      "Market entry. Day order. Post-fill bracket with runner leg.",
  },

  // 4 — Supertrend Trend Follow (both directions)
  {
    id: "supertrend-trend-follow",
    name: "Supertrend Trend Follow",
    description:
      "Long when close crosses above Supertrend(10, 3); short when close crosses below it.",
    edge_type: "Trend following",
    best_on: "Liquid index futures, ETFs, and high-beta equities on 1h charts",
    why_it_works:
      "Supertrend adapts the trailing stop to volatility (ATR). Flip signals align entry with the dominant trend while automatically managing risk.",
    tags: { horizon: "swing", direction: "both", timeframe: "1h", regime: "trend", hold: "hours–days" },
    details: {
      entry: "Close crosses above Supertrend(10, 3) for long; crosses below for short",
      stop: "1× ATR(14) initial stop",
      target: "No fixed target — full position runs as runner",
      runner: "100% rides with Supertrend level as proxy trailing stop",
      logical_exit: "Opposite direction cross signal fires",
      time_constraints: "Regular session; avoid last 30 min before close",
      risk_sizing: "1% per trade; do not hold both sides simultaneously",
    },
    draft: {
      name: "Supertrend Trend Follow",
      description: "Long on Supertrend up-cross; short on Supertrend down-cross.",
      identity: { tags: ["swing", "trend", "supertrend"], direction: "both" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: { expression_text: "1h.close crosses_above 1h.supertrend(10, 3)" },
        short: { expression_text: "1h.close crosses_below 1h.supertrend(10, 3)" },
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "ATR", simple_value: 1.0 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "runner",
          size_pct: 1.0,
          target_type: "trail-ATR",
          target_value: 1.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "opposite_cross", params: {} }],
        short: [{ id: uid(), template_id: "opposite_cross", params: {} }],
      },
    },
    suggested_controls:
      "Timeframe: 1h. Allowed directions: both. Skip power hour.",
    suggested_execution_plan:
      "Market entry. Day order. Runner leg with trailing ATR stop.",
  },

  // 5 — Donchian Channel Breakout
  {
    id: "donchian-breakout",
    name: "Donchian Channel Breakout",
    description: "Long when close exceeds the 20-bar Donchian high. Ride with trailing stop.",
    edge_type: "Breakout / trend following",
    best_on: "Commodity ETFs, sector rotators, and trend-persistent equities on daily bars",
    why_it_works:
      "A new 20-bar high indicates price has broken out of a consolidation range. The Turtle Trading research showed these breakouts have positive expectancy when exits are managed with trailing stops.",
    tags: { horizon: "position", direction: "long", timeframe: "1d", regime: "trend", hold: "weeks" },
    details: {
      entry: "Close > Donchian high(20) — new 20-bar high close",
      stop: "3% below entry",
      target: "No fixed target",
      runner: "Full position trails at 3% trailing stop",
      logical_exit: "Close below Donchian low(10)",
      time_constraints: "No specific session constraints; position-trade timeframe",
      risk_sizing: "0.5–1% per trade; allow 5+ concurrent positions",
    },
    draft: {
      name: "Donchian Breakout",
      description: "Long when close > 20-bar Donchian channel high.",
      identity: { tags: ["position", "breakout", "donchian"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: { expression_text: "1d.close > 1d.donchian_high(20)" },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "%", simple_value: 3.0 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "runner",
          size_pct: 1.0,
          target_type: "trail-%",
          target_value: 3.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "opposite_cross", params: {} }],
        short: [],
      },
    },
    suggested_controls:
      "Timeframe: 1d. Trading horizon: position. Max consecutive losses halt: 4.",
    suggested_execution_plan:
      "Market entry. Day order. Scale-out disabled — runner exit only.",
  },

  // 6 — VWAP Reclaim (intraday)
  {
    id: "vwap-reclaim",
    name: "VWAP Reclaim",
    description:
      "Intraday long when price reclaims VWAP from below. Partial exit at 2×ATR; runner trails.",
    edge_type: "Intraday mean reversion + momentum",
    best_on: "High-volume equities and ETFs (SPY, QQQ, AAPL) on 5m bars in the morning session",
    why_it_works:
      "VWAP acts as the intraday fair-value anchor. Reclaims after brief dips indicate that sellers have been absorbed and institutional buyers are still active.",
    tags: { horizon: "intraday", direction: "long", timeframe: "5m", regime: "trend", hold: "30–120 min" },
    details: {
      entry: "5m close crosses above VWAP AND session open < 90 min ago",
      stop: "1× ATR(14) below VWAP at entry",
      target: "60% exits at 2× ATR(14)",
      runner: "40% trails with 1× ATR trailing stop",
      logical_exit: "Session end or close falls back below VWAP",
      time_constraints: "Enter only in first 90 minutes after session open",
      risk_sizing: "0.5–1% per trade; max 2 concurrent intraday positions",
    },
    draft: {
      name: "VWAP Reclaim",
      description: "Long when price crosses above VWAP in the morning session.",
      identity: { tags: ["intraday", "vwap", "reclaim"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: {
          expression_text:
            "5m.close crosses_above 5m.vwap() AND session.minutes_since_open < 90",
        },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "ATR", simple_value: 1.0 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "target",
          size_pct: 0.6,
          target_type: "ATR",
          target_value: 2.0,
          on_fill_action: { kind: "be_exact" },
        },
        {
          id: uid(),
          position: 2,
          kind: "runner",
          size_pct: 0.4,
          target_type: "trail-ATR",
          target_value: 1.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "session_end", params: {} }],
        short: [],
      },
    },
    suggested_controls:
      "Timeframe: 5m. Session: regular only. Skip power hour. Max 2 concurrent.",
    suggested_execution_plan:
      "Market entry. Day order. Post-fill bracket with runner leg.",
  },

  // 7 — Opening Range Breakout (ORB)
  {
    id: "orb",
    name: "Opening Range Breakout",
    description: "Long on break above the first 30-min opening range high.",
    edge_type: "Intraday momentum / breakout",
    best_on: "High-relative-volume days on QQQ, SPY, AAPL, TSLA — 5m bars",
    why_it_works:
      "The opening range captures early price discovery. A decisive break above the range high indicates institutional order flow continuation and often leads to sustained intraday trends.",
    tags: { horizon: "intraday", direction: "long", timeframe: "5m", regime: "trend", hold: "1–4 hours" },
    details: {
      entry: "5m close > ORB high(30) AND session is open",
      stop: "Below ORB low(30) or 1% hard stop",
      target: "50% exits at 2R",
      runner: "50% trails with 0.5% trailing stop",
      logical_exit: "Session end or price re-enters the opening range",
      time_constraints: "Enter only between 10:00 AM and 12:00 PM ET",
      risk_sizing: "1% per trade; only trade when ORB bar rvol > 1.5",
    },
    draft: {
      name: "Opening Range Breakout",
      description: "Long on break above first 30-min opening range high.",
      identity: { tags: ["intraday", "breakout", "orb"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: {
          expression_text:
            "5m.close > orb.high(30) AND session.is_open",
        },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "%", simple_value: 1.0 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "target",
          size_pct: 0.5,
          target_type: "R",
          target_value: 2.0,
          on_fill_action: { kind: "be_exact" },
        },
        {
          id: uid(),
          position: 2,
          kind: "runner",
          size_pct: 0.5,
          target_type: "trail-%",
          target_value: 0.5,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "session_end", params: {} }],
        short: [],
      },
    },
    suggested_controls:
      "Timeframe: 5m. Session: regular only. Session window: 10:00–12:00. Skip power hour.",
    suggested_execution_plan:
      "Market entry. Day order. Post-fill bracket with runner leg.",
  },

  // 8 — MACD Cross with Trend Filter
  {
    id: "macd-cross",
    name: "MACD Cross Momentum",
    description: "Long when MACD line crosses above signal while price is above EMA(50).",
    edge_type: "Momentum confirmation",
    best_on: "Trending equities and sector ETFs on 1h or daily bars",
    why_it_works:
      "MACD crossovers confirm that short-term momentum has shifted in the direction of the prevailing trend. The EMA(50) filter removes most counter-trend fakeouts.",
    tags: { horizon: "swing", direction: "long", timeframe: "1h", regime: "trend", hold: "1–5 days" },
    details: {
      entry: "MACD line(12,26,9) crosses above MACD signal(12,26,9) AND close > EMA(50)",
      stop: "2× ATR(14) below entry",
      target: "3× ATR(14) above entry",
      runner: "None — full exit at target",
      logical_exit: "MACD histogram crosses below zero",
      time_constraints: "No specific constraints on 1h bars; avoid late Friday entries",
      risk_sizing: "1% per trade; max 4 concurrent swing positions",
    },
    draft: {
      name: "MACD Cross Momentum",
      description: "Long when MACD line crosses above signal and price is above EMA(50).",
      identity: { tags: ["swing", "momentum", "macd"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: {
          expression_text:
            "1h.macd_line(12, 26, 9) crosses_above 1h.macd_signal(12, 26, 9) AND 1h.close > 1h.ema(50)",
        },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "ATR", simple_value: 2.0 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "target",
          size_pct: 1.0,
          target_type: "ATR",
          target_value: 3.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "opposite_cross", params: {} }],
        short: [],
      },
    },
    suggested_controls:
      "Timeframe: 1h. Day restrictions: skip Monday. Max 4 concurrent positions.",
    suggested_execution_plan:
      "Market entry. Day order. Single-leg exit at 3R target.",
  },

  // 9 — Bollinger Band Breakout
  {
    id: "bb-breakout",
    name: "Bollinger Band Breakout",
    description:
      "Long when price closes above the upper Bollinger Band with expanding width, signaling a volatility breakout.",
    edge_type: "Volatility breakout",
    best_on: "Momentum equities and ETFs on daily bars; post-consolidation setups",
    why_it_works:
      "Price closing above the upper BB in a widening band environment signals a genuine volatility expansion, not a squeeze retest. These moves tend to continue in the direction of the breakout.",
    tags: { horizon: "swing", direction: "long", timeframe: "1d", regime: "range-to-trend", hold: "3–15 days" },
    details: {
      entry: "Close > BB upper(20, 2) AND BB width(20, 2) > BB width(20, 2) shifted 1 bar",
      stop: "2% below entry",
      target: "5% above entry",
      runner: "None — full exit at target",
      logical_exit: "Close back below BB middle(20) band",
      time_constraints: "No time constraints; daily timeframe",
      risk_sizing: "1–2% per trade; scale up when rvol > 2",
    },
    draft: {
      name: "Bollinger Band Breakout",
      description: "Long when close > BB upper band with expanding band width.",
      identity: { tags: ["swing", "volatility", "bollinger"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: {
          expression_text:
            "1d.close > 1d.bb_upper(20, 2) AND 1d.bb_width(20, 2) > 0.02",
        },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "%", simple_value: 2.0 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "target",
          size_pct: 1.0,
          target_type: "%",
          target_value: 5.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "opposite_cross", params: {} }],
        short: [],
      },
    },
    suggested_controls:
      "Timeframe: 1d. Earnings blackout enabled. Max 5 concurrent swing positions.",
    suggested_execution_plan:
      "Market entry at open. Day order. Single-leg exit at 5% target.",
  },

  // 10 — Prior Day High Breakout
  {
    id: "prior-day-high-breakout",
    name: "Prior Day High Breakout",
    description:
      "Intraday long when 5m price closes above the prior session high with elevated relative volume.",
    edge_type: "Intraday breakout / continuation",
    best_on: "High-momentum equities gapping up or trending strongly — 5m bars",
    why_it_works:
      "The prior day high is a widely-watched resistance level. A clean breakout above it with volume confirmation signals that sellers at that level have been absorbed, often triggering continuation buying.",
    tags: { horizon: "intraday", direction: "long", timeframe: "5m", regime: "trend", hold: "1–3 hours" },
    details: {
      entry: "5m close > prior_day.high AND rvol(20) > 1.5",
      stop: "1× ATR(14) below entry",
      target: "2× ATR(14) above entry (partial)",
      runner: "50% trails at 1× ATR after first target fills",
      logical_exit: "Session end or close falls below prior_day.high",
      time_constraints: "Enter only in first 2 hours of regular session",
      risk_sizing: "1% per trade; max 2 concurrent intraday positions",
    },
    draft: {
      name: "Prior Day High Breakout",
      description: "Long when 5m close > prior day high with elevated relative volume.",
      identity: { tags: ["intraday", "breakout", "prior-day"], direction: "long" },
      timeframe_aliases: {},
      variables: [],
      entries: {
        long: {
          expression_text:
            "5m.close > prior_day.high AND 5m.rvol(20) > 1.5 AND session.minutes_since_open < 120",
        },
        short: null,
      },
      stops: [
        { id: uid(), mode: "simple", scope: "all", simple_type: "ATR", simple_value: 1.0 },
      ],
      legs: [
        {
          id: uid(),
          position: 1,
          kind: "target",
          size_pct: 0.5,
          target_type: "ATR",
          target_value: 2.0,
          on_fill_action: { kind: "be_exact" },
        },
        {
          id: uid(),
          position: 2,
          kind: "runner",
          size_pct: 0.5,
          target_type: "trail-ATR",
          target_value: 1.0,
          on_fill_action: { kind: "be_exact" },
        },
      ],
      logical_exits: {
        long: [{ id: uid(), template_id: "session_end", params: {} }],
        short: [],
      },
    },
    suggested_controls:
      "Timeframe: 5m. Session: regular only. Skip power hour. Max 2 concurrent intraday.",
    suggested_execution_plan:
      "Market entry. Day order. Post-fill bracket with runner leg.",
  },
];

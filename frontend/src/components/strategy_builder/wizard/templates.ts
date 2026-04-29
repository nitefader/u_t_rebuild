import type { WizardIntent } from "@/api/schemas/strategyComposer";

/**
 * Curated starter strategy templates surfaced in the Page-1 wizard side panel.
 *
 * Provenance is QUALITATIVE only in this slice — there is no unified backtest
 * fixture pipeline, so we never display Sharpe / drawdown / annualized return.
 * Templates carry `regime_assumption`, `expected_hold_time`, `known_behavior`,
 * `caveats`, and an explicit `indicative_only_disclaimer`.
 *
 * SESSION-dependent templates (`requires_session_execution = true`) render in
 * a separate "Awaiting backend update" lane with Generate disabled — the
 * canonical engine does not yet execute SESSION-scope features (Slice 6a-ii).
 */

export type TemplateRegime =
  | "ranging"
  | "trending"
  | "high_vol"
  | "regime_agnostic";

export type TemplateHoldTime = "minutes" | "hours" | "days" | "weeks";

export type StarterTemplate = {
  id: string;
  display_name: string;
  short_description: string;
  long_description: string;
  intended_horizon: WizardIntent["horizon"];
  default_direction: WizardIntent["direction"];
  default_base_timeframe: string;
  regime_assumption: TemplateRegime;
  expected_hold_time: TemplateHoldTime;
  known_behavior: string;
  caveats: string;
  indicative_only_disclaimer: boolean;
  required_feature_families: string[];
  feature_seeds: string[];
  wizard_intent_seed: WizardIntent;
  prompt_seed: string;
  entry_logic_plain_english: string;
  stop_logic_plain_english: string;
  target_logic_plain_english: string;
  logical_exit_logic_plain_english: string;
  intent_keywords: string[];
  requires_session_execution: boolean;
  deferred_reason: string | null;
};

const DEFER_SESSION_REASON =
  "Requires SESSION execution (coming in Slice 6a-ii). You can preview, but Generate is disabled until the backend ships SESSION-scope feature execution.";

export const STARTER_TEMPLATES: readonly StarterTemplate[] = [
  {
    id: "vwap-reclaim",
    display_name: "VWAP Reclaim",
    short_description:
      "Long when price reclaims VWAP after a session-low touch.",
    long_description:
      "Trend-day entry. Wait for price to dip below VWAP and tag a new session low, then enter long when price closes back above VWAP. Exits on VWAP loss or by 15:55 ET.",
    intended_horizon: "intraday",
    default_direction: "long",
    default_base_timeframe: "5m",
    regime_assumption: "trending",
    expected_hold_time: "hours",
    known_behavior:
      "Best on liquid names with clean VWAP respect. Suffers in choppy non-trending sessions.",
    caveats:
      "Bad in chop. Avoid first 15 minutes (bid/ask noise). Confirm with volume on reclaim bar.",
    indicative_only_disclaimer: true,
    required_feature_families: ["VWAP", "close"],
    feature_seeds: ["5m.vwap:session=regular[0]", "5m.close[0]"],
    wizard_intent_seed: {
      direction: "long",
      horizon: "intraday",
      base_timeframe: "5m",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: true,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: true,
    },
    prompt_seed:
      "Long when 5m close crosses above VWAP after a session-low touch. Stop below the session low. Target VWAP plus 1× ATR(14). Exit on VWAP loss or by 15:55 ET.",
    entry_logic_plain_english:
      "Long when close crosses above VWAP after touching the session low.",
    stop_logic_plain_english: "Stop below the session low.",
    target_logic_plain_english: "Target = VWAP + 1× ATR(14).",
    logical_exit_logic_plain_english:
      "Flat by 15:55 ET, or exit on VWAP loss after entry.",
    intent_keywords: ["VWAP", "reclaim", "intraday", "session"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  {
    id: "supertrend-trend-follow",
    display_name: "Supertrend Trend Follow",
    short_description:
      "Both directions. Long on Supertrend up-flip; short on down-flip.",
    long_description:
      "Classic ATR-based trend follower. Enter long when Supertrend(10, 3) flips up; short when it flips down. Trail with 1× ATR(14). Exit on opposite flip.",
    intended_horizon: "swing",
    default_direction: "both",
    default_base_timeframe: "1h",
    regime_assumption: "trending",
    expected_hold_time: "days",
    known_behavior:
      "Captures sustained trends; whipsaws painfully in low-volatility ranging regimes.",
    caveats:
      "Use only on names with clear trend regimes. Pair with a regime filter (e.g., ATR percentile) before live deployment.",
    indicative_only_disclaimer: true,
    required_feature_families: ["supertrend", "ATR", "close"],
    feature_seeds: [
      "1h.supertrend:length=10,multiplier=3.0[0]",
      "1h.atr:length=14[0]",
      "1h.close[0]",
    ],
    wizard_intent_seed: {
      direction: "both",
      horizon: "swing",
      base_timeframe: "1h",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: false,
      has_multiple_targets: false,
      has_runner: true,
      has_logical_exit: true,
      has_time_based_exit: false,
    },
    prompt_seed:
      "Long when Supertrend(10,3) flips up; short when it flips down. Trail with 1× ATR(14). Exit on opposite flip.",
    entry_logic_plain_english:
      "Long on Supertrend up-flip; short on down-flip.",
    stop_logic_plain_english: "Trailing 1× ATR(14).",
    target_logic_plain_english:
      "No fixed target — let the runner ride the trend.",
    logical_exit_logic_plain_english: "Exit on opposite Supertrend flip.",
    intent_keywords: ["supertrend", "trend", "ATR", "swing"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  {
    id: "rsi-mean-reversion",
    display_name: "RSI Mean Reversion",
    short_description:
      "Long when RSI(14) < 30 in an uptrend (close > SMA(50)).",
    long_description:
      "Daily mean-reversion long-only. Enter when RSI(14) crosses below 30 while close is still above SMA(50). Exit when RSI(14) > 50 or after 10 bars.",
    intended_horizon: "swing",
    default_direction: "long",
    default_base_timeframe: "1d",
    regime_assumption: "ranging",
    expected_hold_time: "days",
    known_behavior:
      "Works in ranging regimes inside larger uptrends. Fails when the SMA(50) trend rolls over.",
    caveats:
      "Mean-reversion only works in non-trending regimes — consider adding a regime filter. 5% stop can be wide on volatile names.",
    indicative_only_disclaimer: true,
    required_feature_families: ["RSI", "SMA", "close"],
    feature_seeds: [
      "1d.rsi:length=14[0]",
      "1d.sma:length=50[0]",
      "1d.close[0]",
    ],
    wizard_intent_seed: {
      direction: "long",
      horizon: "swing",
      base_timeframe: "1d",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: false,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: true,
    },
    prompt_seed:
      "Long when RSI(14) < 30 and close > SMA(50). Stop 5% below entry. Exit when RSI(14) > 50 or after 10 bars.",
    entry_logic_plain_english:
      "Long when RSI(14) < 30 and close > SMA(50).",
    stop_logic_plain_english: "5% below entry.",
    target_logic_plain_english:
      "No fixed price target — relies on RSI exit.",
    logical_exit_logic_plain_english:
      "Exit when RSI(14) > 50, or after 10 bars in position.",
    intent_keywords: ["RSI", "mean_reversion", "SMA", "swing"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  {
    id: "connors-rsi-2",
    display_name: "Connors RSI-2",
    short_description:
      "Long-only daily mean-reversion using RSI(2) and a down-streak filter.",
    long_description:
      "Larry Connors' published mean-reversion strategy. Long when RSI(2) < 10 and price has closed down 2+ bars in a row, with close > SMA(200) (long-term uptrend filter). Exit when RSI(2) > 70.",
    intended_horizon: "swing",
    default_direction: "long",
    default_base_timeframe: "1d",
    regime_assumption: "ranging",
    expected_hold_time: "days",
    known_behavior:
      "Well-published mean-reversion strategy. Trades infrequently, holds 2-5 bars. Works on liquid large caps and broad-market ETFs.",
    caveats:
      "Whipsaws on low-volume names. Avoid news-driven gaps. Optional 7% stop is a hard safety net only — not a primary exit.",
    indicative_only_disclaimer: true,
    required_feature_families: ["RSI", "down_streak", "SMA"],
    feature_seeds: [
      "1d.rsi:length=2[0]",
      "1d.down_streak[0]",
      "1d.sma:length=200[0]",
      "1d.close[0]",
    ],
    wizard_intent_seed: {
      direction: "long",
      horizon: "swing",
      base_timeframe: "1d",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: false,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: true,
    },
    prompt_seed:
      "Long when daily RSI(2) < 10 and down_streak >= 2 and close > SMA(200). Optional 7% stop. Exit when RSI(2) > 70 or after 10 bars.",
    entry_logic_plain_english:
      "Long when RSI(2) < 10 and price has closed down 2+ bars and close > SMA(200).",
    stop_logic_plain_english: "Optional 7% below entry (hard safety net).",
    target_logic_plain_english:
      "No fixed price target — RSI(2) > 70 is the exit signal.",
    logical_exit_logic_plain_english:
      "Exit when RSI(2) > 70, or after 10 bars in position.",
    intent_keywords: ["RSI", "connors", "mean_reversion", "down_streak", "swing"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  {
    id: "internal-bar-strength",
    display_name: "Internal Bar Strength (IBS)",
    short_description: "Long when IBS < 0.2 in an uptrend (close > SMA(200)).",
    long_description:
      "ETF-style mean-reversion. IBS = (close - low) / (high - low) — measures where close sits inside the bar's range. Low IBS = close near low = exhaustion. Pair with SMA(200) trend filter.",
    intended_horizon: "swing",
    default_direction: "long",
    default_base_timeframe: "1d",
    regime_assumption: "ranging",
    expected_hold_time: "days",
    known_behavior:
      "Works well on broad-market ETFs (SPY, QQQ, IWM). Less reliable on individual names. Holds 1-5 bars.",
    caveats:
      "Best on instruments with predictable mean-reversion behavior. Avoid news catalysts.",
    indicative_only_disclaimer: true,
    required_feature_families: ["IBS", "SMA", "close"],
    feature_seeds: [
      "1d.ibs[0]",
      "1d.sma:length=200[0]",
      "1d.close[0]",
    ],
    wizard_intent_seed: {
      direction: "long",
      horizon: "swing",
      base_timeframe: "1d",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: false,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: true,
    },
    prompt_seed:
      "Long when daily IBS < 0.2 and close > SMA(200). Stop 3% below entry. Exit when IBS > 0.8 or after 5 bars.",
    entry_logic_plain_english:
      "Long when IBS < 0.2 and close > SMA(200).",
    stop_logic_plain_english: "3% below entry.",
    target_logic_plain_english:
      "No fixed price target — IBS > 0.8 is the exit signal.",
    logical_exit_logic_plain_english:
      "Exit when IBS > 0.8, or after 5 bars in position.",
    intent_keywords: ["IBS", "mean_reversion", "SMA", "swing"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  {
    id: "ichimoku-cloud-trend",
    display_name: "Ichimoku Cloud Trend",
    short_description:
      "Both directions. Long above the cloud with Tenkan > Kijun; short symmetric.",
    long_description:
      "Classic Ichimoku trend follower. Long when close is above the cloud, Tenkan-sen > Kijun-sen, and Chikou is bullish. Short symmetric. Stops on Kijun cross.",
    intended_horizon: "swing",
    default_direction: "both",
    default_base_timeframe: "1d",
    regime_assumption: "trending",
    expected_hold_time: "days",
    known_behavior:
      "Strong on persistent trends. Many overlapping rules — easy to over-fit if you tune parameters per symbol.",
    caveats:
      "Senkou A/B in this build do NOT include the +26 forward displacement (Slice 6a-i ships the cloud-edge basis only — known limitation, not a silent approximation; full displacement is a follow-up).",
    indicative_only_disclaimer: true,
    required_feature_families: [
      "tenkan_sen",
      "kijun_sen",
      "senkou_a",
      "senkou_b",
      "chikou_span",
      "ATR",
      "close",
    ],
    feature_seeds: [
      "1d.tenkan_sen:length=9[0]",
      "1d.kijun_sen:length=26[0]",
      "1d.senkou_a:tenkan_length=9,kijun_length=26[0]",
      "1d.senkou_b:length=52[0]",
      "1d.chikou_span:displacement=26[0]",
      "1d.atr:length=14[0]",
      "1d.close[0]",
    ],
    wizard_intent_seed: {
      direction: "both",
      horizon: "swing",
      base_timeframe: "1d",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: true,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: false,
    },
    prompt_seed:
      "Long when daily close is above cloud, Tenkan > Kijun, Chikou bullish. Short symmetric. Stop below Kijun (long). Target 1.5× ATR(14) above entry. Exit on Tenkan-Kijun cross opposite.",
    entry_logic_plain_english:
      "Long when close above cloud, Tenkan > Kijun, Chikou bullish; short symmetric.",
    stop_logic_plain_english: "Below Kijun-sen (long); above Kijun (short).",
    target_logic_plain_english: "1.5× ATR(14) above entry.",
    logical_exit_logic_plain_english:
      "Tenkan-Kijun cross in opposite direction.",
    intent_keywords: ["ichimoku", "cloud", "trend", "swing"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  {
    id: "moving-average-pullback",
    display_name: "Moving Average Pullback",
    short_description:
      "Long when EMA(20) > EMA(50) and price pulls back to EMA(20).",
    long_description:
      "Trend-continuation pullback. Wait for EMA(20) > EMA(50) (uptrend), then enter long on a pullback to within 0.25× ATR of EMA(20). Stops below EMA(50).",
    intended_horizon: "swing",
    default_direction: "long",
    default_base_timeframe: "1d",
    regime_assumption: "trending",
    expected_hold_time: "days",
    known_behavior:
      "Reliable in established uptrends; fails on early reversals or whipsaw markets.",
    caveats:
      "Needs a confirmed uptrend before entry. Avoid first few bars after EMA(50) crosses.",
    indicative_only_disclaimer: true,
    required_feature_families: ["EMA", "ATR", "close"],
    feature_seeds: [
      "1d.ema:length=20[0]",
      "1d.ema:length=50[0]",
      "1d.atr:length=14[0]",
      "1d.close[0]",
    ],
    wizard_intent_seed: {
      direction: "long",
      horizon: "swing",
      base_timeframe: "1d",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: true,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: false,
    },
    prompt_seed:
      "Long when EMA(20) > EMA(50) and close pulls back within 0.25× ATR(14) of EMA(20). Stop 1× ATR(14) below EMA(50). Target 2× ATR(14) above entry. Exit on close below EMA(50).",
    entry_logic_plain_english:
      "Long when EMA(20) > EMA(50) and close pulls back near EMA(20) (within 0.25× ATR(14)).",
    stop_logic_plain_english: "1× ATR(14) below EMA(50).",
    target_logic_plain_english: "2× ATR(14) above entry.",
    logical_exit_logic_plain_english: "Exit on close below EMA(50).",
    intent_keywords: ["EMA", "pullback", "trend", "swing"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  {
    id: "atr-breakout",
    display_name: "ATR Breakout",
    short_description:
      "Both directions. Break the prior 20-bar high/low with rising ATR.",
    long_description:
      "Volatility-expansion breakout. Long when close > prior 20-bar high and ATR(14) is rising; short symmetric. Stops 1× ATR below entry, target 2× ATR above.",
    intended_horizon: "intraday",
    default_direction: "both",
    default_base_timeframe: "15m",
    regime_assumption: "high_vol",
    expected_hold_time: "hours",
    known_behavior:
      "Captures volatility expansions. Whipsaws in low-volatility regimes.",
    caveats:
      "Needs a volatility filter (rising ATR check). Avoid lunch-hour chop on intraday.",
    indicative_only_disclaimer: true,
    required_feature_families: ["highest", "lowest", "ATR", "close"],
    feature_seeds: [
      "15m.highest:length=20,source=high[0]",
      "15m.lowest:length=20,source=low[0]",
      "15m.atr:length=14[0]",
      "15m.close[0]",
    ],
    wizard_intent_seed: {
      direction: "both",
      horizon: "intraday",
      base_timeframe: "15m",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: true,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: true,
    },
    prompt_seed:
      "Long when 15m close > prior 20-bar high and ATR(14) rising; short symmetric. Stop 1× ATR(14). Target 2× ATR(14). Flat by 15:55 ET.",
    entry_logic_plain_english:
      "Long break of prior 20-bar high with rising ATR; short break of 20-bar low.",
    stop_logic_plain_english: "1× ATR(14) opposite side.",
    target_logic_plain_english: "2× ATR(14).",
    logical_exit_logic_plain_english: "Flat by 15:55 ET.",
    intent_keywords: ["breakout", "ATR", "intraday", "volatility"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  {
    id: "fvg-htf",
    display_name: "FVG + Higher Timeframe Confirmation",
    short_description:
      "Both directions. 5m fair-value-gap with 1h trend confirmation.",
    long_description:
      "Inefficiency-fill strategy. Long on a 5m up-FVG when the 1h trend is up (close > 1h.EMA(200)); short symmetric. Stops beyond the opposite swing, target 2× FVG height.",
    intended_horizon: "intraday",
    default_direction: "both",
    default_base_timeframe: "5m",
    regime_assumption: "high_vol",
    expected_hold_time: "hours",
    known_behavior:
      "FVG heuristics vary by author. This template uses the simple 3-bar imbalance definition. Higher timeframe filter avoids counter-trend trades.",
    caveats:
      "FVG definition is heuristic — multiple valid formulations exist. Treat as a starting point, not gospel.",
    indicative_only_disclaimer: true,
    required_feature_families: [
      "FVG",
      "swing_high",
      "swing_low",
      "EMA",
      "close",
    ],
    feature_seeds: [
      "5m.fvg_up[0]",
      "5m.fvg_down[0]",
      "5m.swing_high:lookback=5[0]",
      "5m.swing_low:lookback=5[0]",
      "1h.ema:length=200[0]",
      "5m.close[0]",
    ],
    wizard_intent_seed: {
      direction: "both",
      horizon: "intraday",
      base_timeframe: "5m",
      higher_timeframe_confirmation: true,
      has_stop: true,
      has_target: true,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: false,
    },
    prompt_seed:
      "Long on 5m fvg_up when 1h close > 1h.EMA(200); short symmetric. Stop beyond opposite swing. Target 2× FVG height. Exit on swing low break (long).",
    entry_logic_plain_english:
      "Long on 5m up-FVG when 1h trend is up; short symmetric on down-FVG with 1h down-trend.",
    stop_logic_plain_english: "Beyond opposite swing high/low.",
    target_logic_plain_english: "2× FVG height.",
    logical_exit_logic_plain_english:
      "Exit on swing low break (long) / swing high break (short).",
    intent_keywords: ["FVG", "intraday", "higher_timeframe", "EMA"],
    requires_session_execution: false,
    deferred_reason: null,
  },
  // ─── Awaiting backend update (Slice 6a-ii) ────────────────────────────────
  {
    id: "opening-range-breakout",
    display_name: "Opening Range Breakout",
    short_description:
      "Both directions. Break the 15-min opening range high/low.",
    long_description:
      "Classic intraday breakout. After the first 15 minutes of regular trading, mark the opening-range high and low. Long on close > ORH; short on close < ORL. Stop on opposite side.",
    intended_horizon: "intraday",
    default_direction: "both",
    default_base_timeframe: "5m",
    regime_assumption: "high_vol",
    expected_hold_time: "hours",
    known_behavior:
      "Reliable on high-volume names with morning catalysts. Choppy in low-volume sessions.",
    caveats:
      "Needs liquid names. Avoid the day after holidays. Volume filter recommended.",
    indicative_only_disclaimer: true,
    required_feature_families: [
      "opening_range",
      "volume",
      "ATR",
      "close",
    ],
    feature_seeds: [
      "5m.opening_range_high:session=regular,window_minutes=15[0]",
      "5m.opening_range_low:session=regular,window_minutes=15[0]",
      "5m.opening_range_complete:session=regular,window_minutes=15[0]",
      "5m.atr:length=14[0]",
      "5m.close[0]",
    ],
    wizard_intent_seed: {
      direction: "both",
      horizon: "intraday",
      base_timeframe: "5m",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: true,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: true,
    },
    prompt_seed:
      "Long when 5m close > opening_range_high after window complete; short symmetric. Stop on opposite side. Target 1× ORB width. Flat by 15:55 ET.",
    entry_logic_plain_english:
      "Long when close > opening_range_high (after window complete); short symmetric.",
    stop_logic_plain_english:
      "Static % below opening_range_low (long); above ORH (short).",
    target_logic_plain_english: "1× ORB width above breakout (long).",
    logical_exit_logic_plain_english: "Flat by 15:55 ET.",
    intent_keywords: ["breakout", "opening_range", "ORB", "intraday", "ATR"],
    requires_session_execution: true,
    deferred_reason: DEFER_SESSION_REASON,
  },
  {
    id: "gap-and-go",
    display_name: "Gap-and-Go / Premarket Gapper",
    short_description:
      "Long when gap > 2% and price holds above session high after open.",
    long_description:
      "Classic gap-continuation. Premarket gap up > 2% off prior close. After the open, long when close > regular_session_high_so_far with sustained volume.",
    intended_horizon: "intraday",
    default_direction: "long",
    default_base_timeframe: "5m",
    regime_assumption: "high_vol",
    expected_hold_time: "hours",
    known_behavior:
      "Catches morning continuation moves on news catalysts. Risky on news-driven names — be ready for fade.",
    caveats:
      "Needs premarket data. Risky on news-driven names. Avoid earnings days unless explicitly trading the gap.",
    indicative_only_disclaimer: true,
    required_feature_families: [
      "gap_pct",
      "prior_day_close",
      "session_high",
      "volume",
    ],
    feature_seeds: [
      "5m.gap_pct[0]",
      "5m.prior_day_close[0]",
      "5m.regular_session_high_so_far[0]",
      "5m.volume[0]",
    ],
    wizard_intent_seed: {
      direction: "long",
      horizon: "intraday",
      base_timeframe: "5m",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: true,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: true,
    },
    prompt_seed:
      "Long when gap_pct > 2% at open and 5m close > regular_session_high_so_far. Stop 1% below entry. Target 1× gap-size above entry. Flat by 11:30 ET if no follow-through.",
    entry_logic_plain_english:
      "Long when gap_pct > 2% at open and close > regular_session_high_so_far.",
    stop_logic_plain_english: "1% below entry.",
    target_logic_plain_english: "1× gap-size above entry.",
    logical_exit_logic_plain_english: "Flat by 11:30 ET if no follow-through.",
    intent_keywords: ["gap", "premarket", "intraday", "continuation"],
    requires_session_execution: true,
    deferred_reason: DEFER_SESSION_REASON,
  },
  {
    id: "prior-day-high-low-breakout",
    display_name: "Prior Day High/Low Breakout",
    short_description:
      "Both directions. Break of prior day's high or low.",
    long_description:
      "Classic intraday momentum. Long on close > prior_day_high; short on close < prior_day_low. Stops 1× ATR opposite side, target 2× ATR.",
    intended_horizon: "intraday",
    default_direction: "both",
    default_base_timeframe: "15m",
    regime_assumption: "high_vol",
    expected_hold_time: "hours",
    known_behavior:
      "Classic strategy with broad applicability. Strongest on names with average daily range > recent.",
    caveats:
      "Pair with an average-daily-range filter. Avoid the day after holidays or low-volume sessions.",
    indicative_only_disclaimer: true,
    required_feature_families: [
      "prior_day_high",
      "prior_day_low",
      "ATR",
      "close",
    ],
    feature_seeds: [
      "15m.prior_day_high[0]",
      "15m.prior_day_low[0]",
      "15m.atr:length=14[0]",
      "15m.close[0]",
    ],
    wizard_intent_seed: {
      direction: "both",
      horizon: "intraday",
      base_timeframe: "15m",
      higher_timeframe_confirmation: false,
      has_stop: true,
      has_target: true,
      has_multiple_targets: false,
      has_runner: false,
      has_logical_exit: true,
      has_time_based_exit: true,
    },
    prompt_seed:
      "Long when 15m close > prior_day_high; short when close < prior_day_low. Stop 1× ATR(14) opposite side. Target 2× ATR(14). Flat by 15:55 ET.",
    entry_logic_plain_english:
      "Long break of prior_day_high; short break of prior_day_low.",
    stop_logic_plain_english: "1× ATR(14) opposite side.",
    target_logic_plain_english: "2× ATR(14).",
    logical_exit_logic_plain_english: "Flat by 15:55 ET.",
    intent_keywords: ["breakout", "prior_day", "intraday", "ATR"],
    requires_session_execution: true,
    deferred_reason: DEFER_SESSION_REASON,
  },
];

export function readyTemplates(): readonly StarterTemplate[] {
  return STARTER_TEMPLATES.filter((t) => !t.requires_session_execution);
}

export function deferredTemplates(): readonly StarterTemplate[] {
  return STARTER_TEMPLATES.filter((t) => t.requires_session_execution);
}

export function findTemplateById(id: string): StarterTemplate | null {
  return STARTER_TEMPLATES.find((t) => t.id === id) ?? null;
}

import type { WizardIntent } from "@/api/schemas/strategyComposer";
import type { StarterTemplate } from "./templates";

/**
 * Lightweight intent extraction for the Page-1 wizard.
 *
 * Operator-locked rule (Slice 6b): "Do not rely only on fuzzy string matching.
 * Use basic intent extraction — detect keywords (RSI, breakout, mean reversion,
 * gap, VWAP, etc.) + timeframe references + map to template scoring."
 *
 * This module is kept deliberately small and deterministic. It runs on every
 * keystroke client-side; no backend round-trip. Patterns deliberately bias for
 * recall over precision — better to surface a probably-relevant template than
 * miss one. Operator always has final say.
 */

export type IntentSignalKind =
  | "feature_family"
  | "timeframe"
  | "horizon"
  | "direction"
  | "exit_style";

export type IntentSignal = {
  kind: IntentSignalKind;
  value: string;
  source_phrase: string;
};

const FEATURE_FAMILY_PATTERNS: ReadonlyArray<{
  patterns: readonly string[];
  value: string;
}> = [
  { patterns: ["connors"], value: "connors" },
  {
    patterns: ["rsi", "relative strength"],
    value: "RSI",
  },
  {
    patterns: ["mean reversion", "mean-reversion", "mean reverting", "oversold", "overbought"],
    value: "mean_reversion",
  },
  {
    patterns: [
      "breakout",
      "break out",
      "break above",
      "break below",
      "breaks above",
      "breaks below",
      "breaking above",
      "breaking below",
    ],
    value: "breakout",
  },
  {
    patterns: ["gap up", "gap down", "gap and go", "gap-and-go", " gap "],
    value: "gap",
  },
  { patterns: ["vwap"], value: "VWAP" },
  {
    patterns: ["ichimoku", "tenkan", "kijun", "senkou", "chikou", "cloud"],
    value: "ichimoku",
  },
  { patterns: ["macd"], value: "MACD" },
  {
    patterns: ["fvg", "fair value gap", "fair-value gap", "imbalance"],
    value: "FVG",
  },
  {
    patterns: ["supertrend", "super trend", "super-trend"],
    value: "supertrend",
  },
  {
    patterns: ["pullback", "pull back", "pull-back"],
    value: "pullback",
  },
  {
    patterns: ["opening range", "orb"],
    value: "opening_range",
  },
  {
    patterns: ["prior day", "previous day", "yesterday's high", "yesterday's low"],
    value: "prior_day",
  },
  {
    patterns: ["ibs", "internal bar strength"],
    value: "IBS",
  },
  { patterns: ["atr"], value: "ATR" },
  {
    patterns: ["sma", "simple moving average"],
    value: "SMA",
  },
  {
    patterns: ["ema", "exponential moving average"],
    value: "EMA",
  },
  {
    patterns: ["highest", "lowest"],
    value: "highest",
  },
  {
    patterns: ["session high", "session low", "session-high", "session-low"],
    value: "session_high_low",
  },
];

// Ordered longest-pattern-first; each pattern is matched against
// `\b<pattern>\b` style boundaries (we approximate with leading/trailing
// whitespace since the haystack is space-padded) so "15 minute" cannot
// be partially matched as "5 minute".
const TIMEFRAME_PATTERNS: ReadonlyArray<{
  regexes: readonly RegExp[];
  value: string;
}> = [
  // weekly
  { regexes: [/\b1w\b/, /\bweekly\b/, /\b1[\s-]week\b/], value: "1w" },
  // daily
  { regexes: [/\b1d\b/, /\bdaily\b/, /\b1[\s-]day\b/, /\bend of day\b/], value: "1d" },
  // 4h
  { regexes: [/\b4h\b/, /\b4[\s-]hour\b/, /\bfour hour\b/], value: "4h" },
  // 1h
  { regexes: [/\b1h\b/, /\bhourly\b/, /\b1[\s-]hour\b/, /\bone hour\b/], value: "1h" },
  // 30m
  { regexes: [/\b30m\b/, /\b30[\s-]minute\b/, /\bthirty minute\b/], value: "30m" },
  // 15m
  { regexes: [/\b15m\b/, /\b15[\s-]minute\b/, /\bfifteen minute\b/], value: "15m" },
  // 5m
  { regexes: [/\b5m\b/, /\b5[\s-]minute\b/, /\bfive minute\b/], value: "5m" },
  // 1m
  { regexes: [/\b1m\b/, /\b1[\s-]minute\b/, /\bone minute\b/], value: "1m" },
];

export function extractIntent(prompt: string): IntentSignal[] {
  const signals: IntentSignal[] = [];
  if (!prompt.trim()) return signals;
  // Pad with spaces so word-boundary tokens like " gap " can match start/end.
  const haystack = ` ${prompt.toLowerCase()} `;

  const pushed = new Set<string>(); // dedupe per (kind:value)
  function push(kind: IntentSignalKind, value: string, source_phrase: string) {
    const k = `${kind}:${value}`;
    if (pushed.has(k)) return;
    pushed.add(k);
    signals.push({ kind, value, source_phrase });
  }

  for (const { patterns, value } of FEATURE_FAMILY_PATTERNS) {
    for (const pat of patterns) {
      if (haystack.includes(pat)) {
        push("feature_family", value, pat.trim());
        break;
      }
    }
  }

  // Track which timeframes already matched — only push the most specific.
  let timeframeMatched = false;
  for (const { regexes, value } of TIMEFRAME_PATTERNS) {
    if (timeframeMatched) break;
    for (const rgx of regexes) {
      if (rgx.test(haystack)) {
        push("timeframe", value, value);
        timeframeMatched = true;
        break;
      }
    }
  }

  if (haystack.includes("scalp")) push("horizon", "scalping", "scalp");
  if (
    haystack.includes("intraday") ||
    haystack.includes("day trade") ||
    haystack.includes("day-trade")
  ) {
    push("horizon", "intraday", "intraday");
  }
  if (haystack.includes("swing")) push("horizon", "swing", "swing");
  if (
    haystack.includes("position trade") ||
    haystack.includes("long-term") ||
    haystack.includes("long term") ||
    haystack.includes("multi-week")
  ) {
    push("horizon", "position", "position");
  }

  const hasShort = / short(?!-?term)| short\.|^short |going short|short side/.test(haystack);
  const hasLong = / long(?!-?term)| long\.|^long |going long|long side/.test(haystack);
  if (hasShort && hasLong) {
    push("direction", "both", "both");
  } else if (hasShort) {
    push("direction", "short", "short");
  } else if (hasLong) {
    push("direction", "long", "long");
  } else if (haystack.includes("both directions") || haystack.includes("long and short")) {
    push("direction", "both", "both");
  }

  if (
    haystack.includes("flat by") ||
    haystack.includes("close all by") ||
    haystack.includes("force flat")
  ) {
    push("exit_style", "time_based", "flat by");
  }
  if (
    haystack.includes("after") &&
    (haystack.includes("bars") || haystack.includes("minutes") || haystack.includes("days"))
  ) {
    push("exit_style", "time_based", "after N bars/min/days");
  }

  return signals;
}

/**
 * Score a template against the extracted signals. Higher score = better match.
 * Used to surface the top-3 matches in the side panel.
 */
export function scoreTemplate(
  template: StarterTemplate,
  signals: readonly IntentSignal[],
): number {
  if (signals.length === 0) return 0;
  let score = 0;
  for (const signal of signals) {
    if (signal.kind === "feature_family") {
      if (template.intent_keywords.includes(signal.value)) score += 3;
    } else if (signal.kind === "horizon") {
      if (template.intended_horizon === signal.value) score += 2;
    } else if (signal.kind === "direction") {
      if (template.default_direction === signal.value) score += 2;
    } else if (signal.kind === "timeframe") {
      if (template.default_base_timeframe === signal.value) score += 1;
    }
  }
  return score;
}

export type WizardConflict = {
  field: keyof Pick<WizardIntent, "horizon" | "direction" | "base_timeframe">;
  prompt_value: string;
  checkbox_value: string;
};

/**
 * Detect when the prompt contradicts the current wizard checkboxes.
 *
 * Operator-facing rule: surface a non-blocking warning chip; offer "Adjust to
 * match prompt" or "Keep my checkboxes". Never silently override.
 */
export function detectConflicts(
  signals: readonly IntentSignal[],
  wizard: WizardIntent,
): WizardConflict[] {
  const conflicts: WizardConflict[] = [];
  const horizon = signals.find((s) => s.kind === "horizon");
  if (horizon && horizon.value !== wizard.horizon) {
    conflicts.push({
      field: "horizon",
      prompt_value: horizon.value,
      checkbox_value: wizard.horizon,
    });
  }
  const direction = signals.find((s) => s.kind === "direction");
  if (direction && direction.value !== wizard.direction) {
    conflicts.push({
      field: "direction",
      prompt_value: direction.value,
      checkbox_value: wizard.direction,
    });
  }
  const tf = signals.find((s) => s.kind === "timeframe");
  if (tf && tf.value !== wizard.base_timeframe) {
    conflicts.push({
      field: "base_timeframe",
      prompt_value: tf.value,
      checkbox_value: wizard.base_timeframe,
    });
  }
  return conflicts;
}

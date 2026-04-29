import { describe, expect, it } from "vitest";
import type { WizardIntent } from "@/api/schemas/strategyComposer";
import { detectConflicts, extractIntent, scoreTemplate } from "./intentExtraction";
import { findTemplateById } from "./templates";

const DEFAULT_WIZARD: WizardIntent = {
  direction: "long",
  horizon: "intraday",
  base_timeframe: "5m",
  higher_timeframe_confirmation: false,
  has_stop: true,
  has_target: false,
  has_multiple_targets: false,
  has_runner: false,
  has_logical_exit: true,
  has_time_based_exit: false,
};

describe("extractIntent", () => {
  it("returns nothing for empty prompt", () => {
    expect(extractIntent("")).toEqual([]);
    expect(extractIntent("   ")).toEqual([]);
  });

  it("detects RSI feature family", () => {
    const signals = extractIntent("Long when RSI is below 30");
    expect(signals.some((s) => s.kind === "feature_family" && s.value === "RSI")).toBe(true);
  });

  it("detects Connors specifically", () => {
    const signals = extractIntent("Connors RSI-2 mean reversion strategy");
    const values = signals.filter((s) => s.kind === "feature_family").map((s) => s.value);
    expect(values).toContain("connors");
    expect(values).toContain("RSI");
    expect(values).toContain("mean_reversion");
  });

  it("detects breakout family", () => {
    const signals = extractIntent("Long when close breaks above prior high");
    expect(signals.some((s) => s.value === "breakout")).toBe(true);
  });

  it("detects gap, VWAP, MACD, Ichimoku, FVG, supertrend", () => {
    const cases: Array<[string, string]> = [
      ["Trade gap up names at the open", "gap"],
      ["VWAP reclaim long", "VWAP"],
      ["MACD signal cross", "MACD"],
      ["Ichimoku cloud trend", "ichimoku"],
      ["5m fair value gap fill", "FVG"],
      ["Supertrend flip up", "supertrend"],
    ];
    for (const [prompt, value] of cases) {
      const signals = extractIntent(prompt);
      expect(signals.some((s) => s.value === value)).toBe(true);
    }
  });

  it("detects timeframes (5m, 15m, hourly, daily)", () => {
    const cases: Array<[string, string]> = [
      ["5m breakout", "5m"],
      ["15 minute strategy", "15m"],
      ["hourly trend follow", "1h"],
      ["daily mean reversion", "1d"],
    ];
    for (const [prompt, tf] of cases) {
      const signals = extractIntent(prompt);
      const found = signals.find((s) => s.kind === "timeframe");
      expect(found?.value).toBe(tf);
    }
  });

  it("detects horizon (scalping/intraday/swing/position)", () => {
    expect(
      extractIntent("Scalping the open").find((s) => s.kind === "horizon")?.value,
    ).toBe("scalping");
    expect(
      extractIntent("Intraday breakout").find((s) => s.kind === "horizon")?.value,
    ).toBe("intraday");
    expect(
      extractIntent("Swing trade dailies").find((s) => s.kind === "horizon")?.value,
    ).toBe("swing");
    expect(
      extractIntent("Long-term position trade").find((s) => s.kind === "horizon")?.value,
    ).toBe("position");
  });

  it("detects direction long-only", () => {
    const signals = extractIntent("I want to go long when RSI is oversold");
    expect(signals.some((s) => s.kind === "direction" && s.value === "long")).toBe(true);
  });

  it("detects direction short-only", () => {
    const signals = extractIntent("Going short when price breaks below VWAP");
    expect(signals.some((s) => s.kind === "direction" && s.value === "short")).toBe(true);
  });

  it("detects both directions when long AND short are mentioned", () => {
    const signals = extractIntent("Trade long when above VWAP and short when below");
    const direction = signals.find((s) => s.kind === "direction");
    expect(direction?.value).toBe("both");
  });

  it("detects time-based exit style", () => {
    const signals = extractIntent("Exit after 10 bars or flat by 15:55 ET");
    expect(signals.some((s) => s.kind === "exit_style" && s.value === "time_based")).toBe(true);
  });

  it("dedupes repeated signals", () => {
    const signals = extractIntent("RSI long when RSI is below 30 and RSI cross up");
    const rsiSignals = signals.filter((s) => s.kind === "feature_family" && s.value === "RSI");
    expect(rsiSignals).toHaveLength(1);
  });
});

describe("scoreTemplate", () => {
  it("returns 0 when no signals", () => {
    const t = findTemplateById("vwap-reclaim")!;
    expect(scoreTemplate(t, [])).toBe(0);
  });

  it("scores Connors RSI-2 highest for a Connors-RSI prompt", () => {
    const signals = extractIntent("Connors RSI-2 mean reversion daily long");
    const ranked = [
      "connors-rsi-2",
      "rsi-mean-reversion",
      "vwap-reclaim",
      "supertrend-trend-follow",
    ].map((id) => ({
      id,
      score: scoreTemplate(findTemplateById(id)!, signals),
    }));
    ranked.sort((a, b) => b.score - a.score);
    expect(ranked[0].id).toBe("connors-rsi-2");
  });

  it("scores VWAP Reclaim highest for a VWAP intraday prompt", () => {
    const signals = extractIntent("VWAP reclaim intraday 5m long");
    const ranked = [
      "vwap-reclaim",
      "supertrend-trend-follow",
      "rsi-mean-reversion",
    ].map((id) => ({
      id,
      score: scoreTemplate(findTemplateById(id)!, signals),
    }));
    ranked.sort((a, b) => b.score - a.score);
    expect(ranked[0].id).toBe("vwap-reclaim");
  });

  it("scores Supertrend highest for a supertrend hourly trend prompt", () => {
    const signals = extractIntent("Supertrend swing trend follow on hourly chart, both long and short");
    const ranked = [
      "supertrend-trend-follow",
      "vwap-reclaim",
      "rsi-mean-reversion",
    ].map((id) => ({
      id,
      score: scoreTemplate(findTemplateById(id)!, signals),
    }));
    ranked.sort((a, b) => b.score - a.score);
    expect(ranked[0].id).toBe("supertrend-trend-follow");
  });
});

describe("detectConflicts", () => {
  it("returns no conflicts when prompt is empty", () => {
    expect(detectConflicts(extractIntent(""), DEFAULT_WIZARD)).toEqual([]);
  });

  it("detects horizon conflict (prompt says swing, checkbox says intraday)", () => {
    const signals = extractIntent("Swing trade daily RSI mean reversion");
    const conflicts = detectConflicts(signals, DEFAULT_WIZARD);
    const horizon = conflicts.find((c) => c.field === "horizon");
    expect(horizon?.prompt_value).toBe("swing");
    expect(horizon?.checkbox_value).toBe("intraday");
  });

  it("detects direction conflict (prompt says short, checkbox says long)", () => {
    const signals = extractIntent("Going short when price breaks below support");
    const conflicts = detectConflicts(signals, DEFAULT_WIZARD);
    const direction = conflicts.find((c) => c.field === "direction");
    expect(direction?.prompt_value).toBe("short");
    expect(direction?.checkbox_value).toBe("long");
  });

  it("detects timeframe conflict (prompt says 1h, checkbox says 5m)", () => {
    const signals = extractIntent("Hourly supertrend follower");
    const conflicts = detectConflicts(signals, DEFAULT_WIZARD);
    const tf = conflicts.find((c) => c.field === "base_timeframe");
    expect(tf?.prompt_value).toBe("1h");
    expect(tf?.checkbox_value).toBe("5m");
  });

  it("returns empty when prompt aligns with checkboxes", () => {
    const signals = extractIntent("Intraday 5m long breakout");
    expect(detectConflicts(signals, DEFAULT_WIZARD)).toEqual([]);
  });
});

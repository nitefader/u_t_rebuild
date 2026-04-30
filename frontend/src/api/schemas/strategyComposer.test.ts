import { describe, expect, it } from "vitest";
import { StrategyControlsVersionSchema } from "./strategyComposer";

const fullPayload = {
  id: "sc-1",
  strategy_controls_id: "sc-id-1",
  version: 1,
  name: "Controls",
  timeframe: "5m",
  trading_horizon: "intraday",
  allowed_directions: "long",
  higher_timeframe_confirmation_required: false,
  session_preference: "regular_only",
  earnings_news_blackout_enabled: false,
  // Fields previously dropped on the floor by the frontend schema:
  cooldown_bars: 3,
  cooldown_minutes: null,
  max_trades_per_session: 5,
  max_trades_per_day: 20,
  session_windows: [
    { session: "regular", start: "09:30:00", end: "16:00:00" },
  ],
  avoid_first_minutes: 5,
  no_new_entries_after: "15:30:00",
  force_flat_by: "15:55:00",
  time_based_exit_after_bars: null,
  time_based_exit_after_minutes: null,
  time_based_exit_after_days: null,
  feature_refs: ["5m.ema:length=20[0]"],
  regime_filter_refs: ["regime.spy_above_200d"],
};

describe("StrategyControlsVersionSchema", () => {
  it("round-trips a backend payload that carries the full control surface", () => {
    const parsed = StrategyControlsVersionSchema.parse(fullPayload);
    expect(parsed.cooldown_bars).toBe(3);
    expect(parsed.cooldown_minutes).toBeNull();
    expect(parsed.max_trades_per_session).toBe(5);
    expect(parsed.max_trades_per_day).toBe(20);
    expect(parsed.session_windows).toEqual([
      { session: "regular", start: "09:30:00", end: "16:00:00" },
    ]);
    expect(parsed.avoid_first_minutes).toBe(5);
    expect(parsed.no_new_entries_after).toBe("15:30:00");
    expect(parsed.force_flat_by).toBe("15:55:00");
    expect(parsed.feature_refs).toEqual(["5m.ema:length=20[0]"]);
    expect(parsed.regime_filter_refs).toEqual(["regime.spy_above_200d"]);
  });

  it("applies defaults when the new fields are absent (existing drafts still parse)", () => {
    const minimal = {
      id: "sc-1",
      strategy_controls_id: "sc-id-1",
      version: 1,
      name: "Controls",
      timeframe: "5m",
    };
    const parsed = StrategyControlsVersionSchema.parse(minimal);
    expect(parsed.session_windows).toEqual([]);
    expect(parsed.feature_refs).toEqual([]);
    expect(parsed.regime_filter_refs).toEqual([]);
    expect(parsed.cooldown_bars).toBeUndefined();
    expect(parsed.max_trades_per_day).toBeUndefined();
  });

  it("rejects setting both cooldown_bars and cooldown_minutes", () => {
    const result = StrategyControlsVersionSchema.safeParse({
      ...fullPayload,
      cooldown_bars: 3,
      cooldown_minutes: 10,
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("cooldown_bars or cooldown_minutes"))).toBe(true);
    }
  });

  it("rejects setting more than one time-based exit unit", () => {
    const result = StrategyControlsVersionSchema.safeParse({
      ...fullPayload,
      time_based_exit_after_bars: 10,
      time_based_exit_after_minutes: 30,
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("at most one of bars / minutes / days"))).toBe(true);
    }
  });

  it("rejects force_flat_by earlier than no_new_entries_after", () => {
    const result = StrategyControlsVersionSchema.safeParse({
      ...fullPayload,
      no_new_entries_after: "15:55:00",
      force_flat_by: "15:30:00",
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(result.error.issues.some((i) => i.message.includes("force_flat_by must be at or after"))).toBe(true);
    }
  });

  it("treats HH:MM and HH:MM:SS as equal when comparing force_flat_by ≥ no_new_entries_after", () => {
    // Adversarial case: lex compare would say "15:30" < "15:30:00" and
    // false-block this save. Numeric-seconds compare must accept it.
    const result = StrategyControlsVersionSchema.safeParse({
      ...fullPayload,
      no_new_entries_after: "15:30:00",
      force_flat_by: "15:30",
    });
    expect(result.success).toBe(true);
  });

  it("still rejects force_flat_by earlier than no_new_entries_after across mixed precision", () => {
    const result = StrategyControlsVersionSchema.safeParse({
      ...fullPayload,
      no_new_entries_after: "15:30:00",
      force_flat_by: "15:29",
    });
    expect(result.success).toBe(false);
  });
});

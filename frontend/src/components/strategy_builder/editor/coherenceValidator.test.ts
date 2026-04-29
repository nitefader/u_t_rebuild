/**
 * Unit tests for coherenceValidator.ts — one test per rule + dismissal test.
 */

import { describe, expect, it } from "vitest";
import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import type { StrategyDraft } from "@/api/schemas/strategyComposer";
import type { StrategyVersionPayload } from "@/api/schemas/strategies";
import { editorStateFromDraft } from "./editorState";
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRuleArray = any;
import type { EditorState } from "./editorState";
import { validateCoherence } from "./coherenceValidator";
import type { CoherenceWarning } from "./coherenceValidator";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeStrategy(overrides: Partial<StrategyVersionPayload> = {}): StrategyVersionPayload {
  return {
    id: "ver-1",
    strategy_id: "strat-1",
    version: 1,
    name: "Test",
    description: null,
    feature_refs: ["5m.close[0]"],
    entry_rules: [
      {
        name: "long_entry",
        side: "long",
        intent_type: "entry",
        condition: {
          kind: "group",
          operator: "all",
          children: [
            {
              kind: "condition",
              left_feature: "5m.close[0]",
              operator: "gt",
              right_feature: "5m.open[0]",
            },
          ],
        },
        logical_exit_rule: null,
      },
    ],
    exit_rules: [],
    tags: [],
    created_at: "2026-04-28T00:00:00Z",
    ...overrides,
  };
}

function makeDraft(
  strategyOverrides: Partial<StrategyVersionPayload> = {},
  controlsOverrides: Record<string, unknown> = {},
  presetKind = "market_entry_market_exit",
  presetOverrides: Record<string, unknown> = {},
): StrategyDraft {
  return {
    draft_id: "draft-1",
    prompt: "test",
    strategy: makeStrategy(strategyOverrides),
    strategy_controls: {
      id: "sc-1",
      strategy_controls_id: "sc-id-1",
      version: 1,
      name: "Controls",
      timeframe: "5m",
      trading_horizon: "swing",
      allowed_directions: "long",
      higher_timeframe_confirmation_required: false,
      session_preference: "regular_only",
      earnings_news_blackout_enabled: false,
      ...controlsOverrides,
    },
    execution_style: {
      id: "es-1",
      execution_style_id: "es-id-1",
      version: 1,
      name: "Style",
      entry_order_type: "market",
      feature_refs: [],
      preset: { kind: presetKind, overrides: presetOverrides },
      created_at: "2026-04-28T00:00:00Z",
    },
    backtest_plan: { symbols: [], timeframe: "5m", initial_capital: 100000, cost_model: null },
    launch_plans: {},
    signal_plan_shape: null,
    validation: { valid: true, errors: [], warnings: [], normalized_feature_refs: [] },
  } as unknown as StrategyDraft;
}

function makeState(
  strategyOverrides: Partial<StrategyVersionPayload> = {},
  controlsOverrides: Record<string, unknown> = {},
  presetKind = "market_entry_market_exit",
  presetOverrides: Record<string, unknown> = {},
): EditorState {
  return editorStateFromDraft(makeDraft(strategyOverrides, controlsOverrides, presetKind, presetOverrides));
}

function makeCatalogItem(kind: string, overrides: Partial<FeatureCatalogItem> = {}): FeatureCatalogItem {
  return {
    kind,
    display_name: kind,
    namespace: "technical",
    scope: "symbol",
    source: "",
    allowed_params: [],
    default_params: {},
    supported_timeframes: ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
    supported_consumers: ["backtest", "live"],
    supported_modes: [],
    example_refs: [],
    description: null,
    ...overrides,
  };
}

const emptyCatalog: FeatureCatalogItem[] = [];
const dismissed = new Set<string>();

function findById(warnings: CoherenceWarning[], id: string): CoherenceWarning | undefined {
  return warnings.find((w) => w.id === id);
}

// ---------------------------------------------------------------------------
// Rule: htf_in_exit_not_entry (warn)
// ---------------------------------------------------------------------------

describe("htf_in_exit_not_entry", () => {
  it("fires when exit refs a higher-timeframe feature not present in entry", () => {
    const state = makeState(
      {
        feature_refs: ["5m.close[0]", "1h.ema:length=20[0]"],
        entry_rules: [
          {
            name: "long_entry",
            side: "long",
            intent_type: "entry",
            condition: {
              kind: "condition",
              left_feature: "5m.close[0]",
              operator: "gt",
              right_value: 0,
            },
            logical_exit_rule: null,
          },
        ] as AnyRuleArray,
        exit_rules: [
          {
            name: "feature_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: {
              kind: "feature_condition",
              feature_condition: {
                kind: "condition",
                left_feature: "1h.ema:length=20[0]",
                operator: "gt",
                right_value: 0,
              },
            },
          },
        ] as AnyRuleArray,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "htf_in_exit_not_entry");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("warn");
    expect(w!.sectionId).toBe("section-logical-exit");
  });

  it("does not fire when exit uses same timeframe as entry", () => {
    const state = makeState(
      {
        exit_rules: [
          {
            name: "feature_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: {
              kind: "feature_condition",
              feature_condition: {
                kind: "condition",
                left_feature: "5m.close[0]",
                operator: "lt",
                right_value: 0,
              },
            },
          },
        ] as AnyRuleArray,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "htf_in_exit_not_entry")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: logical_exit_fires_immediately_after_entry (error)
// ---------------------------------------------------------------------------

describe("logical_exit_fires_immediately_after_entry", () => {
  it("fires when feature exit overlaps entry feature with no minimum hold", () => {
    const state = makeState(
      {
        exit_rules: [
          {
            name: "feature_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: {
              kind: "feature_condition",
              feature_condition: {
                kind: "condition",
                left_feature: "5m.close[0]",
                operator: "lt",
                right_value: 0,
              },
            },
          },
        ] as AnyRuleArray,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "logical_exit_fires_immediately_after_entry");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("error");
    expect(w!.dismissed).toBe(false);
  });

  it("does not fire when a bars_since_entry hold exists", () => {
    const state = makeState(
      {
        exit_rules: [
          {
            name: "feature_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: {
              kind: "feature_condition",
              feature_condition: {
                kind: "condition",
                left_feature: "5m.close[0]",
                operator: "lt",
                right_value: 0,
              },
            },
          },
          {
            name: "bars_hold",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: { kind: "bars_since_entry", bars: 3 },
          },
        ] as AnyRuleArray,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "logical_exit_fires_immediately_after_entry")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: stop_target_ratio_nonsensical (warn)
// ---------------------------------------------------------------------------

describe("stop_target_ratio_nonsensical", () => {
  it("fires when target_pct / stop_pct < 0.5 for bracket_stop_target", () => {
    const state = makeState({}, {}, "bracket_stop_target", { stop_pct: 4.0, target_pct: 1.0 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "stop_target_ratio_nonsensical");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("warn");
    expect(w!.sectionId).toBe("section-stop-plan");
  });

  it("does not fire when ratio is 1:1 or better", () => {
    const state = makeState({}, {}, "bracket_stop_target", { stop_pct: 1.0, target_pct: 2.0 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "stop_target_ratio_nonsensical")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: intraday_no_time_exit (warn)
// ---------------------------------------------------------------------------

describe("intraday_no_time_exit", () => {
  it("fires for intraday strategy with no time-based exit", () => {
    const state = makeState({}, { trading_horizon: "intraday" });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "intraday_no_time_exit");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("warn");
    expect(w!.sectionId).toBe("section-strategy-controls");
  });

  it("fires for scalping strategy with no time-based exit", () => {
    const state = makeState({}, { trading_horizon: "scalping" });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "intraday_no_time_exit")).toBeDefined();
  });

  it("does not fire for swing strategy", () => {
    const state = makeState({}, { trading_horizon: "swing" });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "intraday_no_time_exit")).toBeUndefined();
  });

  it("does not fire for intraday when a bars_since_entry exit exists", () => {
    const state = makeState(
      {
        exit_rules: [
          {
            name: "bars_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: { kind: "bars_since_entry", bars: 10 },
          },
        ] as AnyRuleArray,
      },
      { trading_horizon: "intraday" },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "intraday_no_time_exit")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: feature_not_supported_for_timeframe (error)
// ---------------------------------------------------------------------------

describe("feature_not_supported_for_timeframe", () => {
  it("fires when a ref's timeframe is not in supported_timeframes", () => {
    const catalog = [makeCatalogItem("close", { supported_timeframes: ["5m", "15m"] })];
    const state = makeState({ feature_refs: ["1m.close[0]"] });
    const warnings = validateCoherence(state, catalog, dismissed);
    const w = warnings.find((x) => x.id.startsWith("feature_not_supported_for_timeframe"));
    expect(w).toBeDefined();
    expect(w!.severity).toBe("error");
    expect(w!.sectionId).toBe("section-required-features");
  });

  it("does not fire when timeframe is supported", () => {
    const catalog = [makeCatalogItem("close", { supported_timeframes: ["5m", "15m"] })];
    const state = makeState({ feature_refs: ["5m.close[0]"] });
    const warnings = validateCoherence(state, catalog, dismissed);
    expect(warnings.filter((w) => w.id.startsWith("feature_not_supported_for_timeframe"))).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Rule: feature_not_executable (error)
// ---------------------------------------------------------------------------

describe("feature_not_executable", () => {
  it("fires when feature kind is not in supported_consumers for backtest", () => {
    const catalog = [makeCatalogItem("live_only_feat", { supported_consumers: ["live"] })];
    const state = makeState({ feature_refs: ["5m.live_only_feat[0]"] });
    const warnings = validateCoherence(state, catalog, dismissed);
    const w = warnings.find((x) => x.id.startsWith("feature_not_executable"));
    expect(w).toBeDefined();
    expect(w!.severity).toBe("error");
    expect(w!.sectionId).toBe("section-required-features");
  });

  it("does not fire when backtest is in supported_consumers", () => {
    const catalog = [makeCatalogItem("close", { supported_consumers: ["backtest", "live"] })];
    const state = makeState({ feature_refs: ["5m.close[0]"] });
    const warnings = validateCoherence(state, catalog, dismissed);
    expect(warnings.filter((w) => w.id.startsWith("feature_not_executable"))).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Rule: stop_pct_out_of_range (error)
// ---------------------------------------------------------------------------

describe("stop_pct_out_of_range", () => {
  it("fires when stop_pct = 0 for bracket_stop_target", () => {
    const state = makeState({}, {}, "bracket_stop_target", { stop_pct: 0, target_pct: 2 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "stop_pct_out_of_range")).toBeDefined();
  });

  it("fires when stop_pct > 50 for bracket_stop_target", () => {
    const state = makeState({}, {}, "bracket_stop_target", { stop_pct: 51, target_pct: 2 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "stop_pct_out_of_range")?.severity).toBe("error");
  });

  it("does not fire when stop_pct is 1.5 (valid)", () => {
    const state = makeState({}, {}, "bracket_stop_target", { stop_pct: 1.5, target_pct: 3 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "stop_pct_out_of_range")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: target_pct_out_of_range (error)
// ---------------------------------------------------------------------------

describe("target_pct_out_of_range", () => {
  it("fires when target_pct <= 0 for bracket_stop_target", () => {
    const state = makeState({}, {}, "bracket_stop_target", { stop_pct: 1, target_pct: 0 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "target_pct_out_of_range")?.severity).toBe("error");
  });

  it("does not fire when target_pct = 2", () => {
    const state = makeState({}, {}, "bracket_stop_target", { stop_pct: 1, target_pct: 2 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "target_pct_out_of_range")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: targets_runner_exceed_100 (error)
// ---------------------------------------------------------------------------

describe("targets_runner_exceed_100", () => {
  it("fires when sum of slice_pct > 1.0 for multi_target_scale_out", () => {
    const state = makeState(
      {},
      {},
      "multi_target_scale_out",
      {
        targets: [
          { target_pct: 1, slice_pct: 0.5 },
          { target_pct: 2, slice_pct: 0.6 },
        ],
        stop_pct: null,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "targets_runner_exceed_100");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("error");
    expect(w!.sectionId).toBe("section-target-plan");
  });

  it("does not fire when sum = 1.0", () => {
    const state = makeState(
      {},
      {},
      "multi_target_scale_out",
      {
        targets: [
          { target_pct: 1, slice_pct: 0.5 },
          { target_pct: 2, slice_pct: 0.5 },
        ],
        stop_pct: null,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "targets_runner_exceed_100")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: targets_below_100_no_runner_no_stop (warn)
// ---------------------------------------------------------------------------

describe("targets_below_100_no_runner_no_stop", () => {
  it("fires when sum < 1.0 and stop_pct is null", () => {
    const state = makeState(
      {},
      {},
      "multi_target_scale_out",
      {
        targets: [
          { target_pct: 1, slice_pct: 0.25 },
          { target_pct: 2, slice_pct: 0.25 },
        ],
        stop_pct: null,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "targets_below_100_no_runner_no_stop");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("warn");
  });

  it("does not fire when stop_pct is set", () => {
    const state = makeState(
      {},
      {},
      "multi_target_scale_out",
      {
        targets: [
          { target_pct: 1, slice_pct: 0.25 },
          { target_pct: 2, slice_pct: 0.25 },
        ],
        stop_pct: 1.5,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "targets_below_100_no_runner_no_stop")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: short_enabled_no_short_entry (error)
// ---------------------------------------------------------------------------

describe("short_enabled_no_short_entry", () => {
  it("fires when allowed_directions=short but no short entry exists", () => {
    const state = makeState({}, { allowed_directions: "short" });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "short_enabled_no_short_entry");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("error");
    expect(w!.sectionId).toBe("section-entry-short");
  });

  it("fires when allowed_directions=both but only long entry exists", () => {
    const state = makeState({}, { allowed_directions: "both" });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "short_enabled_no_short_entry")).toBeDefined();
  });

  it("does not fire when a short entry is present", () => {
    const state = makeState(
      {
        entry_rules: [
          { name: "long_entry", side: "long", intent_type: "entry", condition: null, logical_exit_rule: null },
          { name: "short_entry", side: "short", intent_type: "entry", condition: null, logical_exit_rule: null },
        ] as AnyRuleArray,
      },
      { allowed_directions: "both" },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "short_enabled_no_short_entry")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: both_dir_asymmetric_exits (warn)
// ---------------------------------------------------------------------------

describe("both_dir_asymmetric_exits", () => {
  it("fires when exits exist but none covers short side", () => {
    const state = makeState(
      {
        entry_rules: [
          { name: "long_entry", side: "long", intent_type: "entry", condition: null, logical_exit_rule: null },
          { name: "short_entry", side: "short", intent_type: "entry", condition: null, logical_exit_rule: null },
        ] as AnyRuleArray,
        exit_rules: [
          {
            name: "long_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: { kind: "feature_condition" },
          },
        ] as AnyRuleArray,
      },
      { allowed_directions: "both" },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "both_dir_asymmetric_exits");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("warn");
    expect(w!.sectionId).toBe("section-logical-exit");
  });

  it("does not fire when exits cover both sides", () => {
    const state = makeState(
      {
        entry_rules: [
          { name: "long_entry", side: "long", intent_type: "entry", condition: null, logical_exit_rule: null },
          { name: "short_entry", side: "short", intent_type: "entry", condition: null, logical_exit_rule: null },
        ] as AnyRuleArray,
        exit_rules: [
          {
            name: "long_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: { kind: "feature_condition" },
          },
          {
            name: "short_exit",
            side: "short",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: { kind: "feature_condition" },
          },
        ] as AnyRuleArray,
      },
      { allowed_directions: "both" },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "both_dir_asymmetric_exits")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: htf_confirmation_required_but_no_htf_feature (error)
// ---------------------------------------------------------------------------

describe("htf_confirmation_required_but_no_htf_feature", () => {
  it("fires when HTF required but all refs are on the base timeframe", () => {
    const state = makeState(
      { feature_refs: ["5m.close[0]"] },
      { timeframe: "5m", higher_timeframe_confirmation_required: true },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "htf_confirmation_required_but_no_htf_feature");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("error");
    expect(w!.sectionId).toBe("section-strategy-controls");
  });

  it("does not fire when an HTF ref is present", () => {
    const state = makeState(
      { feature_refs: ["5m.close[0]", "1h.ema:length=20[0]"] },
      { timeframe: "5m", higher_timeframe_confirmation_required: true },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "htf_confirmation_required_but_no_htf_feature")).toBeUndefined();
  });

  it("does not fire when HTF confirmation is not required", () => {
    const state = makeState(
      { feature_refs: ["5m.close[0]"] },
      { timeframe: "5m", higher_timeframe_confirmation_required: false },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "htf_confirmation_required_but_no_htf_feature")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: time_based_exit_no_unit (error)
// ---------------------------------------------------------------------------

describe("time_based_exit_no_unit", () => {
  it("fires when a bars_since_entry rule has bars=0", () => {
    const state = makeState(
      {
        exit_rules: [
          {
            name: "bars_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: { kind: "bars_since_entry", bars: 0 },
          },
        ] as AnyRuleArray,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "time_based_exit_no_unit");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("error");
    expect(w!.sectionId).toBe("section-time-based-exit");
  });

  it("does not fire when bars_since_entry has bars=5", () => {
    const state = makeState(
      {
        exit_rules: [
          {
            name: "bars_exit",
            side: "long",
            intent_type: "exit",
            condition: null,
            logical_exit_rule: { kind: "bars_since_entry", bars: 5 },
          },
        ] as AnyRuleArray,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "time_based_exit_no_unit")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Rule: multi_target_slices_below_100 (info)
// ---------------------------------------------------------------------------

describe("multi_target_slices_below_100", () => {
  it("fires as info when sum < 1.0 AND stop_pct is set", () => {
    const state = makeState(
      {},
      {},
      "multi_target_scale_out",
      {
        targets: [
          { target_pct: 1, slice_pct: 0.25 },
          { target_pct: 2, slice_pct: 0.25 },
        ],
        stop_pct: 1.5,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    const w = findById(warnings, "multi_target_slices_below_100");
    expect(w).toBeDefined();
    expect(w!.severity).toBe("info");
    expect(w!.sectionId).toBe("section-target-plan");
  });

  it("does not fire when sum = 1.0", () => {
    const state = makeState(
      {},
      {},
      "multi_target_scale_out",
      {
        targets: [
          { target_pct: 1, slice_pct: 0.5 },
          { target_pct: 2, slice_pct: 0.5 },
        ],
        stop_pct: 1.5,
      },
    );
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "multi_target_slices_below_100")).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Dismissal test — warn/info get dismissed=true; errors stay dismissed=false
// ---------------------------------------------------------------------------

describe("dismissal", () => {
  it("sets dismissed=true for warn when id is in dismissedIds", () => {
    const state = makeState({}, { trading_horizon: "intraday" });
    const dismissedSet = new Set(["intraday_no_time_exit"]);
    const warnings = validateCoherence(state, emptyCatalog, dismissedSet);
    const w = findById(warnings, "intraday_no_time_exit");
    expect(w).toBeDefined();
    expect(w!.dismissed).toBe(true);
    expect(w!.severity).toBe("warn");
  });

  it("errors always have dismissed=false even if id is in dismissedIds", () => {
    const state = makeState({}, { allowed_directions: "short" });
    const dismissedSet = new Set(["short_enabled_no_short_entry"]);
    const warnings = validateCoherence(state, emptyCatalog, dismissedSet);
    const w = findById(warnings, "short_enabled_no_short_entry");
    expect(w).toBeDefined();
    expect(w!.dismissed).toBe(false);
    expect(w!.severity).toBe("error");
  });

  it("sets dismissed=true for info when id is in dismissedIds", () => {
    const state = makeState(
      {},
      {},
      "multi_target_scale_out",
      {
        targets: [
          { target_pct: 1, slice_pct: 0.25 },
          { target_pct: 2, slice_pct: 0.25 },
        ],
        stop_pct: 1.5,
      },
    );
    const dismissedSet = new Set(["multi_target_slices_below_100"]);
    const warnings = validateCoherence(state, emptyCatalog, dismissedSet);
    const w = findById(warnings, "multi_target_slices_below_100");
    expect(w?.dismissed).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// Rule: cooldown_bars_on_coarse_timeframe (warn)
// ---------------------------------------------------------------------------

describe("cooldown_bars_on_coarse_timeframe", () => {
  it("fires when cooldown_bars is set on a 1d strategy", () => {
    const state = makeState({}, { timeframe: "1d", cooldown_bars: 3 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "cooldown_bars_on_coarse_timeframe")).toBeDefined();
  });

  it("fires on 1w as well (>= 1d rank)", () => {
    const state = makeState({}, { timeframe: "1w", cooldown_bars: 1 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "cooldown_bars_on_coarse_timeframe")).toBeDefined();
  });

  it("does NOT fire on intraday timeframes", () => {
    const state = makeState({}, { timeframe: "5m", cooldown_bars: 3 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "cooldown_bars_on_coarse_timeframe")).toBeUndefined();
  });

  it("does NOT fire when cooldown_bars is unset", () => {
    const state = makeState({}, { timeframe: "1d" });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "cooldown_bars_on_coarse_timeframe")).toBeUndefined();
  });

  it("does NOT fire when only cooldown_minutes is set on a daily strategy", () => {
    const state = makeState({}, { timeframe: "1d", cooldown_minutes: 1440 });
    const warnings = validateCoherence(state, emptyCatalog, dismissed);
    expect(findById(warnings, "cooldown_bars_on_coarse_timeframe")).toBeUndefined();
  });
});

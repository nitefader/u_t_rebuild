import { describe, expect, it } from "vitest";
import type { StrategyDraft } from "@/api/schemas/strategyComposer";
import type { StrategyVersionPayload } from "@/api/schemas/strategies";
import type { EditorRule } from "../SignalRuleEditor";
import {
  applyPresetToDraft,
  applyStrategyControlsToDraft,
  applyStrategyToDraft,
  bucketExitRules,
  collectAllFeatureRefs,
  editorStateFromDraft,
} from "./editorState";

function makeStrategy(overrides: Partial<StrategyVersionPayload> = {}): StrategyVersionPayload {
  return {
    id: "ver-1",
    strategy_id: "strat-1",
    version: 1,
    name: "Test",
    description: null,
    feature_refs: ["5m.ema:length=20[0]"],
    entry_rules: [],
    exit_rules: [],
    tags: [],
    created_at: "2026-04-28T00:00:00Z",
    ...overrides,
  };
}

function makeDraft(strategy: StrategyVersionPayload, presetKind = "market_entry_market_exit"): StrategyDraft {
  return {
    draft_id: "draft-1",
    prompt: "test prompt",
    strategy,
    strategy_controls: {
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
    },
    execution_style: {
      id: "es-1",
      execution_style_id: "es-id-1",
      version: 1,
      name: "Style",
      entry_order_type: "market",
      feature_refs: [],
      preset: { kind: presetKind, overrides: {} },
      created_at: "2026-04-28T00:00:00Z",
    },
    backtest_plan: {
      symbols: [],
      timeframe: "5m",
      initial_capital: 100000,
      cost_model: null,
    },
    launch_plans: {},
    signal_plan_shape: null,
    validation: { valid: true, errors: [], warnings: [], normalized_feature_refs: [] },
  } as unknown as StrategyDraft;
}

describe("editorState", () => {
  describe("editorStateFromDraft", () => {
    it("derives preset from draft.execution_style.preset.kind", () => {
      const draft = makeDraft(makeStrategy(), "bracket_stop_target");
      // Mutate the preset record to carry overrides:
      (draft.execution_style.preset as Record<string, unknown>).overrides = {
        stop_pct: 1.5,
        target_pct: 3,
      };
      const state = editorStateFromDraft(draft);
      expect(state.preset.kind).toBe("bracket_stop_target");
      expect(state.preset.overrides).toMatchObject({ stop_pct: 1.5, target_pct: 3 });
    });

    it("falls back to market_entry_market_exit when preset is missing", () => {
      const draft = makeDraft(makeStrategy());
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (draft.execution_style as any).preset = null;
      const state = editorStateFromDraft(draft);
      expect(state.preset.kind).toBe("market_entry_market_exit");
    });
  });

  describe("applyPresetToDraft", () => {
    it("syncs the preset back into draft.execution_style.preset", () => {
      const state = editorStateFromDraft(makeDraft(makeStrategy()));
      const next = applyPresetToDraft(state, {
        kind: "bracket_runner",
        overrides: { first_target_pct: 2, first_slice_pct: 0.5, trail_pct: 1.2 },
      });
      const preset = next.draft.execution_style.preset as Record<string, unknown>;
      expect(preset.kind).toBe("bracket_runner");
      expect(preset.overrides).toMatchObject({ trail_pct: 1.2 });
    });
  });

  describe("applyStrategyToDraft + applyStrategyControlsToDraft", () => {
    it("replaces only the targeted slice", () => {
      const initial = editorStateFromDraft(makeDraft(makeStrategy()));
      const renamed = applyStrategyToDraft(initial, makeStrategy({ name: "Renamed" }));
      expect(renamed.draft.strategy.name).toBe("Renamed");
      expect(renamed.draft.strategy_controls?.trading_horizon).toBe("intraday");

      const cleared = applyStrategyControlsToDraft(renamed, null);
      expect(cleared.draft.strategy_controls).toBeNull();
      expect(cleared.draft.strategy.name).toBe("Renamed");
    });
  });

  describe("bucketExitRules", () => {
    it("routes time-flavor logical_exit kinds to timeBased; feature/hybrid stay logical", () => {
      const rules: EditorRule[] = [
        {
          name: "feature_exit",
          side: "long",
          intent_type: "exit",
          logical_exit_rule: { kind: "feature_condition" },
        },
        {
          name: "bars_exit",
          side: "long",
          intent_type: "exit",
          logical_exit_rule: { kind: "bars_since_entry", bars: 10 },
        },
        {
          name: "tof_exit",
          side: "long",
          intent_type: "exit",
          logical_exit_rule: { kind: "time_of_day_et", hour: 15, minute: 55 },
        },
        {
          name: "hybrid_exit",
          side: "long",
          intent_type: "exit",
          logical_exit_rule: { kind: "hybrid", operator: "all", children: [] },
        },
      ];
      const buckets = bucketExitRules(rules);
      expect(buckets.logical.map((e) => e.rule.name)).toEqual(["feature_exit", "hybrid_exit"]);
      expect(buckets.timeBased.map((e) => e.rule.name)).toEqual(["bars_exit", "tof_exit"]);
      // Indices stay aligned to the source array.
      expect(buckets.logical[0]!.index).toBe(0);
      expect(buckets.timeBased[0]!.index).toBe(1);
    });

    it("rules without a logical_exit_rule fall into the logical bucket", () => {
      const rules: EditorRule[] = [
        { name: "no_rule", side: "long", intent_type: "exit" },
      ];
      const buckets = bucketExitRules(rules);
      expect(buckets.logical).toHaveLength(1);
      expect(buckets.timeBased).toHaveLength(0);
    });
  });

  describe("collectAllFeatureRefs", () => {
    it("includes feature_refs union, condition trees, and stop/target candidate features", () => {
      const strategy = makeStrategy({
        feature_refs: ["5m.ema:length=20[0]"],
        entry_rules: [
          {
            name: "entry_long",
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
                  right_feature: "5m.ema:length=20[0]",
                },
              ],
            },
          },
        ],
        exit_rules: [
          {
            name: "exit_long",
            side: "long",
            intent_type: "exit",
            stop_candidate_feature: "5m.atr:length=14[0]",
            logical_exit_rule: {
              kind: "feature_condition",
              feature_condition: {
                kind: "condition",
                left_feature: "5m.rsi:length=14[0]",
                operator: "gt",
                right_value: 70,
              },
            },
          },
        ],
      });
      const refs = collectAllFeatureRefs(strategy);
      expect(refs).toEqual(
        expect.arrayContaining([
          "5m.ema:length=20[0]",
          "5m.close[0]",
          "5m.atr:length=14[0]",
          "5m.rsi:length=14[0]",
        ]),
      );
    });

    it("dedupes refs that appear in multiple places", () => {
      const strategy = makeStrategy({
        feature_refs: ["5m.ema:length=20[0]", "5m.ema:length=20[0]"],
      });
      const refs = collectAllFeatureRefs(strategy);
      expect(refs).toHaveLength(1);
      expect(refs[0]).toBe("5m.ema:length=20[0]");
    });
  });
});

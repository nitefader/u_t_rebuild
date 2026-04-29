/**
 * coherenceValidator.ts — Client-side coherence rules for the Page-2 editor.
 *
 * Rules run synchronously over the full EditorState + feature catalog.
 * They produce CoherenceWarning objects that the editor surfaces
 * per-section (severity bars) and in the global CoherenceWarningsPanel.
 *
 * Doctrine guards:
 *   - Errors block Save. Warn/info do not.
 *   - Warn/info can be dismissed (tracked in EditorPage component state).
 *   - Errors cannot be dismissed (dismissed is always false for errors).
 *   - logical_exit is the only exit intent — never add a sibling intent here.
 */

import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import type { EditorRule } from "../SignalRuleEditor";
import type { BracketStopTargetOverrides, MultiTargetScaleOutOverrides } from "../ExecutionStylePresetRow";
import { TIME_BASED_EXIT_KINDS, collectAllFeatureRefs, bucketExitRules } from "./editorState";
import type { EditorState } from "./editorState";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type SectionId =
  | "section-required-features"
  | "section-entry-long"
  | "section-entry-short"
  | "section-stop-plan"
  | "section-target-plan"
  | "section-runner-plan"
  | "section-logical-exit"
  | "section-time-based-exit"
  | "section-strategy-controls"
  | "section-execution-preset";

export interface CoherenceWarning {
  /** Stable rule id used for dismissal tracking. */
  id: string;
  severity: "error" | "warn" | "info";
  sectionId: SectionId;
  message: string;
  /**
   * true when the id is present in the dismissedIds set.
   * Only warn/info can be dismissed; errors always have dismissed=false.
   */
  dismissed: boolean;
}

// ---------------------------------------------------------------------------
// Timeframe rank table (mirrors backend)
// ---------------------------------------------------------------------------

const TIMEFRAME_RANK: Record<string, number> = {
  "1m": 1,
  "5m": 5,
  "15m": 15,
  "30m": 30,
  "1h": 60,
  "4h": 240,
  "1d": 1440,
  "1w": 10080,
  "1mo": 43200,
};

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/** Extract the timeframe prefix from a canonical feature ref like "5m.ema:length=20[0]" */
function refTimeframe(ref: string): string | null {
  const dot = ref.indexOf(".");
  return dot >= 0 ? ref.slice(0, dot) : null;
}

/** Extract the feature kind from a canonical ref "5m.ema:length=20[0]" → "ema" */
function refKind(ref: string): string | null {
  const dot = ref.indexOf(".");
  if (dot < 0) return null;
  const rest = ref.slice(dot + 1);
  const colon = rest.indexOf(":");
  const bracket = rest.indexOf("[");
  if (colon >= 0) return rest.slice(0, colon);
  if (bracket >= 0) return rest.slice(0, bracket);
  return rest || null;
}

/** Walk a condition tree and collect all feature refs in it. */
function refsInCondition(expr: unknown): string[] {
  if (!expr || typeof expr !== "object") return [];
  const node = expr as {
    kind?: string;
    left_feature?: string;
    right_feature?: string;
    children?: unknown[];
  };
  if (node.kind === "group") {
    return (node.children ?? []).flatMap(refsInCondition);
  }
  const out: string[] = [];
  if (typeof node.left_feature === "string" && node.left_feature) out.push(node.left_feature);
  if (typeof node.right_feature === "string" && node.right_feature) out.push(node.right_feature);
  return out;
}

/** Collect all feature refs referenced by entry rules (conditions + stop/target candidates). */
function entryFeatureRefs(rules: EditorRule[]): string[] {
  const out = new Set<string>();
  for (const rule of rules) {
    if (rule.intent_type !== "entry") continue;
    for (const ref of refsInCondition(rule.condition ?? null)) out.add(ref);
    if (rule.stop_candidate_feature) out.add(rule.stop_candidate_feature);
    if (rule.target_candidate_feature) out.add(rule.target_candidate_feature);
  }
  return Array.from(out);
}

/** Walk a logical_exit_rule recursively and collect feature refs. */
function refsInLogicalExit(rule: unknown): string[] {
  if (!rule || typeof rule !== "object") return [];
  const r = rule as {
    kind?: string;
    feature_condition?: unknown;
    children?: unknown[];
  };
  if (r.kind === "feature_condition") {
    return refsInCondition(r.feature_condition);
  }
  if (r.kind === "hybrid") {
    return (r.children ?? []).flatMap(refsInLogicalExit);
  }
  return [];
}

/** Collect feature refs from exit rules that are logical (non-time-based). */
function exitFeatureRefs(rules: EditorRule[]): string[] {
  const out = new Set<string>();
  const buckets = bucketExitRules(rules);
  for (const { rule } of buckets.logical) {
    for (const ref of refsInLogicalExit(rule.logical_exit_rule ?? null)) out.add(ref);
  }
  return Array.from(out);
}

// ---------------------------------------------------------------------------
// Main validator
// ---------------------------------------------------------------------------

export function validateCoherence(
  state: EditorState,
  catalog: FeatureCatalogItem[],
  dismissedIds: Set<string>,
): CoherenceWarning[] {
  const warnings: CoherenceWarning[] = [];

  function push(
    id: string,
    severity: "error" | "warn" | "info",
    sectionId: SectionId,
    message: string,
  ): void {
    const dismissed = severity !== "error" && dismissedIds.has(id);
    warnings.push({ id, severity, sectionId, message, dismissed });
  }

  const { draft, preset } = state;
  const strategy = draft.strategy;
  const controls = draft.strategy_controls ?? null;

  const allRefs = collectAllFeatureRefs(strategy);
  const entryRules = (strategy.entry_rules ?? []) as EditorRule[];
  const exitRules = (strategy.exit_rules ?? []) as EditorRule[];
  const buckets = bucketExitRules(exitRules);

  // Build a catalog lookup by kind.
  const catalogByKind = new Map<string, FeatureCatalogItem>();
  for (const item of catalog) {
    catalogByKind.set(item.kind, item);
  }

  // ------------------------------------------------------------------ §1
  // htf_in_exit_not_entry
  // Exit rule references a higher-timeframe feature not used by any entry rule.
  // ------------------------------------------------------------------ §1
  {
    const entryTfs = new Set(entryFeatureRefs(entryRules).map(refTimeframe).filter(Boolean) as string[]);
    const exitRefs = exitFeatureRefs(exitRules);
    const missingHtfRefs = exitRefs.filter((ref) => {
      const tf = refTimeframe(ref);
      return tf !== null && !entryTfs.has(tf);
    });
    if (missingHtfRefs.length > 0) {
      push(
        "htf_in_exit_not_entry",
        "warn",
        "section-logical-exit",
        "Exit references higher-timeframe feature not used by entry — entry may signal without HTF context.",
      );
    }
  }

  // ------------------------------------------------------------------ §2
  // logical_exit_fires_immediately_after_entry
  // A feature_condition exit has a condition identical (feature ref + negated op)
  // to an entry condition AND no time/bars minimum exists in any exit rule.
  // ------------------------------------------------------------------ §2
  {
    // Collect entry condition left_feature refs.
    const entryLeftFeatures = new Set<string>();
    for (const rule of entryRules) {
      for (const ref of refsInCondition(rule.condition ?? null)) {
        entryLeftFeatures.add(ref);
      }
    }

    // Check if any feature_condition exit references the same feature with no hold.
    const hasFeatureExit = buckets.logical.some(
      ({ rule }) => rule.logical_exit_rule?.kind === "feature_condition",
    );
    const exitConditionRefs = exitFeatureRefs(exitRules);
    const overlaps = exitConditionRefs.some((ref) => entryLeftFeatures.has(ref));

    // No time or bars minimum?
    const hasMinimumHold = exitRules.some((rule) => {
      const kind = rule.logical_exit_rule?.kind;
      return kind === "bars_since_entry" || kind === "time_in_position_seconds";
    });

    if (hasFeatureExit && overlaps && !hasMinimumHold) {
      push(
        "logical_exit_fires_immediately_after_entry",
        "error",
        "section-logical-exit",
        "Logical exit can fire immediately after entry. Add a minimum hold (bars or seconds) or change the condition.",
      );
    }
  }

  // ------------------------------------------------------------------ §3
  // stop_target_ratio_nonsensical
  // bracket_stop_target: target_pct / stop_pct < 0.5
  // ------------------------------------------------------------------ §3
  if (preset.kind === "bracket_stop_target") {
    const o = preset.overrides as BracketStopTargetOverrides;
    const stop = o.stop_pct;
    const target = o.target_pct;
    if (stop > 0 && target / stop < 0.5) {
      push(
        "stop_target_ratio_nonsensical",
        "warn",
        "section-stop-plan",
        "Reward/risk ratio looks inverted (target ≤ ½ × stop). Confirm the values are correct.",
      );
    }
  }

  // ------------------------------------------------------------------ §4
  // intraday_no_time_exit
  // scalping or intraday horizon with no time-based exit and no force-flat.
  // ------------------------------------------------------------------ §4
  {
    const horizon = controls?.trading_horizon;
    if (horizon === "scalping" || horizon === "intraday") {
      const hasTimeExit = exitRules.some((rule) => {
        const kind = rule.logical_exit_rule?.kind;
        return kind !== undefined && TIME_BASED_EXIT_KINDS.has(kind);
      });
      // "force-flat" is not part of current preset shapes — treat as absent.
      if (!hasTimeExit) {
        push(
          "intraday_no_time_exit",
          "warn",
          "section-strategy-controls",
          "Intraday strategies usually flatten by end of day. Consider a time-based exit or a force-flat time.",
        );
      }
    }
  }

  // ------------------------------------------------------------------ §5
  // feature_not_supported_for_timeframe
  // A feature ref's timeframe is not in catalog supported_timeframes.
  // ------------------------------------------------------------------ §5
  for (const ref of allRefs) {
    const tf = refTimeframe(ref);
    const kind = refKind(ref);
    if (!tf || !kind) continue;
    const entry = catalogByKind.get(kind);
    if (!entry) continue;
    if (entry.supported_timeframes.length > 0 && !entry.supported_timeframes.includes(tf)) {
      push(
        `feature_not_supported_for_timeframe:${ref}`,
        "error",
        "section-required-features",
        `\`${ref}\` is not supported on \`${tf}\` (supported: \`${entry.supported_timeframes.join(", ")}\`).`,
      );
    }
  }

  // ------------------------------------------------------------------ §6
  // feature_not_executable
  // A feature ref's kind is NOT in supported_consumers for "backtest".
  // ------------------------------------------------------------------ §6
  for (const ref of allRefs) {
    const kind = refKind(ref);
    if (!kind) continue;
    const entry = catalogByKind.get(kind);
    if (!entry) continue;
    if (entry.supported_consumers.length > 0 && !entry.supported_consumers.includes("backtest")) {
      push(
        `feature_not_executable:${ref}`,
        "error",
        "section-required-features",
        `\`${kind}\` is registered but not executable for backtest. Pick a supported feature.`,
      );
    }
  }

  // ------------------------------------------------------------------ §7
  // stop_pct_out_of_range
  // stop_pct <= 0 || stop_pct > 50 for bracket_stop_target or multi_target with stop.
  // ------------------------------------------------------------------ §7
  {
    let stopPct: number | null = null;
    if (preset.kind === "bracket_stop_target") {
      stopPct = (preset.overrides as BracketStopTargetOverrides).stop_pct;
    } else if (preset.kind === "multi_target_scale_out") {
      const o = preset.overrides as MultiTargetScaleOutOverrides;
      stopPct = o.stop_pct;
    }
    if (stopPct !== null && typeof stopPct === "number" && (stopPct <= 0 || stopPct > 50)) {
      push(
        "stop_pct_out_of_range",
        "error",
        "section-stop-plan",
        "Stop must be between 0 and 50 percent.",
      );
    }
  }

  // ------------------------------------------------------------------ §8
  // target_pct_out_of_range
  // bracket_stop_target target_pct <= 0
  // ------------------------------------------------------------------ §8
  if (preset.kind === "bracket_stop_target") {
    const o = preset.overrides as BracketStopTargetOverrides;
    if (o.target_pct <= 0) {
      push(
        "target_pct_out_of_range",
        "error",
        "section-target-plan",
        "Target must be greater than 0.",
      );
    }
  }

  // ------------------------------------------------------------------ §9
  // targets_runner_exceed_100
  // multi_target_scale_out: sum of slice_pct > 1.0
  // ------------------------------------------------------------------ §9
  if (preset.kind === "multi_target_scale_out") {
    const o = preset.overrides as MultiTargetScaleOutOverrides;
    const total = o.targets.reduce((acc, t) => acc + (Number.isFinite(t.slice_pct) ? t.slice_pct : 0), 0);
    if (total > 1.0 + 1e-9) {
      push(
        "targets_runner_exceed_100",
        "error",
        "section-target-plan",
        "Targets + runner total exceeds 100% of position.",
      );
    }
  }

  // ------------------------------------------------------------------ §10
  // targets_below_100_no_runner_no_stop
  // multi_target_scale_out: sum < 1.0 AND stop_pct is null
  // ------------------------------------------------------------------ §10
  if (preset.kind === "multi_target_scale_out") {
    const o = preset.overrides as MultiTargetScaleOutOverrides;
    const total = o.targets.reduce((acc, t) => acc + (Number.isFinite(t.slice_pct) ? t.slice_pct : 0), 0);
    if (total < 1.0 - 1e-9 && (o.stop_pct === null || o.stop_pct === undefined)) {
      push(
        "targets_below_100_no_runner_no_stop",
        "warn",
        "section-target-plan",
        `Targets cover only ${Math.round(total * 100)}% of position; remainder has no exit. Add a runner, a stop, or raise targets.`,
      );
    }
  }

  // ------------------------------------------------------------------ §11
  // short_enabled_no_short_entry
  // allowed_directions is "short" or "both" AND no entry rule has side="short".
  // ------------------------------------------------------------------ §11
  {
    const dir = controls?.allowed_directions;
    if (dir === "short" || dir === "both") {
      const hasShortEntry = entryRules.some((r) => r.side === "short");
      if (!hasShortEntry) {
        push(
          "short_enabled_no_short_entry",
          "error",
          "section-entry-short",
          "Short rules are enabled but no short entry exists. Add a short entry rule or remove short direction.",
        );
      }
    }
  }

  // ------------------------------------------------------------------ §12
  // both_dir_asymmetric_exits
  // allowed_directions="both" AND exit rules exist but none covers both sides.
  // ------------------------------------------------------------------ §12
  {
    const dir = controls?.allowed_directions;
    if (dir === "both" && exitRules.length > 0) {
      const sides = new Set(exitRules.map((r) => r.side));
      const coversLong = sides.has("long");
      const coversShort = sides.has("short");
      if (!coversLong || !coversShort) {
        push(
          "both_dir_asymmetric_exits",
          "warn",
          "section-logical-exit",
          "Strategy trades both sides but exits are asymmetric. Confirm long and short positions both have exit logic.",
        );
      }
    }
  }

  // ------------------------------------------------------------------ §13
  // htf_confirmation_required_but_no_htf_feature
  // higher_timeframe_confirmation_required=true AND no feature ref has a higher timeframe.
  // ------------------------------------------------------------------ §13
  {
    if (controls?.higher_timeframe_confirmation_required) {
      const baseRank = TIMEFRAME_RANK[controls.timeframe] ?? 0;
      const hasHtf = allRefs.some((ref) => {
        const tf = refTimeframe(ref);
        return tf !== null && (TIMEFRAME_RANK[tf] ?? 0) > baseRank;
      });
      if (!hasHtf) {
        push(
          "htf_confirmation_required_but_no_htf_feature",
          "error",
          "section-strategy-controls",
          "HTF confirmation is required, but no higher-timeframe feature is referenced.",
        );
      }
    }
  }

  // ------------------------------------------------------------------ §14
  // time_based_exit_no_unit
  // A time-based exit rule exists but its relevant field is null/undefined/0.
  // ------------------------------------------------------------------ §14
  for (const { rule } of buckets.timeBased) {
    const exit = rule.logical_exit_rule as Record<string, unknown> | null | undefined;
    if (!exit) continue;
    const kind = exit.kind as string | undefined;
    if (!kind || !TIME_BASED_EXIT_KINDS.has(kind)) continue;
    let hasValue = false;
    if (kind === "bars_since_entry") hasValue = typeof exit.bars === "number" && (exit.bars as number) > 0;
    else if (kind === "time_in_position_seconds") hasValue = typeof exit.seconds === "number" && (exit.seconds as number) > 0;
    else if (kind === "time_of_day_et") hasValue = typeof exit.hour === "number";
    else if (kind === "minutes_before_session_close") hasValue = typeof exit.minutes_before_close === "number" && (exit.minutes_before_close as number) > 0;
    else if (kind === "session_window") hasValue = typeof exit.session === "string" && (exit.session as string).length > 0;
    if (!hasValue) {
      push(
        "time_based_exit_no_unit",
        "error",
        "section-time-based-exit",
        "Pick a time-based exit kind (after N minutes, after N bars, at HH:MM ET, or N minutes before close).",
      );
      break; // one error is enough; the per-rule display is in the section
    }
  }

  // ------------------------------------------------------------------ §16
  // cooldown_bars_on_coarse_timeframe
  // cooldown_bars is set on a strategy whose base timeframe is daily or coarser.
  // On 1d+ timeframes, "wait N bars" is N days — almost certainly not the
  // operator's intent. cooldown_minutes is the right unit there.
  // ------------------------------------------------------------------ §16
  {
    const tf = controls?.timeframe;
    const tfRank = tf ? TIMEFRAME_RANK[tf] ?? 0 : 0;
    if (controls?.cooldown_bars != null && tfRank >= TIMEFRAME_RANK["1d"]!) {
      push(
        "cooldown_bars_on_coarse_timeframe",
        "warn",
        "section-strategy-controls",
        `Cooldown bars on a ${tf} strategy means N days between trades. Use cooldown minutes (or hours via 60×) for wall-clock throttling.`,
      );
    }
  }

  // ------------------------------------------------------------------ §15
  // multi_target_slices_below_100 (info — stop IS present)
  // multi_target_scale_out: sum < 1.0 AND stop_pct is NOT null
  // ------------------------------------------------------------------ §15
  if (preset.kind === "multi_target_scale_out") {
    const o = preset.overrides as MultiTargetScaleOutOverrides;
    const total = o.targets.reduce((acc, t) => acc + (Number.isFinite(t.slice_pct) ? t.slice_pct : 0), 0);
    if (total < 1.0 - 1e-9 && o.stop_pct !== null && o.stop_pct !== undefined) {
      push(
        "multi_target_slices_below_100",
        "info",
        "section-target-plan",
        `Scale-out covers ${Math.round(total * 100)}%; remainder is open-ended without a stop.`,
      );
    }
  }

  return warnings;
}

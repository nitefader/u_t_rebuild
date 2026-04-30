import type {
  ExecutionMode,
  ExecutionStylePresetKind,
  LogicalExitRule,
  StrategyControlsVersion,
  StrategyDraft,
} from "@/api/schemas/strategyComposer";
import type { StrategyVersionPayload } from "@/api/schemas/strategies";
import {
  defaultPresetValue,
  type BracketRunnerOverrides,
  type BracketStopTargetOverrides,
  type ExecutionStylePresetValue,
  type ExecutionStyleOverrides,
  type MultiTargetScaleOutOverrides,
  type StopEntryOverrides,
} from "../ExecutionStylePresetRow";
import type { EditorRule } from "../SignalRuleEditor";

/**
 * EditorState — root mutable state of the Page-2 prefilled editor.
 *
 * The wizard generates an immutable `StrategyDraft` (Tier-2 AI output).
 * Page 2 mounts that draft into an `EditorState` the operator can edit
 * directly. Sections receive slices of this state and emit slice changes.
 *
 * Doctrine guards baked in here:
 *   - `draft` is the ONLY save shape. The save flow posts the entire
 *     draft envelope back to /composer/drafts; nothing about preset or
 *     overrides lives outside the draft once we save.
 *   - `preset` is editor-side companion state. Derived initially from
 *     `draft.execution_style.preset`. Changing it updates the draft
 *     execution_style.preset record so a subsequent save carries the
 *     new preset kind and overrides without a Regenerate round-trip.
 *   - We never re-derive `feature_refs` from the UI — that lives on the
 *     saved StrategyVersion and downstream surfaces (Backtest, Sim Lab,
 *     Chart Lab, Walk-Forward, Runtime) read the saved version's refs +
 *     entry/exit conditions, never a parallel UI selection.
 */
export interface EditorState {
  draft: StrategyDraft;
  preset: ExecutionStylePresetValue;
}

/** Editor-side rule classification — operator-facing labels only.
 * Underlying payload is always `LogicalExitRule` (per
 * feedback_logical_exit_is_the_only_exit_intent). The flavor merely
 * routes the rule into the right Page-2 section. */
export const TIME_BASED_EXIT_KINDS = new Set<string>([
  "bars_since_entry",
  "time_in_position_seconds",
  "time_of_day_et",
  "minutes_before_session_close",
  "session_window",
]);

/** Feature-flavor logical exits (and feature-condition / hybrid). */
export const LOGICAL_EXIT_KINDS = new Set<string>([
  "feature_condition",
  "hybrid",
]);

export function editorStateFromDraft(draft: StrategyDraft): EditorState {
  const presetKind = readPresetKind(draft) ?? "market_entry_market_exit";
  let preset = defaultPresetValue(presetKind);
  const overrides = readPresetOverrides(draft, presetKind);
  if (overrides) preset = { ...preset, overrides };
  return { draft, preset };
}

function readPresetKind(draft: StrategyDraft): ExecutionStylePresetKind | null {
  const preset = draft.execution_style.preset as
    | { kind?: string }
    | null
    | undefined;
  const k = preset?.kind;
  if (
    k === "market_entry_market_exit" ||
    k === "stop_entry_market_exit" ||
    k === "bracket_stop_target" ||
    k === "bracket_runner" ||
    k === "multi_target_scale_out"
  ) {
    return k;
  }
  return null;
}

function readPresetOverrides(
  draft: StrategyDraft,
  kind: ExecutionStylePresetKind,
): ExecutionStyleOverrides | null {
  const presetRecord = draft.execution_style.preset as Record<string, unknown> | null | undefined;
  if (!presetRecord) return null;
  const raw = presetRecord.overrides as Record<string, unknown> | undefined;
  if (!raw) return null;
  if (kind === "market_entry_market_exit") return {};
  if (kind === "stop_entry_market_exit") {
    const o = raw as Partial<StopEntryOverrides>;
    return {
      entry_stop_offset_bps: typeof o.entry_stop_offset_bps === "number" ? o.entry_stop_offset_bps : 10,
    };
  }
  if (kind === "bracket_stop_target") {
    const o = raw as Partial<BracketStopTargetOverrides>;
    return {
      stop_pct: typeof o.stop_pct === "number" ? o.stop_pct : 1.0,
      target_pct: typeof o.target_pct === "number" ? o.target_pct : 2.0,
    };
  }
  if (kind === "bracket_runner") {
    const o = raw as Partial<BracketRunnerOverrides>;
    return {
      first_target_pct: typeof o.first_target_pct === "number" ? o.first_target_pct : 1.0,
      first_slice_pct: typeof o.first_slice_pct === "number" ? o.first_slice_pct : 0.5,
      trail_pct: typeof o.trail_pct === "number" ? o.trail_pct : 1.0,
    };
  }
  if (kind === "multi_target_scale_out") {
    const o = raw as Partial<MultiTargetScaleOutOverrides>;
    const targets = Array.isArray(o.targets)
      ? o.targets.map((t) => ({
          target_pct: typeof t.target_pct === "number" ? t.target_pct : 1,
          slice_pct: typeof t.slice_pct === "number" ? t.slice_pct : 0.25,
        }))
      : [];
    return {
      targets:
        targets.length > 0
          ? targets
          : [
              { target_pct: 1.0, slice_pct: 0.25 },
              { target_pct: 2.0, slice_pct: 0.25 },
              { target_pct: 3.0, slice_pct: 0.25 },
              { target_pct: 4.0, slice_pct: 0.25 },
            ],
      stop_pct: typeof o.stop_pct === "number" ? o.stop_pct : null,
    };
  }
  return null;
}

/** Sync the editor's preset value back into the draft.execution_style
 * passthrough record so a save round-trip preserves operator edits. */
export function applyPresetToDraft(state: EditorState, next: ExecutionStylePresetValue): EditorState {
  const presetRecord: Record<string, unknown> = {
    ...((state.draft.execution_style.preset as Record<string, unknown> | null | undefined) ?? {}),
    kind: next.kind,
    overrides: next.overrides,
  };
  return {
    ...state,
    preset: next,
    draft: {
      ...state.draft,
      execution_style: {
        ...state.draft.execution_style,
        preset: presetRecord,
      },
    },
  };
}

/** Mutate the strategy version payload (name / description / tags / rules). */
export function applyStrategyToDraft(
  state: EditorState,
  next: StrategyVersionPayload,
): EditorState {
  return {
    ...state,
    draft: { ...state.draft, strategy: next },
  };
}

/** Mutate the strategy controls. */
export function applyStrategyControlsToDraft(
  state: EditorState,
  next: StrategyControlsVersion | null,
): EditorState {
  return {
    ...state,
    draft: { ...state.draft, strategy_controls: next },
  };
}

/** Read the operator-selected ExecutionMode (post_fill_bracket default). */
export function readExecutionMode(state: EditorState): ExecutionMode {
  const raw = (state.draft.execution_style as { execution_mode?: unknown }).execution_mode;
  if (raw === "post_fill_bracket" || raw === "native_alpaca_bracket") return raw;
  return "post_fill_bracket";
}

/** Mutate the ExecutionPlan's execution_mode (post-fill bracket vs native). */
export function applyExecutionModeToDraft(
  state: EditorState,
  next: ExecutionMode,
): EditorState {
  return {
    ...state,
    draft: {
      ...state.draft,
      execution_style: {
        ...state.draft.execution_style,
        execution_mode: next,
      },
    },
  };
}

/** Editor-side helpers that classify exit rules into "logical" vs "time-based"
 * sections. Both serialize to a single `LogicalExitRule` payload — this is
 * pure presentation logic for the editor. */
export interface ExitRuleBucket {
  logical: ExitRuleEntry[];
  timeBased: ExitRuleEntry[];
}

export interface ExitRuleEntry {
  rule: EditorRule;
  index: number;
}

export function bucketExitRules(rules: EditorRule[]): ExitRuleBucket {
  const logical: ExitRuleEntry[] = [];
  const timeBased: ExitRuleEntry[] = [];
  rules.forEach((rule, index) => {
    const kind = rule.logical_exit_rule?.kind;
    if (kind && TIME_BASED_EXIT_KINDS.has(kind)) {
      timeBased.push({ rule, index });
    } else {
      logical.push({ rule, index });
    }
  });
  return { logical, timeBased };
}

/** Walk every condition inside a rule's condition tree and a rule's
 * logical_exit_rule (recursing through hybrid children) and return all
 * referenced features in document order. Used by RequiredFeaturesSection
 * to render the derived read-only feature list. */
export function collectAllFeatureRefs(payload: StrategyVersionPayload): string[] {
  const out = new Set<string>();
  for (const r of payload.feature_refs ?? []) {
    if (r) out.add(r);
  }
  for (const rule of [...(payload.entry_rules ?? []), ...(payload.exit_rules ?? [])]) {
    walkRule(rule as EditorRule, out);
  }
  return Array.from(out);
}

function walkRule(rule: EditorRule, out: Set<string>): void {
  walkCondition(rule.condition ?? null, out);
  if (rule.stop_candidate_feature) out.add(rule.stop_candidate_feature);
  if (rule.target_candidate_feature) out.add(rule.target_candidate_feature);
  walkLogicalExit(rule.logical_exit_rule ?? null, out);
}

function walkCondition(expr: unknown, out: Set<string>): void {
  if (!expr || typeof expr !== "object") return;
  const node = expr as { kind?: string; left_feature?: string; right_feature?: string; children?: unknown[] };
  if (node.kind === "group") {
    (node.children ?? []).forEach((c) => walkCondition(c, out));
    return;
  }
  if (typeof node.left_feature === "string" && node.left_feature) out.add(node.left_feature);
  if (typeof node.right_feature === "string" && node.right_feature) out.add(node.right_feature);
}

function walkLogicalExit(rule: LogicalExitRule | null | undefined, out: Set<string>): void {
  if (!rule) return;
  if (rule.kind === "feature_condition") {
    walkCondition(rule.feature_condition, out);
  }
  if (rule.kind === "hybrid") {
    for (const child of (rule.children ?? []) as LogicalExitRule[]) {
      walkLogicalExit(child, out);
    }
  }
}

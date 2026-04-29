import { z } from "zod";
import {
  ConditionGroupSchema,
  ConditionNodeSchema,
  StrategyVersionPayloadSchema,
  type StrategyVersionPayload,
} from "./strategies";

/**
 * Schemas for the Strategy Builder + AI Composer endpoints.
 *
 * Contract source: docs/system_rebuild_outputs/STRATEGY_BUILDER_FRONTEND_CONTRACT.md
 *
 * Doctrine reminders enforced by the typed shapes here:
 *   - Strategy Builder is draft-only.
 *   - Strategy does NOT own Risk.
 *   - Strategy does NOT own Universe.
 *   - LogicalExitRule is the only typed exit-rule shape — time / bars / session /
 *     feature / hybrid all live under one of the seven kinds, never as a sibling
 *     top-level intent.
 *
 * All envelopes use `.passthrough()` so additive backend fields never reject
 * the typed client (per the contract's "Frontend schemas should use typed
 * core fields with .passthrough() so additive backend fields do not break
 * the UI" rule).
 */

// ---------- Feature catalog ---------------------------------------------------

export const FeatureCatalogItemSchema = z
  .object({
    kind: z.string(),
    display_name: z.string().nullable().optional(),
    namespace: z.string().default("other"),
    scope: z.string().default("symbol"),
    source: z.string().default(""),
    allowed_params: z.array(z.string()).default([]),
    default_params: z.record(z.union([z.string(), z.number(), z.boolean()])).default({}),
    supported_timeframes: z.array(z.string()).default([]),
    supported_consumers: z.array(z.string()).default([]),
    supported_modes: z.array(z.string()).default([]),
    example_refs: z.array(z.string()).default([]),
    description: z.string().nullable().optional(),
  })
  .passthrough();
export type FeatureCatalogItem = z.infer<typeof FeatureCatalogItemSchema>;

export const FeatureCatalogResponseSchema = z.array(FeatureCatalogItemSchema);

export const FeatureAliasMapSchema = z.record(z.string());
export type FeatureAliasMap = z.infer<typeof FeatureAliasMapSchema>;

// ---------- Feature reference validation -------------------------------------

export const FeatureReferenceValidationItemSchema = z
  .object({
    input: z.string(),
    valid: z.boolean(),
    normalized_ref: z.string().nullable().optional(),
    feature_key: z.string().nullable().optional(),
    display_name: z.string().nullable().optional(),
    error_code: z.string().nullable().optional(),
    message: z.string().nullable().optional(),
  })
  .passthrough();
export type FeatureReferenceValidationItem = z.infer<
  typeof FeatureReferenceValidationItemSchema
>;

export const FeatureReferenceValidationSchema = z
  .object({
    valid: z.boolean(),
    errors: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    items: z.array(FeatureReferenceValidationItemSchema).default([]),
    normalized_feature_refs: z.array(z.string()).default([]),
  })
  .passthrough();
export type FeatureReferenceValidation = z.infer<typeof FeatureReferenceValidationSchema>;

export const FeatureReferenceValidationRequestSchema = z.object({
  feature_refs: z.array(z.string()),
  consumer: z.string().optional(),
});
export type FeatureReferenceValidationRequest = z.infer<
  typeof FeatureReferenceValidationRequestSchema
>;

// ---------- Feature plan preview ---------------------------------------------

export const FeaturePlanPreviewSchema = z
  .object({
    valid: z.boolean(),
    errors: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    feature_keys: z.array(z.string()).default([]),
    normalized_feature_refs: z.array(z.string()).default([]),
    warmup_by_timeframe: z.record(z.number()).default({}),
  })
  .passthrough();
export type FeaturePlanPreview = z.infer<typeof FeaturePlanPreviewSchema>;

export const FeaturePlanPreviewRequestSchema = z.object({
  feature_refs: z.array(z.string()),
  consumer: z.string().optional(),
});
export type FeaturePlanPreviewRequest = z.infer<typeof FeaturePlanPreviewRequestSchema>;

// ---------- LogicalExitRule (the seven kinds) --------------------------------

export const LogicalExitRuleKindSchema = z.enum([
  "feature_condition",
  "bars_since_entry",
  "time_in_position_seconds",
  "time_of_day_et",
  "minutes_before_session_close",
  "session_window",
  "hybrid",
]);
export type LogicalExitRuleKind = z.infer<typeof LogicalExitRuleKindSchema>;

export const LogicalExitHybridOperatorSchema = z.enum(["all", "any"]);

const conditionExpression: z.ZodTypeAny = z.lazy(() =>
  z.union([ConditionNodeSchema, ConditionGroupSchema]),
);

// Recursive — hybrid kind nests child rules.
export const LogicalExitRuleSchema: z.ZodTypeAny = z.lazy(() =>
  z
    .object({
      kind: LogicalExitRuleKindSchema,
      // feature_condition
      feature_condition: conditionExpression.optional(),
      // bars_since_entry
      bars: z.number().int().nullable().optional(),
      // time_in_position_seconds
      seconds: z.number().int().nullable().optional(),
      // time_of_day_et
      hour: z.number().int().nullable().optional(),
      minute: z.number().int().nullable().optional(),
      // minutes_before_session_close
      minutes_before_close: z.number().int().nullable().optional(),
      // session_window
      session: z.string().nullable().optional(),
      // hybrid
      operator: LogicalExitHybridOperatorSchema.optional(),
      children: z.array(LogicalExitRuleSchema).optional(),
      label: z.string().nullable().optional(),
    })
    .passthrough(),
);
export type LogicalExitRule = z.infer<typeof LogicalExitRuleSchema>;

// ---------- Condition + LogicalExit parse ------------------------------------

export const ConditionParseResponseSchema = z
  .object({
    valid: z.boolean(),
    errors: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    normalized_condition: conditionExpression.nullable().optional(),
    normalized_logical_exit_rule: LogicalExitRuleSchema.nullable().optional(),
  })
  .passthrough();
export type ConditionParseResponse = z.infer<typeof ConditionParseResponseSchema>;

export const ConditionParseRequestSchema = z
  .object({
    condition: conditionExpression.optional(),
    logical_exit_rule: LogicalExitRuleSchema.optional(),
    consumer: z.string().optional(),
  })
  .refine(
    (req) => Boolean(req.condition) || Boolean(req.logical_exit_rule),
    { message: "condition or logical_exit_rule is required" },
  );
export type ConditionParseRequest = z.infer<typeof ConditionParseRequestSchema>;

// ---------- Reuse matches ----------------------------------------------------

export const StrategyDraftComponentMatchSchema = z
  .object({
    component_kind: z.string(),
    name: z.string().nullable().optional(),
    score: z.number().nullable().optional(),
    reason: z.string().nullable().optional(),
    component_id: z.string().nullable().optional(),
    payload: z.record(z.unknown()).nullable().optional(),
  })
  .passthrough();
export type StrategyDraftComponentMatch = z.infer<typeof StrategyDraftComponentMatchSchema>;

export const ReuseMatchResponseSchema = z
  .object({
    risk_plan: z.array(StrategyDraftComponentMatchSchema).default([]),
    execution_style: z.array(StrategyDraftComponentMatchSchema).default([]),
    universe: z.array(StrategyDraftComponentMatchSchema).default([]),
    watchlist: z.array(StrategyDraftComponentMatchSchema).default([]),
    screener: z.array(StrategyDraftComponentMatchSchema).default([]),
  })
  .passthrough();
export type ReuseMatchResponse = z.infer<typeof ReuseMatchResponseSchema>;

export const ReuseMatchRequestSchema = z
  .object({
    name: z.string().optional(),
    feature_refs: z.array(z.string()).default([]),
    tags: z.array(z.string()).default([]),
    description: z.string().nullable().optional(),
  })
  .passthrough();
export type ReuseMatchRequest = z.infer<typeof ReuseMatchRequestSchema>;

// ---------- StrategyDraft (composer preview / save) --------------------------

export const StrategyDraftValidationSchema = z
  .object({
    valid: z.boolean(),
    errors: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    normalized_feature_refs: z.array(z.string()).default([]),
    feature_plan_preview: FeaturePlanPreviewSchema.nullable().optional(),
  })
  .passthrough();
export type StrategyDraftValidation = z.infer<typeof StrategyDraftValidationSchema>;

export const StrategyDraftLaunchPlanSchema = z
  .object({
    surface: z.string(),
    method: z.string(),
    route: z.string(),
    request: z.record(z.unknown()).default({}),
    ready: z.boolean().default(false),
    missing_fields: z.array(z.string()).default([]),
  })
  .passthrough();
export type StrategyDraftLaunchPlan = z.infer<typeof StrategyDraftLaunchPlanSchema>;

export const StrategyDraftLaunchPlansSchema = z
  .object({
    chart_lab: StrategyDraftLaunchPlanSchema.nullable().optional(),
    backtest: StrategyDraftLaunchPlanSchema.nullable().optional(),
    walk_forward: StrategyDraftLaunchPlanSchema.nullable().optional(),
  })
  .passthrough();
export type StrategyDraftLaunchPlans = z.infer<typeof StrategyDraftLaunchPlansSchema>;

export const StrategyDraftBacktestPlanSchema = z
  .object({
    symbols: z.array(z.string()).default([]),
    timeframe: z.string().nullable().optional(),
    initial_capital: z.number().nullable().optional(),
    cost_model: z.unknown().nullable().optional(),
  })
  .passthrough();
export type StrategyDraftBacktestPlan = z.infer<typeof StrategyDraftBacktestPlanSchema>;

// ---------- ExecutionStylePresetKind (5 locked presets) ----------------------

export const ExecutionStylePresetKindSchema = z.enum([
  "market_entry_market_exit",
  "stop_entry_market_exit",
  "bracket_stop_target",
  "bracket_runner",
  "multi_target_scale_out",
]);
export type ExecutionStylePresetKind = z.infer<typeof ExecutionStylePresetKindSchema>;

// ---------- WizardIntent + Strategy Controls (Slice 6a-i) --------------------

export const TradingHorizonSchema = z.enum(["scalping", "intraday", "swing", "position"]);
export type TradingHorizon = z.infer<typeof TradingHorizonSchema>;

export const AllowedDirectionsSchema = z.enum(["long", "short", "both"]);
export type AllowedDirections = z.infer<typeof AllowedDirectionsSchema>;

export const SessionPreferenceSchema = z.enum(["regular_only", "regular_and_extended"]);
export type SessionPreference = z.infer<typeof SessionPreferenceSchema>;

/**
 * Page-1 wizard checkboxes — what the operator declared up front before AI.
 * Mirrors backend `WizardIntent` (extra="forbid"; do not add fields casually).
 */
export const WizardIntentSchema = z
  .object({
    direction: AllowedDirectionsSchema.default("long"),
    horizon: TradingHorizonSchema.default("intraday"),
    base_timeframe: z.string().default("5m"),
    higher_timeframe_confirmation: z.boolean().default(false),
    has_stop: z.boolean().default(true),
    has_target: z.boolean().default(false),
    has_multiple_targets: z.boolean().default(false),
    has_runner: z.boolean().default(false),
    has_logical_exit: z.boolean().default(true),
    has_time_based_exit: z.boolean().default(false),
  })
  .passthrough();
export type WizardIntent = z.infer<typeof WizardIntentSchema>;

export const StrategyControlsVersionSchema = z
  .object({
    id: z.string(),
    strategy_controls_id: z.string(),
    version: z.number(),
    name: z.string(),
    timeframe: z.string(),
    trading_horizon: TradingHorizonSchema.default("intraday"),
    allowed_directions: AllowedDirectionsSchema.default("long"),
    higher_timeframe_confirmation_required: z.boolean().default(false),
    session_preference: SessionPreferenceSchema.default("regular_only"),
    earnings_news_blackout_enabled: z.boolean().default(false),
  })
  .passthrough();
export type StrategyControlsVersion = z.infer<typeof StrategyControlsVersionSchema>;

// ---------- ExecutionStyleVersion (passthrough; UI reads .preset.kind only) --

export const ExecutionStyleVersionSchema = z
  .object({
    id: z.string(),
    execution_style_id: z.string(),
    version: z.number(),
    name: z.string(),
    entry_order_type: z.string(),
    exit_order_type: z.string().optional(),
    time_in_force: z.string().optional(),
    entry_limit_offset_bps: z.number().nullable().optional(),
    cancel_after_bars: z.number().nullable().optional(),
    bracket: z.record(z.unknown()).nullable().optional(),
    trailing_stop_enabled: z.boolean().optional(),
    scale_out_enabled: z.boolean().optional(),
    feature_refs: z.array(z.string()).default([]),
    preset: z.record(z.unknown()).nullable().optional(),
    created_at: z.string().optional(),
  })
  .passthrough();
export type ExecutionStyleVersion = z.infer<typeof ExecutionStyleVersionSchema>;

// ---------- StrategyDraft (composer preview / save) --------------------------

export const StrategyDraftSchema = z
  .object({
    draft_id: z.string().nullable().optional(),
    prompt: z.string().nullable().optional(),
    strategy: StrategyVersionPayloadSchema,
    strategy_controls: StrategyControlsVersionSchema.nullable().optional(),
    execution_style: ExecutionStyleVersionSchema,
    backtest_plan: StrategyDraftBacktestPlanSchema,
    launch_plans: StrategyDraftLaunchPlansSchema,
    signal_plan_shape: z.record(z.unknown()).nullable().optional(),
    validation: StrategyDraftValidationSchema,
  })
  .passthrough();
export type StrategyDraft = z.infer<typeof StrategyDraftSchema>;

// ---------- Composer endpoints -----------------------------------------------

export const AIComposerRequestSchema = z
  .object({
    prompt: z.string().min(1),
    timeframe: z.string().default("5m"),
    initial_capital: z.number().positive().default(100_000),
    feature_refs: z.array(z.string()).default([]),
    execution_style_preset: ExecutionStylePresetKindSchema.default("market_entry_market_exit"),
    execution_style_overrides: z.record(z.unknown()).nullable().optional(),
    wizard_intent: WizardIntentSchema.nullable().optional(),
  })
  .passthrough();
export type AIComposerRequest = z.infer<typeof AIComposerRequestSchema>;

export const StrategyDraftSaveRequestSchema = z
  .object({
    draft: StrategyDraftSchema,
  })
  .passthrough();
export type StrategyDraftSaveRequest = z.infer<typeof StrategyDraftSaveRequestSchema>;

// StrategyVersionRecord is what the save endpoint nests under
// `strategy_version`; its `payload` field carries the persisted
// StrategyVersion. Frontend navigates via `.strategy_id` after save.
export const StrategyVersionRecordSchema = z
  .object({
    strategy_version_id: z.string(),
    strategy_id: z.string(),
    version: z.number(),
    status: z.string(),
    payload: StrategyVersionPayloadSchema,
    frozen_at: z.string().nullable().optional(),
    frozen_by: z.string().nullable().optional(),
    created_at: z.string().optional(),
  })
  .passthrough();
export type StrategyVersionRecord = z.infer<typeof StrategyVersionRecordSchema>;

export const StrategyDraftComponentSnapshotsSchema = z
  .object({
    execution_style: ExecutionStyleVersionSchema,
    backtest_plan: StrategyDraftBacktestPlanSchema,
    launch_plans: StrategyDraftLaunchPlansSchema,
  })
  .passthrough();
export type StrategyDraftComponentSnapshots = z.infer<
  typeof StrategyDraftComponentSnapshotsSchema
>;

export const StrategyDraftSaveResponseSchema = z
  .object({
    strategy_version: StrategyVersionRecordSchema,
    draft: StrategyDraftSchema,
    component_version_snapshots: StrategyDraftComponentSnapshotsSchema,
    deployment_created: z.boolean().default(false),
    broker_action_created: z.boolean().default(false),
    live_readiness_claimed: z.boolean().default(false),
  })
  .passthrough();
export type StrategyDraftSaveResponse = z.infer<typeof StrategyDraftSaveResponseSchema>;

// ---------- Re-exports for convenience ---------------------------------------

export type { StrategyVersionPayload };

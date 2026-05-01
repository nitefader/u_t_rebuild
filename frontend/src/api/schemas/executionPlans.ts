import { z } from "zod";

// ------------------------------------------------------------------
// Enums
// ------------------------------------------------------------------

export const OrderTypeSchema = z.enum(["market", "limit", "stop", "stop_limit"]);
export type OrderType = z.infer<typeof OrderTypeSchema>;

export const TimeInForceSchema = z.enum(["day", "gtc", "ioc", "fok"]);
export type TimeInForce = z.infer<typeof TimeInForceSchema>;

export const ExecutionModeSchema = z.enum([
  "post_fill_bracket",
  "native_alpaca_bracket",
]);

export const OrderRetryPolicySchema = z.enum([
  "none",
  "reprice_once",
  "reprice_until_filled",
]);
export type OrderRetryPolicy = z.infer<typeof OrderRetryPolicySchema>;

export const OrderCancelPolicySchema = z.enum([
  "hold",
  "cancel_on_opposite_signal",
  "cancel_after_bars",
]);
export type OrderCancelPolicy = z.infer<typeof OrderCancelPolicySchema>;
export type ExecutionMode = z.infer<typeof ExecutionModeSchema>;

export const ExecutionStylePresetKindSchema = z.enum([
  "market_entry_market_exit",
  "stop_entry_market_exit",
  "bracket_stop_target",
  "bracket_runner",
  "multi_target_scale_out",
]);
export type ExecutionStylePresetKind = z.infer<typeof ExecutionStylePresetKindSchema>;

// ------------------------------------------------------------------
// BracketSpec
// ------------------------------------------------------------------

export const BracketSpecSchema = z.object({
  enabled: z.boolean().default(false),
  take_profit_r_multiple: z.number().nullable().optional(),
  stop_loss_r_multiple: z.number().nullable().optional(),
});
export type BracketSpec = z.infer<typeof BracketSpecSchema>;

// ------------------------------------------------------------------
// Preset discriminated union (read model)
// ------------------------------------------------------------------

export const MarketEntryMarketExitPresetSchema = z.object({
  kind: z.literal("market_entry_market_exit"),
});

export const StopEntryMarketExitPresetSchema = z.object({
  kind: z.literal("stop_entry_market_exit"),
  entry_stop_offset_bps: z.number().default(10.0),
});

export const BracketStopTargetPresetSchema = z.object({
  kind: z.literal("bracket_stop_target"),
  stop_pct: z.number().default(1.0),
  target_pct: z.number().default(2.0),
});

export const BracketRunnerPresetSchema = z.object({
  kind: z.literal("bracket_runner"),
  first_target_pct: z.number().default(1.0),
  first_slice_pct: z.number().default(0.5),
  trail_pct: z.number().default(1.0),
});

export const MultiTargetTierSchema = z.object({
  target_pct: z.number(),
  slice_pct: z.number(),
});

export const MultiTargetScaleOutPresetSchema = z.object({
  kind: z.literal("multi_target_scale_out"),
  targets: z.array(MultiTargetTierSchema),
  stop_pct: z.number().nullable().optional(),
});

export const ExecutionStylePresetSpecSchema = z.discriminatedUnion("kind", [
  MarketEntryMarketExitPresetSchema,
  StopEntryMarketExitPresetSchema,
  BracketStopTargetPresetSchema,
  BracketRunnerPresetSchema,
  MultiTargetScaleOutPresetSchema,
]);
export type ExecutionStylePresetSpec = z.infer<typeof ExecutionStylePresetSpecSchema>;

// ------------------------------------------------------------------
// Draft (write model)
// ------------------------------------------------------------------

export const ExecutionPlanDraftSchema = z.object({
  name: z.string().min(1).max(120),
  entry_order_type: OrderTypeSchema.default("market"),
  exit_order_type: OrderTypeSchema.default("market"),
  time_in_force: TimeInForceSchema.default("day"),
  entry_limit_offset_bps: z.number().nullable().optional(),
  cancel_after_bars: z.number().int().nullable().optional(),
  bracket: BracketSpecSchema.default({ enabled: false }),
  execution_mode: ExecutionModeSchema.default("post_fill_bracket"),
  trailing_stop_enabled: z.boolean().default(false),
  scale_out_enabled: z.boolean().default(false),
  order_retry_policy: OrderRetryPolicySchema.default("none"),
  order_cancel_policy: OrderCancelPolicySchema.default("hold"),
  order_retry_max_attempts: z.number().int().min(1).nullable().optional(),
  order_retry_offset_bps: z.number().min(0).nullable().optional(),
  feature_refs: z.array(z.string()).default([]),
  preset: ExecutionStylePresetSpecSchema.nullable().optional(),
});
export type ExecutionPlanDraft = z.infer<typeof ExecutionPlanDraftSchema>;

// ------------------------------------------------------------------
// Domain version (payload inside records)
// ------------------------------------------------------------------

export const ExecutionPlanVersionSchema = z
  .object({
    id: z.string(),
    execution_style_id: z.string(),
    version: z.number().int(),
    name: z.string(),
    entry_order_type: OrderTypeSchema,
    exit_order_type: OrderTypeSchema,
    time_in_force: TimeInForceSchema,
    entry_limit_offset_bps: z.number().nullable().optional(),
    cancel_after_bars: z.number().nullable().optional(),
    bracket: BracketSpecSchema,
    execution_mode: ExecutionModeSchema,
    trailing_stop_enabled: z.boolean(),
    scale_out_enabled: z.boolean(),
    order_retry_policy: OrderRetryPolicySchema.default("none"),
    order_cancel_policy: OrderCancelPolicySchema.default("hold"),
    order_retry_max_attempts: z.number().int().nullable().optional(),
    order_retry_offset_bps: z.number().nullable().optional(),
    feature_refs: z.array(z.string()).default([]),
    preset: ExecutionStylePresetSpecSchema.nullable().optional(),
    created_at: z.string(),
  })
  .passthrough();
export type ExecutionPlanVersion = z.infer<typeof ExecutionPlanVersionSchema>;

// ------------------------------------------------------------------
// Persistence record
// ------------------------------------------------------------------

export const ExecutionPlanVersionRecordSchema = z
  .object({
    payload: ExecutionPlanVersionSchema,
    saved_at: z.string(),
  })
  .passthrough();
export type ExecutionPlanVersionRecord = z.infer<typeof ExecutionPlanVersionRecordSchema>;

// ------------------------------------------------------------------
// Library summary (list row)
// ------------------------------------------------------------------

export const ExecutionPlanLibrarySummarySchema = z
  .object({
    execution_plan_id: z.string(),
    name: z.string(),
    head_version_id: z.string().optional(),
    head_version_number: z.number().int(),
    is_default: z.boolean(),
    retired_at: z.string().nullable(),
    usage_count: z.number().int(),
  })
  .passthrough();
export type ExecutionPlanLibrarySummary = z.infer<typeof ExecutionPlanLibrarySummarySchema>;

export const ExecutionPlanLibraryListResponseSchema = z
  .object({
    libraries: z.array(ExecutionPlanLibrarySummarySchema).default([]),
  })
  .passthrough();
export type ExecutionPlanLibraryListResponse = z.infer<
  typeof ExecutionPlanLibraryListResponseSchema
>;

// ------------------------------------------------------------------
// Version summary (history entry)
// ------------------------------------------------------------------

export const ExecutionPlanVersionSummarySchema = z
  .object({
    version_id: z.string(),
    version: z.number().int(),
    saved_at: z.string(),
  })
  .passthrough();
export type ExecutionPlanVersionSummary = z.infer<typeof ExecutionPlanVersionSummarySchema>;

// ------------------------------------------------------------------
// Full library detail
// ------------------------------------------------------------------

export const ExecutionPlanLibrarySchema = z
  .object({
    execution_plan_id: z.string(),
    name: z.string(),
    is_default: z.boolean(),
    retired_at: z.string().nullable(),
    head: ExecutionPlanVersionRecordSchema,
    history: z.array(ExecutionPlanVersionSummarySchema).default([]),
  })
  .passthrough();
export type ExecutionPlanLibrary = z.infer<typeof ExecutionPlanLibrarySchema>;

// ------------------------------------------------------------------
// used-by response
// ------------------------------------------------------------------

export const ExecutionPlanUsedByResponseSchema = z
  .object({
    deployment_ids: z.array(z.string()).default([]),
  })
  .passthrough();
export type ExecutionPlanUsedByResponse = z.infer<typeof ExecutionPlanUsedByResponseSchema>;

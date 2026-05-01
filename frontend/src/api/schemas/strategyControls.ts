import { z } from "zod";

// ------------------------------------------------------------------
// Enums
// ------------------------------------------------------------------

export const WeekdaySchema = z.enum(["MON", "TUE", "WED", "THU", "FRI"]);
export type Weekday = z.infer<typeof WeekdaySchema>;

export const TradingHorizonSchema = z.enum([
  "scalping",
  "intraday",
  "swing",
  "position",
  "other",
]);
export type TradingHorizon = z.infer<typeof TradingHorizonSchema>;

export const AllowedDirectionsSchema = z.enum(["long", "short", "both"]);
export type AllowedDirections = z.infer<typeof AllowedDirectionsSchema>;

export const SessionPreferenceSchema = z.enum([
  "regular_only",
  "regular_and_extended",
]);
export type SessionPreference = z.infer<typeof SessionPreferenceSchema>;

export const SessionNameSchema = z.enum([
  "premarket",
  "regular",
  "after_hours",
]);
export type SessionName = z.infer<typeof SessionNameSchema>;

// ------------------------------------------------------------------
// SessionWindow
// ------------------------------------------------------------------

export const SessionWindowSchema = z.object({
  session: SessionNameSchema,
  start: z.string(),
  end: z.string(),
});
export type SessionWindow = z.infer<typeof SessionWindowSchema>;

// ------------------------------------------------------------------
// Draft (write model)
// ------------------------------------------------------------------

export const StrategyControlsDraftSchema = z.object({
  name: z.string().min(1).max(120),
  timeframe: z.string().min(1),
  allowed_directions: AllowedDirectionsSchema.default("long"),
  higher_timeframe_confirmation_required: z.boolean().default(false),
  session_preference: SessionPreferenceSchema.default("regular_only"),
  session_windows: z.array(SessionWindowSchema).default([]),
  avoid_first_minutes: z.number().int().min(0).nullable().optional(),
  no_new_entries_after: z.string().nullable().optional(),
  force_flat_by: z.string().nullable().optional(),
  time_based_exit_after_bars: z.number().int().min(1).nullable().optional(),
  time_based_exit_after_minutes: z.number().int().min(1).nullable().optional(),
  time_based_exit_after_days: z.number().int().min(1).nullable().optional(),
  cooldown_bars: z.number().int().min(0).nullable().optional(),
  cooldown_minutes: z.number().int().min(0).nullable().optional(),
  max_trades_per_session: z.number().int().min(1).nullable().optional(),
  max_trades_per_day: z.number().int().min(1).nullable().optional(),
  earnings_news_blackout_enabled: z.boolean().default(false),
  max_consecutive_losses_halt: z.number().int().min(1).nullable().optional(),
  skip_power_hour: z.boolean().default(false),
  day_of_week_restrictions: z.array(WeekdaySchema).default([]),
  feature_refs: z.array(z.string()).default([]),
  regime_filter_refs: z.array(z.string()).default([]),
});
export type StrategyControlsDraft = z.infer<typeof StrategyControlsDraftSchema>;

// ------------------------------------------------------------------
// Domain version (payload inside records)
// ------------------------------------------------------------------

export const StrategyControlsVersionSchema = z
  .object({
    id: z.string(),
    strategy_controls_id: z.string(),
    version: z.number().int(),
    name: z.string(),
    timeframe: z.string(),
    allowed_directions: AllowedDirectionsSchema,
    higher_timeframe_confirmation_required: z.boolean(),
    session_preference: SessionPreferenceSchema,
    session_windows: z.array(SessionWindowSchema).default([]),
    avoid_first_minutes: z.number().nullable().optional(),
    no_new_entries_after: z.string().nullable().optional(),
    force_flat_by: z.string().nullable().optional(),
    time_based_exit_after_bars: z.number().nullable().optional(),
    time_based_exit_after_minutes: z.number().nullable().optional(),
    time_based_exit_after_days: z.number().nullable().optional(),
    cooldown_bars: z.number().nullable().optional(),
    cooldown_minutes: z.number().nullable().optional(),
    max_trades_per_session: z.number().nullable().optional(),
    max_trades_per_day: z.number().nullable().optional(),
    earnings_news_blackout_enabled: z.boolean(),
    max_consecutive_losses_halt: z.number().int().nullable().optional(),
    skip_power_hour: z.boolean().default(false),
    day_of_week_restrictions: z.array(WeekdaySchema).default([]),
    feature_refs: z.array(z.string()).default([]),
    regime_filter_refs: z.array(z.string()).default([]),
    created_at: z.string(),
  })
  .passthrough();
export type StrategyControlsVersion = z.infer<typeof StrategyControlsVersionSchema>;

// ------------------------------------------------------------------
// Persistence record
// ------------------------------------------------------------------

export const StrategyControlsVersionRecordSchema = z
  .object({
    payload: StrategyControlsVersionSchema,
    saved_at: z.string(),
  })
  .passthrough();
export type StrategyControlsVersionRecord = z.infer<
  typeof StrategyControlsVersionRecordSchema
>;

// ------------------------------------------------------------------
// Library summary (list row)
// ------------------------------------------------------------------

export const StrategyControlsLibrarySummarySchema = z
  .object({
    strategy_controls_id: z.string(),
    name: z.string(),
    head_version_id: z.string().optional(),
    head_version_number: z.number().int(),
    is_default: z.boolean(),
    retired_at: z.string().nullable(),
    usage_count: z.number().int(),
  })
  .passthrough();
export type StrategyControlsLibrarySummary = z.infer<
  typeof StrategyControlsLibrarySummarySchema
>;

export const StrategyControlsLibraryListResponseSchema = z
  .object({
    libraries: z.array(StrategyControlsLibrarySummarySchema).default([]),
  })
  .passthrough();
export type StrategyControlsLibraryListResponse = z.infer<
  typeof StrategyControlsLibraryListResponseSchema
>;

// ------------------------------------------------------------------
// Version summary (history entry)
// ------------------------------------------------------------------

export const StrategyControlsVersionSummarySchema = z
  .object({
    version_id: z.string(),
    version: z.number().int(),
    saved_at: z.string(),
  })
  .passthrough();
export type StrategyControlsVersionSummary = z.infer<
  typeof StrategyControlsVersionSummarySchema
>;

// ------------------------------------------------------------------
// Full library detail
// ------------------------------------------------------------------

export const StrategyControlsLibrarySchema = z
  .object({
    strategy_controls_id: z.string(),
    name: z.string(),
    is_default: z.boolean(),
    retired_at: z.string().nullable(),
    head: StrategyControlsVersionRecordSchema,
    history: z.array(StrategyControlsVersionSummarySchema).default([]),
  })
  .passthrough();
export type StrategyControlsLibrary = z.infer<typeof StrategyControlsLibrarySchema>;

// ------------------------------------------------------------------
// used-by response
// ------------------------------------------------------------------

export const StrategyControlsUsedByResponseSchema = z
  .object({
    deployment_ids: z.array(z.string()).default([]),
  })
  .passthrough();
export type StrategyControlsUsedByResponse = z.infer<
  typeof StrategyControlsUsedByResponseSchema
>;

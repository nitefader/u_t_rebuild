import { z } from "zod";

export const ChartLabHealthSchema = z.object({
  streaming_enabled: z.boolean(),
  test_stream: z.boolean(),
  default_symbol: z.string(),
  data_feed: z.string(),
  websocket_path: z.string(),
  routing_note: z.string().default(""),
});
export type ChartLabHealth = z.infer<typeof ChartLabHealthSchema>;

export const ChartBarSchema = z
  .object({
    symbol: z.string(),
    timeframe: z.string().optional(),
    timestamp: z.string(),
    open: z.number(),
    high: z.number(),
    low: z.number(),
    close: z.number(),
    volume: z.number().nullable().optional(),
  })
  .passthrough();
export type ChartBar = z.infer<typeof ChartBarSchema>;

export const ChartLabFrameSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("ready"), symbol: z.string(), test_stream: z.boolean().optional() }),
  z.object({ type: z.literal("bar"), data: ChartBarSchema }),
  z.object({ type: z.literal("error"), code: z.string() }),
]);
export type ChartLabFrame = z.infer<typeof ChartLabFrameSchema>;

// ──────────────────────────────────────────────────────────────────────────
// Strategy preview (POST /api/v1/chart-lab/preview).
// Deployment-like research surface: replay a saved StrategyVersion with
// Strategy Control, Execution Plan, Risk Plan, symbol, and Data Policy.
// ──────────────────────────────────────────────────────────────────────────

export const FeatureAvailabilitySchema = z.enum([
  "available",
  "warmup",
  "missing",
  "unsupported",
]);
export type FeatureAvailability = z.infer<typeof FeatureAvailabilitySchema>;

export const ChartLabFeatureValueSchema = z.object({
  feature_key: z.string(),
  value: z.number().nullable(),
  availability: FeatureAvailabilitySchema,
  source_timeframe: z.string(),
  source_timestamp: z.string(),
});
export type ChartLabFeatureValue = z.infer<typeof ChartLabFeatureValueSchema>;

export const ChartLabFeatureOriginSchema = z.enum(["derived", "manual"]);
export type ChartLabFeatureOrigin = z.infer<typeof ChartLabFeatureOriginSchema>;

export const ChartLabFeatureGroupSchema = z.enum([
  "Trend",
  "Momentum",
  "Volatility",
  "Volume",
  "Price",
  "Time",
]);
export type ChartLabFeatureGroup = z.infer<typeof ChartLabFeatureGroupSchema>;

export const ChartLabFeatureDescriptorSchema = z.object({
  feature_key: z.string(),
  feature_ref: z.string(),
  name: z.string(),
  timeframe: z.string(),
  indicator_type: z.string(),
  group: ChartLabFeatureGroupSchema,
  origin: ChartLabFeatureOriginSchema,
  badge: z.string(),
});
export type ChartLabFeatureDescriptor = z.infer<typeof ChartLabFeatureDescriptorSchema>;

export const ChartLabFeatureLibraryResponseSchema = z.object({
  timeframe: z.string(),
  features: z.array(ChartLabFeatureDescriptorSchema).default([]),
});
export type ChartLabFeatureLibraryResponse = z.infer<
  typeof ChartLabFeatureLibraryResponseSchema
>;

export const ChartLabSignalMarkerSchema = z.object({
  timestamp: z.string(),
  symbol: z.string(),
  marker_type: z.string(),
  side: z.string(),
  reason: z.string(),
  signal_name: z.string(),
});
export type ChartLabSignalMarker = z.infer<typeof ChartLabSignalMarkerSchema>;

export const ChartLabBarPreviewSchema = z.object({
  bar_index: z.number().default(0),
  timestamp: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number().nullable().optional(),
  is_warmup: z.boolean().default(false),
  feature_values: z.array(ChartLabFeatureValueSchema).default([]),
  signal_markers: z.array(ChartLabSignalMarkerSchema).default([]),
  condition_truth_tree: z.record(z.string(), z.unknown()).default({}),
  non_fire_reasons: z.array(z.string()).default([]),
});
export type ChartLabBarPreview = z.infer<typeof ChartLabBarPreviewSchema>;

export const ChartLabFeatureSpecSchema = z
  .object({
    kind: z.string(),
    namespace: z.string(),
    timeframe: z.string(),
    source: z.string(),
    params: z.record(z.string(), z.unknown()).default({}),
    lookback: z.number().default(0),
    shift: z.number().default(0),
    scope: z.string().default("symbol"),
    version: z.string().default("v1"),
  })
  .passthrough();
export type ChartLabFeatureSpec = z.infer<typeof ChartLabFeatureSpecSchema>;

export const ChartLabFeaturePlanSchema = z
  .object({
    id: z.string(),
    strategy_version_id: z.string(),
    consumer: z.string(),
    symbols: z.array(z.string()).default([]),
    timeframes: z.array(z.string()).default([]),
    feature_specs: z.array(ChartLabFeatureSpecSchema).default([]),
    feature_keys: z.array(z.string()).default([]),
  })
  .passthrough();
export type ChartLabFeaturePlan = z.infer<typeof ChartLabFeaturePlanSchema>;

export const ChartLabSessionSchema = z
  .object({
    id: z.string(),
    mode: z.string(),
    symbol: z.string(),
    timeframe: z.string(),
    start: z.string(),
    end: z.string(),
    strategy_version_id: z.string().nullable().optional(),
    program_version_id: z.string().nullable().optional(),
  })
  .passthrough();
export type ChartLabSession = z.infer<typeof ChartLabSessionSchema>;

export const ChartLabPreviewEvidenceSchema = z
  .object({
    evidence_id: z.string(),
    strategy_id: z.string().nullable().optional(),
    strategy_version_id: z.string().nullable().optional(),
    symbol: z.string(),
    timeframe: z.string(),
    start: z.string(),
    end: z.string(),
    feature_snapshot_count: z.number(),
    signal_marker_count: z.number(),
    artifact_id: z.string().nullable().optional(),
    deployment_snapshot_id: z.string().nullable().optional(),
    deployment_snapshot: z.record(z.unknown()).nullable().optional(),
  })
  .passthrough();
export type ChartLabPreviewEvidence = z.infer<typeof ChartLabPreviewEvidenceSchema>;

export const ChartLabPreviewResponseSchema = z.object({
  session: ChartLabSessionSchema,
  feature_plan: ChartLabFeaturePlanSchema,
  features: z.array(ChartLabFeatureDescriptorSchema).default([]),
  bars: z.array(ChartLabBarPreviewSchema).default([]),
  evidence: ChartLabPreviewEvidenceSchema.nullable().optional(),
});
export type ChartLabPreviewResponse = z.infer<typeof ChartLabPreviewResponseSchema>;

export const ChartLabPreviewRequestSchema = z.object({
  strategy_version_id: z.string().nullable().optional(),
  manual_feature_refs: z.array(z.string()).default([]),
  symbol: z.string().min(1),
  timeframe: z.string().min(1),
  start: z.string(),
  end: z.string(),
  source: z.enum(["alpaca", "yahoo"]).default("alpaca"),
  adjustment_policy: z
    .enum(["split_dividend_adjusted", "split_only", "raw"])
    .default("split_dividend_adjusted"),
});
export type ChartLabPreviewRequest = z.infer<typeof ChartLabPreviewRequestSchema>;

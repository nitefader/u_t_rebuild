import { z } from "zod";

/**
 * Schemas for the Screener API.
 *
 * Doctrine guards reflected here:
 *   - Screener never deploys, attaches Accounts, or submits broker orders.
 *   - Runs are immutable; rerun creates a new run with parent_run_id.
 *   - AI output is advisory only and compiles into visible typed rules.
 *   - Save-as-watchlist creates a new Watchlist; it never mutates one.
 */

export const ScreenerMetricSchema = z.enum([
  "price",
  "avg_volume_20d",
  "relative_volume",
  "gap_pct",
  "change_pct",
  "rsi_14",
  "atr_14_pct",
  "prior_day_close",
  "prior_day_range_pct",
  "broker.tradable",
  "broker.fractionable",
  "broker.shortable",
  "broker.easy_to_borrow",
  "broker.active",
  "broker.exchange",
  "broker.asset_class",
  "broker.name",
]);
export type ScreenerMetric = z.infer<typeof ScreenerMetricSchema>;

export const ScreenerCriterionOperatorSchema = z.enum([
  "gte",
  "lte",
  "gt",
  "lt",
  "between",
  "eq",
]);
export type ScreenerCriterionOperator = z.infer<typeof ScreenerCriterionOperatorSchema>;

export const ScreenerFieldValueSchema = z.union([z.number(), z.string(), z.boolean()]);
export type ScreenerFieldValue = z.infer<typeof ScreenerFieldValueSchema>;

export const ScreenerCriterionSchema = z
  .object({
    metric: ScreenerMetricSchema,
    operator: ScreenerCriterionOperatorSchema,
    value: ScreenerFieldValueSchema,
    value_max: z.number().nullable().optional(),
    label: z.string().nullable().optional(),
  })
  .passthrough();
export type ScreenerCriterion = z.infer<typeof ScreenerCriterionSchema>;

export const ScreenerExpressionKindSchema = z.enum(["all", "any", "not", "criterion"]);
export type ScreenerExpressionKind = z.infer<typeof ScreenerExpressionKindSchema>;

export const ScreenerExpressionSchema: z.ZodTypeAny = z.lazy(() =>
  z
    .object({
      kind: ScreenerExpressionKindSchema,
      children: z.array(ScreenerExpressionSchema).default([]),
      criterion: ScreenerCriterionSchema.nullable().optional(),
    })
    .passthrough(),
);
export type ScreenerExpression = z.infer<typeof ScreenerExpressionSchema>;

export const ScreenerSourcePreferenceSchema = z.enum(["auto", "alpaca", "data_center"]);
export type ScreenerSourcePreference = z.infer<typeof ScreenerSourcePreferenceSchema>;

export const ScreenerUniverseSourceKindSchema = z.enum([
  "explicit",
  "watchlist",
  "preset",
  "market_list",
]);
export type ScreenerUniverseSourceKind = z.infer<typeof ScreenerUniverseSourceKindSchema>;

export const ScreenerUniverseSourceSchema = z
  .object({
    kind: ScreenerUniverseSourceKindSchema,
    symbols: z.array(z.string()).default([]),
    watchlist_id: z.string().nullable().optional(),
    preset: z.string().nullable().optional(),
    market_list_key: z.string().nullable().optional(),
  })
  .passthrough();
export type ScreenerUniverseSource = z.infer<typeof ScreenerUniverseSourceSchema>;

export const ScreenerVersionSchema = z
  .object({
    id: z.string(),
    screener_id: z.string(),
    version: z.number(),
    name: z.string(),
    description: z.string().nullable().optional(),
    universe_source: ScreenerUniverseSourceSchema,
    criteria: z.array(ScreenerCriterionSchema).default([]),
    expression: ScreenerExpressionSchema.nullable().optional(),
    timeframe: z.string().default("1d"),
    source_preference: ScreenerSourcePreferenceSchema.default("auto"),
    sort_metric: ScreenerMetricSchema.nullable().optional(),
    sort_descending: z.boolean().default(true),
    max_results: z.number().int().default(200),
    tags: z.array(z.string()).default([]),
    created_at: z.string(),
  })
  .passthrough();
export type ScreenerVersion = z.infer<typeof ScreenerVersionSchema>;

export const ScreenerStatusSchema = z.enum(["draft", "active", "deprecated", "archived"]);

export const ScreenerSchema = z
  .object({
    id: z.string(),
    name: z.string(),
    description: z.string().nullable().optional(),
    tags: z.array(z.string()).default([]),
    status: ScreenerStatusSchema.default("active"),
    created_at: z.string(),
    last_run_at: z.string().nullable().optional(),
    last_run_id: z.string().nullable().optional(),
    version_count: z.number().int().default(1),
    latest_version_id: z.string().nullable().optional(),
  })
  .passthrough();
export type Screener = z.infer<typeof ScreenerSchema>;

export const ScreenerRunStatusSchema = z.enum([
  "queued",
  "running",
  "completed",
  "failed",
  "canceled",
]);
export type ScreenerRunStatus = z.infer<typeof ScreenerRunStatusSchema>;

export const ScreenerResultMetricValueSchema = z.union([
  z.number(),
  z.string(),
  z.boolean(),
  z.null(),
]);

export const ScreenerResultRowSchema = z
  .object({
    symbol: z.string(),
    matched: z.boolean(),
    metrics: z.record(ScreenerResultMetricValueSchema).default({}),
    failed_criteria: z.array(z.string()).default([]),
    passed_criteria: z.array(z.string()).default([]),
    blocked_reasons: z.array(z.string()).default([]),
    evidence: z.record(z.unknown()).default({}),
    score: z.number().nullable().optional(),
    sparkline: z.array(z.number()).default([]),
  })
  .passthrough();
export type ScreenerResultRow = z.infer<typeof ScreenerResultRowSchema>;

export const ScreenerRunSchema = z
  .object({
    id: z.string(),
    screener_id: z.string(),
    screener_version_id: z.string(),
    started_at: z.string(),
    completed_at: z.string().nullable().optional(),
    status: ScreenerRunStatusSchema,
    run_kind: z.string().default("run"),
    parent_run_id: z.string().nullable().optional(),
    universe_size: z.number().int().default(0),
    matched_count: z.number().int().default(0),
    results: z.array(ScreenerResultRowSchema).default([]),
    error: z.string().nullable().optional(),
    sources_used: z.array(z.string()).default([]),
    source_evidence: z.record(z.unknown()).default({}),
    source_freshness: z.record(z.unknown()).default({}),
    audit_events: z.array(z.record(z.unknown())).default([]),
    cache_hit_rate: z.number().nullable().optional(),
    operator_session_id: z.string().nullable().optional(),
  })
  .passthrough();
export type ScreenerRun = z.infer<typeof ScreenerRunSchema>;

export const ScreenerResponseSchema = z
  .object({
    screener: ScreenerSchema,
    versions: z.array(ScreenerVersionSchema).default([]),
    last_run: ScreenerRunSchema.nullable().optional(),
  })
  .passthrough();
export type ScreenerResponse = z.infer<typeof ScreenerResponseSchema>;

export const ScreenerListResponseSchema = z
  .object({
    screeners: z.array(ScreenerSchema).default([]),
  })
  .passthrough();
export type ScreenerListResponse = z.infer<typeof ScreenerListResponseSchema>;

export const ScreenerRunListResponseSchema = z
  .object({
    runs: z.array(ScreenerRunSchema).default([]),
  })
  .passthrough();
export type ScreenerRunListResponse = z.infer<typeof ScreenerRunListResponseSchema>;

export const ScreenerCreateRequestSchema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().nullable().optional(),
  tags: z.array(z.string()).default([]),
  universe_source: ScreenerUniverseSourceSchema,
  criteria: z.array(ScreenerCriterionSchema).default([]),
  expression: ScreenerExpressionSchema.nullable().optional(),
  timeframe: z.string().default("1d"),
  source_preference: ScreenerSourcePreferenceSchema.default("auto"),
  sort_metric: ScreenerMetricSchema.nullable().optional(),
  sort_descending: z.boolean().default(true),
  max_results: z.number().int().min(1).max(1000).default(200),
});
export type ScreenerCreateRequest = z.infer<typeof ScreenerCreateRequestSchema>;

export const ScreenerPatchRequestSchema = z.object({
  name: z.string().max(120).nullable().optional(),
  description: z.string().nullable().optional(),
  tags: z.array(z.string()).nullable().optional(),
  status: ScreenerStatusSchema.nullable().optional(),
});
export type ScreenerPatchRequest = z.infer<typeof ScreenerPatchRequestSchema>;

export const ScreenerRunRequestSchema = z.object({
  version_id: z.string().nullable().optional(),
  operator_session_id: z.string().nullable().optional(),
});
export type ScreenerRunRequest = z.infer<typeof ScreenerRunRequestSchema>;

export const ScreenerRerunRequestSchema = z.object({
  operator_session_id: z.string().nullable().optional(),
});
export type ScreenerRerunRequest = z.infer<typeof ScreenerRerunRequestSchema>;

export const SaveAsWatchlistRequestSchema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().nullable().optional(),
  only_matched: z.boolean().default(true),
  kind: z.enum(["static", "dynamic"]).default("static"),
});
export type SaveAsWatchlistRequest = z.infer<typeof SaveAsWatchlistRequestSchema>;

export const SaveAsWatchlistResponseSchema = z
  .object({
    watchlist_id: z.string(),
    name: z.string(),
    symbol_count: z.number().int(),
  })
  .passthrough();
export type SaveAsWatchlistResponse = z.infer<typeof SaveAsWatchlistResponseSchema>;

export const ScreenerPresetSchema = z
  .object({
    key: z.string(),
    label: z.string(),
    symbol_count: z.number().int(),
    sample_symbols: z.array(z.string()).default([]),
  })
  .passthrough();
export type ScreenerPreset = z.infer<typeof ScreenerPresetSchema>;

export const ScreenerPresetsResponseSchema = z
  .object({
    presets: z.array(ScreenerPresetSchema).default([]),
  })
  .passthrough();

export const ScreenerFieldDefinitionSchema = z
  .object({
    key: ScreenerMetricSchema,
    label: z.string(),
    value_type: z.enum(["number", "boolean", "string"]).default("number"),
    unit: z.string().nullable().optional(),
    sources: z.array(z.string()).default([]),
    cadence: z.string().nullable().optional(),
    unavailable_behavior: z.string().nullable().optional(),
    supported_operators: z.array(ScreenerCriterionOperatorSchema).default([]),
  })
  .passthrough();
export type ScreenerFieldDefinition = z.infer<typeof ScreenerFieldDefinitionSchema>;

// Back-compat alias for old components. The /fields endpoint is preferred.
export type ScreenerMetricDefinition = ScreenerFieldDefinition;

export const ScreenerMetricsResponseSchema = z
  .object({
    metrics: z.array(ScreenerFieldDefinitionSchema).default([]),
  })
  .passthrough();

export const ScreenerFieldsResponseSchema = z
  .object({
    fields: z.array(ScreenerFieldDefinitionSchema).default([]),
  })
  .passthrough();
export type ScreenerFieldsResponse = z.infer<typeof ScreenerFieldsResponseSchema>;

export const ScreenerTemplateSchema = z
  .object({
    key: z.string(),
    label: z.string(),
    category: z.string(),
    description: z.string(),
    universe_source: ScreenerUniverseSourceSchema,
    expression: ScreenerExpressionSchema,
    sort_metric: ScreenerMetricSchema.nullable().optional(),
    sort_descending: z.boolean().default(true),
    timeframe: z.string().default("1d"),
    tags: z.array(z.string()).default([]),
  })
  .passthrough();
export type ScreenerTemplate = z.infer<typeof ScreenerTemplateSchema>;

export const ScreenerTemplatesResponseSchema = z
  .object({
    templates: z.array(ScreenerTemplateSchema).default([]),
  })
  .passthrough();
export type ScreenerTemplatesResponse = z.infer<typeof ScreenerTemplatesResponseSchema>;

export const ScreenerFromTemplateRequestSchema = z.object({
  template_key: z.string().min(1),
  name: z.string().max(120).nullable().optional(),
  description: z.string().nullable().optional(),
  tags: z.array(z.string()).default([]),
});
export type ScreenerFromTemplateRequest = z.infer<typeof ScreenerFromTemplateRequestSchema>;

export const MarketListDefinitionSchema = z
  .object({
    key: z.string(),
    label: z.string(),
    category: z.string(),
    provider: z.string(),
    description: z.string(),
    source: z.string(),
  })
  .passthrough();
export type MarketListDefinition = z.infer<typeof MarketListDefinitionSchema>;

export const MarketListsResponseSchema = z
  .object({
    market_lists: z.array(MarketListDefinitionSchema).default([]),
  })
  .passthrough();
export type MarketListsResponse = z.infer<typeof MarketListsResponseSchema>;

export const MarketListRunResponseSchema = z
  .object({
    screener: ScreenerSchema,
    version: ScreenerVersionSchema,
    run: ScreenerRunSchema,
  })
  .passthrough();
export type MarketListRunResponse = z.infer<typeof MarketListRunResponseSchema>;

export const ScreenerAIInterpretRequestSchema = z.object({
  prompt: z.string().min(1),
  operator_session_id: z.string().nullable().optional(),
});
export type ScreenerAIInterpretRequest = z.infer<typeof ScreenerAIInterpretRequestSchema>;

export const ScreenerAIInterpretResponseSchema = z
  .object({
    advisory_only: z.boolean().default(true),
    suggested_template_keys: z.array(z.string()).default([]),
    universe_source: ScreenerUniverseSourceSchema,
    expression: ScreenerExpressionSchema,
    assumptions: z.array(z.string()).default([]),
    unsupported_clauses: z.array(z.string()).default([]),
    audit_preview: z.record(z.unknown()).default({}),
  })
  .passthrough();
export type ScreenerAIInterpretResponse = z.infer<typeof ScreenerAIInterpretResponseSchema>;

export const ScreenerRunDiffSchema = z
  .object({
    run_id: z.string(),
    against_run_id: z.string(),
    added: z.array(z.string()).default([]),
    removed: z.array(z.string()).default([]),
    stayed: z.array(z.string()).default([]),
    newly_failed: z.array(z.string()).default([]),
    reason_changes: z.array(z.record(z.unknown())).default([]),
  })
  .passthrough();
export type ScreenerRunDiff = z.infer<typeof ScreenerRunDiffSchema>;

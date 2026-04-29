import { z } from "zod";

export const QualityStatusSchema = z.enum(["ok", "warning", "stale", "unknown"]);
export type QualityStatus = z.infer<typeof QualityStatusSchema>;

export const HistoricalBarSchema = z.object({
  timestamp: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number().nullable().optional(),
  vwap: z.number().nullable().optional(),
  trade_count: z.number().nullable().optional(),
  provider: z.string(),
  quality_status: QualityStatusSchema,
  bid: z.number().nullable().optional(),
  ask: z.number().nullable().optional(),
  spread: z.number().nullable().optional(),
  source_feed: z.string().nullable().optional(),
  adjusted_close: z.number().nullable().optional(),
  corporate_action_flag: z.boolean().nullable().optional(),
  gap_flag: z.boolean().nullable().optional(),
  synthetic_bar_flag: z.boolean().nullable().optional(),
});
export type HistoricalBar = z.infer<typeof HistoricalBarSchema>;

export const HistoricalDatasetSummarySchema = z.object({
  dataset_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  provider: z.string(),
  adjustment_label: z.string(),
  bar_count: z.number(),
  coverage_start: z.string(),
  coverage_end: z.string(),
  aggregate_quality_status: QualityStatusSchema,
});
export type HistoricalDatasetSummary = z.infer<typeof HistoricalDatasetSummarySchema>;

export const DatasetUsageRecordSchema = z.object({
  tool: z.string(),
  last_used_at: z.string(),
  note: z.string().optional().default(""),
});
export type DatasetUsageRecord = z.infer<typeof DatasetUsageRecordSchema>;

export const HistoricalDatasetDetailSchema = z.object({
  dataset_id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  provider: z.string(),
  adjustment_label: z.string(),
  bar_count: z.number(),
  coverage_start: z.string(),
  coverage_end: z.string(),
  missing_bar_count: z.number(),
  warnings: z.array(z.string()),
  aggregate_quality_status: QualityStatusSchema,
  provider_decision_markdown: z.string(),
  quality_report_markdown: z.string(),
  usage_history: z.array(DatasetUsageRecordSchema),
});
export type HistoricalDatasetDetail = z.infer<typeof HistoricalDatasetDetailSchema>;

export const HistoricalDatasetListResponseSchema = z.object({
  items: z.array(HistoricalDatasetSummarySchema),
});

export const HistoricalBarPageSchema = z.object({
  dataset_id: z.string(),
  offset: z.number(),
  limit: z.number(),
  total: z.number(),
  bars: z.array(HistoricalBarSchema),
});

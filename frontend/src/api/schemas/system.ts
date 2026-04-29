/**
 * Zod schemas mirroring the backend system status / streams /
 * settings response shapes.
 *
 * Source of truth: backend/app/api/routes/system_status.py,
 * system_streams.py, system_settings.py. Keep aligned.
 */

import { z } from "zod";

export const SystemStatusSchema = z.object({
  alpaca_endpoint: z.string(),
  alpaca_data_feed: z.string().nullable().optional(),
  alpaca_credentials_present: z.boolean(),
  alpaca_test_stream: z.boolean(),
  operator_environment: z.string(),
  operator_environment_source: z.string(),
  operator_environment_conflict: z.string().nullable().optional(),
});
export type SystemStatus = z.infer<typeof SystemStatusSchema>;

export const HubStatusSchema = z.object({
  provider: z.string(),
  asset_class: z.string().default("stock"),
  data_feed: z.string(),
  is_running: z.boolean(),
  consumer_count: z.number(),
  subscribed_symbols: z.array(z.string()),
  stream_status: z.string().nullable().optional(),
  last_error: z.string().nullable().optional(),
  last_message_at: z.string().nullable().optional(),
});
export type HubStatus = z.infer<typeof HubStatusSchema>;

export const TradeStreamStatusSchema = z.object({
  account_id: z.string(),
  account_label: z.string().nullable().optional(),
  is_running: z.boolean(),
  last_event_at: z.string().nullable().optional(),
  last_error: z.string().nullable().optional(),
  subscriber_count: z.number(),
  subscriber_summary_lines: z.array(z.string()).default([]),
  is_stale: z.boolean(),
  stale_reason: z.string().nullable().optional(),
  idle_note: z.string().nullable().optional(),
});
export type TradeStreamStatus = z.infer<typeof TradeStreamStatusSchema>;

export const SystemStreamsResponseSchema = z.object({
  market_data_hubs: z.array(HubStatusSchema),
  trade_streams: z.array(TradeStreamStatusSchema),
  snapshot_at: z.string(),
});
export type SystemStreamsResponse = z.infer<typeof SystemStreamsResponseSchema>;

export const SystemSettingsSchema = z
  .object({
    alpaca_use_test_stream: z.boolean().optional(),
    alpaca_data_feed: z.string().optional(),
    chart_lab_one_symbol_fakepaca: z.boolean().optional(),
    default_symbol: z.string().optional(),
  })
  .passthrough();
export type SystemSettings = z.infer<typeof SystemSettingsSchema>;

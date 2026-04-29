import { z } from "zod";

export const WatchlistKindSchema = z.enum(["static", "dynamic"]);
export type WatchlistKind = z.infer<typeof WatchlistKindSchema>;

export const WatchlistDynamicRulesSchema = z
  .object({
    universe: z.string().default("us_equities"),
    filters: z.array(z.record(z.unknown())).default([]),
    notes: z.string().nullable().optional(),
    source_type: z.enum(["manual_rules", "screener_version", "template"]).default("manual_rules"),
    screener_id: z.string().nullable().optional(),
    screener_version_id: z.string().nullable().optional(),
    template_key: z.string().nullable().optional(),
    refresh_policy: z.enum(["manual", "scheduled_review", "auto_snapshot"]).default("manual"),
    approval_policy: z.enum(["operator_review", "auto_approve"]).default("operator_review"),
  })
  .passthrough();
export type WatchlistDynamicRules = z.infer<typeof WatchlistDynamicRulesSchema>;

export const WatchlistSchema = z
  .object({
    watchlist_id: z.string(),
    name: z.string(),
    description: z.string().nullable().optional(),
    kind: WatchlistKindSchema,
    static_symbols: z.array(z.string()).default([]),
    dynamic_rules: WatchlistDynamicRulesSchema.nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    latest_snapshot_id: z.string().nullable().optional(),
    snapshot_count: z.number().default(0),
    status: z.enum(["active", "archived"]).default("active"),
    archived_at: z.string().nullable().optional(),
  })
  .passthrough();
export type Watchlist = z.infer<typeof WatchlistSchema>;

export const WatchlistSnapshotSchema = z
  .object({
    watchlist_snapshot_id: z.string(),
    watchlist_id: z.string(),
    taken_at: z.string(),
    symbols: z.array(z.string()),
    note: z.string().nullable().optional(),
    source_run_id: z.string().nullable().optional(),
    source_label: z.string().nullable().optional(),
    added_symbols: z.array(z.string()).default([]),
    removed_symbols: z.array(z.string()).default([]),
    stayed_symbols: z.array(z.string()).default([]),
    evidence: z.record(z.unknown()).default({}),
  })
  .passthrough();
export type WatchlistSnapshot = z.infer<typeof WatchlistSnapshotSchema>;

export const WatchlistResponseSchema = z
  .object({
    watchlist: WatchlistSchema,
    snapshots: z.array(WatchlistSnapshotSchema).default([]),
  })
  .passthrough();
export type WatchlistResponse = z.infer<typeof WatchlistResponseSchema>;

export const WatchlistListResponseSchema = z
  .object({
    watchlists: z.array(WatchlistSchema).default([]),
  })
  .passthrough();
export type WatchlistListResponse = z.infer<typeof WatchlistListResponseSchema>;

export const WatchlistWriteRequestSchema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().nullable().optional(),
  kind: WatchlistKindSchema,
  static_symbols: z.array(z.string()).default([]),
  dynamic_rules: WatchlistDynamicRulesSchema.nullable().optional(),
});
export type WatchlistWriteRequest = z.infer<typeof WatchlistWriteRequestSchema>;

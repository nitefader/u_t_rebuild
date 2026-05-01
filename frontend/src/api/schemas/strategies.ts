/**
 * Minimal schemas for the legacy /api/v1/strategies backend.
 *
 * The legacy strategy backend stays alive through Slice 11 (runtime swap)
 * because research surfaces (Backtests, Walk-Forward, Optimization, Sim Lab)
 * and Deployments need it for strategy/version pickers and human-readable
 * run labels. This file is NOT the v4 IDE schema — that lives in
 * frontend/src/api/schemas/strategiesV4.ts.
 *
 * Only the types required by surviving consumers are exported here. The
 * strategy builder / composer schemas (ConditionNode, SignalRule, etc.) are
 * gone with the deleted UI surfaces.
 */

import { z } from "zod";

export const StrategyVersionPayloadSchema = z
  .object({
    id: z.string(),
    strategy_id: z.string(),
    version: z.number(),
    name: z.string(),
    description: z.string().nullable().optional(),
    feature_refs: z.array(z.string()).default([]),
    tags: z.array(z.string()).default([]),
    created_at: z.string(),
  })
  .passthrough();
export type StrategyVersionPayload = z.infer<typeof StrategyVersionPayloadSchema>;

export const StrategyVersionRecordSchema = z
  .object({
    strategy_version_id: z.string(),
    strategy_id: z.string(),
    version: z.number(),
    status: z.string(),
    payload: StrategyVersionPayloadSchema,
    frozen_at: z.string().nullable().optional(),
    frozen_by: z.string().nullable().optional(),
    created_at: z.string(),
  })
  .passthrough();
export type StrategyVersionRecord = z.infer<typeof StrategyVersionRecordSchema>;

export const StrategySchema = z
  .object({
    strategy_id: z.string(),
    name: z.string(),
    description: z.string().nullable().optional(),
    tags: z.array(z.string()).default([]),
    status: z.string(),
    created_at: z.string(),
    latest_version_id: z.string().nullable().optional(),
    frozen_version_ids: z.array(z.string()).default([]),
    version_count: z.number().default(0),
  })
  .passthrough();
export type Strategy = z.infer<typeof StrategySchema>;

export const StrategyResponseSchema = z
  .object({
    strategy: StrategySchema,
    versions: z.array(StrategyVersionRecordSchema).default([]),
  })
  .passthrough();
export type StrategyResponse = z.infer<typeof StrategyResponseSchema>;

export const StrategyListResponseSchema = z
  .object({
    strategies: z.array(StrategySchema).default([]),
  })
  .passthrough();
export type StrategyListResponse = z.infer<typeof StrategyListResponseSchema>;

export const StrategyWriteRequestSchema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().nullable().optional(),
  tags: z.array(z.string()).default([]),
});
export type StrategyWriteRequest = z.infer<typeof StrategyWriteRequestSchema>;

import { z } from "zod";
import { TradingHorizonSchema } from "./risk";

export const DeploymentLifecycleStatusSchema = z.enum([
  "draft",
  "active",
  "paused",
  "stopped",
]);
export type DeploymentLifecycleStatus = z.infer<typeof DeploymentLifecycleStatusSchema>;

export const DeploymentSchema = z.object({
  deployment_id: z.string(),
  name: z.string(),
  description: z.string().nullable().optional(),
  strategy_version_id: z.string(),
  watchlist_ids: z.array(z.string()).default([]),
  subscribed_account_ids: z.array(z.string()).default([]),
  lifecycle_status: DeploymentLifecycleStatusSchema,
  runtime_overrides: z.record(z.unknown()).default({}),
  /**
   * Risk horizon declared by this Deployment (Slice B).
   * Null = fall back to StrategyControls.trading_horizon.
   * Doctrine: Deployment chooses horizon; Account chooses RiskPlan; Governor enforces.
   */
  risk_horizon: TradingHorizonSchema.nullable().optional(),
  created_at: z.string(),
  updated_at: z.string(),
  started_at: z.string().nullable().optional(),
  stopped_at: z.string().nullable().optional(),
});
export type Deployment = z.infer<typeof DeploymentSchema>;

export const DeploymentResponseSchema = z.object({
  deployment: DeploymentSchema,
});
export type DeploymentResponse = z.infer<typeof DeploymentResponseSchema>;

export const DeploymentListResponseSchema = z.object({
  deployments: z.array(DeploymentSchema).default([]),
});
export type DeploymentListResponse = z.infer<typeof DeploymentListResponseSchema>;

export const DeploymentWriteRequestSchema = z.object({
  name: z.string().min(1).max(120),
  description: z.string().nullable().optional(),
  strategy_version_id: z.string(),
  watchlist_ids: z.array(z.string()).default([]),
  subscribed_account_ids: z.array(z.string()).default([]),
  runtime_overrides: z.record(z.unknown()).default({}),
  risk_horizon: TradingHorizonSchema.nullable().optional(),
});
export type DeploymentWriteRequest = z.infer<typeof DeploymentWriteRequestSchema>;

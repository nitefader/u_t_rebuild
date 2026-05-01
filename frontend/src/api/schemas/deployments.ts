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
  /**
   * Legacy FK — kept until Slice 11 cutover. Optional for v4-only rows.
   */
  strategy_version_id: z.string().nullable().optional(),
  /**
   * v4 FK — set by Slice 9+ deployments that bind a StrategyVersionV4.
   */
  strategy_version_v4_id: z.string().nullable().optional(),
  strategy_controls_version_id: z.string().nullable().optional(),
  execution_plan_version_id: z.string().nullable().optional(),
  risk_plan_version_id: z.string().nullable().optional(),
  watchlist_ids: z.array(z.string()).default([]),
  subscribed_account_ids: z.array(z.string()).default([]),
  lifecycle_status: DeploymentLifecycleStatusSchema,
  runtime_overrides: z.record(z.unknown()).default({}),
  /**
   * Risk horizon declared by this Deployment (Slice 8.7).
   * Deployment is the sole source of horizon; StrategyControls does not carry
   * a trading_horizon field. Doctrine: Deployment chooses horizon; Account
   * chooses RiskPlan; Governor enforces.
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
  /** Legacy FK — optional for v4-only rows. */
  strategy_version_id: z.string().nullable().optional(),
  /** v4 FK — set when binding a StrategyVersionV4. */
  strategy_version_v4_id: z.string().nullable().optional(),
  strategy_controls_version_id: z.string().nullable().optional(),
  execution_plan_version_id: z.string().nullable().optional(),
  risk_plan_version_id: z.string().nullable().optional(),
  watchlist_ids: z.array(z.string()).default([]),
  subscribed_account_ids: z.array(z.string()).default([]),
  runtime_overrides: z.record(z.unknown()).default({}),
  risk_horizon: TradingHorizonSchema.nullable().optional(),
});
export type DeploymentWriteRequest = z.infer<typeof DeploymentWriteRequestSchema>;

export const DeploymentRebindRequestSchema = z.object({
  strategy_controls_version_id: z.string().nullable().optional(),
  execution_plan_version_id: z.string().nullable().optional(),
  effective: z.string().default("now"),
});
export type DeploymentRebindRequest = z.infer<typeof DeploymentRebindRequestSchema>;

export const DeploymentBindingHistoryEntrySchema = z.object({
  entry_id: z.string(),
  deployment_id: z.string(),
  timestamp: z.string(),
  actor: z.string(),
  before: z.record(z.string().nullable()),
  after: z.record(z.string().nullable()),
  effective: z.string(),
});
export type DeploymentBindingHistoryEntry = z.infer<
  typeof DeploymentBindingHistoryEntrySchema
>;

export const DeploymentBindingHistoryListResponseSchema = z.object({
  entries: z.array(DeploymentBindingHistoryEntrySchema).default([]),
});
export type DeploymentBindingHistoryListResponse = z.infer<
  typeof DeploymentBindingHistoryListResponseSchema
>;

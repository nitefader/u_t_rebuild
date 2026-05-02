import { z } from "zod";

/**
 * RiskPlan / RiskPlanVersion / RiskPlanConfig schemas.
 *
 * Backed by the `RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT.md` §4 + §8.
 *
 * Routes are owned by Operation Turtle Shell (B1..B4):
 *   GET    /api/v1/risk-plans
 *   POST   /api/v1/risk-plans
 *   GET    /api/v1/risk-plans/{risk_plan_id}
 *   PATCH  /api/v1/risk-plans/{risk_plan_id}
 *   POST   /api/v1/risk-plans/{risk_plan_id}/versions
 *   GET    /api/v1/risk-plans/{risk_plan_id}/versions
 *   POST   /api/v1/risk-plans/{risk_plan_id}/activate
 *   POST   /api/v1/risk-plans/{risk_plan_id}/archive
 *   POST   /api/v1/risk-plans/ai-draft
 *   GET    /api/v1/accounts/{account_id}/risk-plan
 *   PUT    /api/v1/accounts/{account_id}/risk-plan
 *
 * All object schemas use `.passthrough()` so additive backend fields do not
 * break the typed UI client.
 */

export const RiskPlanStatusSchema = z.enum(["draft", "active", "archived"]);
export type RiskPlanStatus = z.infer<typeof RiskPlanStatusSchema>;

export const RiskPlanTierSchema = z.enum(["conservative", "balanced", "aggressive", "custom"]);
export type RiskPlanTier = z.infer<typeof RiskPlanTierSchema>;

export const RiskPlanSourceSchema = z.enum([
  "manual",
  "ai_generated",
  "optimization_generated",
  "walk_forward_recommended",
]);
export type RiskPlanSource = z.infer<typeof RiskPlanSourceSchema>;

export const RiskPlanVersionStatusSchema = z.enum(["draft", "active", "deprecated"]);
export type RiskPlanVersionStatus = z.infer<typeof RiskPlanVersionStatusSchema>;

export const RiskPlanSizingMethodSchema = z.enum([
  "fixed_shares",
  "fixed_notional",
  "risk_percent",
  "volatility_adjusted",
  "account_percent",
  "custom",
]);
export type RiskPlanSizingMethod = z.infer<typeof RiskPlanSizingMethodSchema>;

export const WholeShareRoundingSchema = z.enum(["floor", "round", "ceil"]);
export type WholeShareRounding = z.infer<typeof WholeShareRoundingSchema>;

/**
 * RiskPlanConfig — full set per contract §4.3.
 *
 * All fields optional/nullable so drafts and partial AI prompts can round-trip.
 * Validation tightening lives in the Create/Edit drawer (per §9.4).
 */
export const RiskPlanConfigSchema = z
  .object({
    sizing_method: RiskPlanSizingMethodSchema,

    fixed_shares: z.number().nullable().optional(),
    fixed_notional: z.number().nullable().optional(),
    risk_per_trade_pct: z.number().nullable().optional(),
    account_allocation_pct: z.number().nullable().optional(),
    max_trade_notional: z.number().nullable().optional(),
    min_trade_notional: z.number().nullable().optional(),

    max_position_notional: z.number().nullable().optional(),
    max_position_pct_of_equity: z.number().nullable().optional(),
    max_symbol_exposure_pct: z.number().nullable().optional(),
    max_sector_exposure_pct: z.number().nullable().optional(),
    max_gross_exposure_pct: z.number().nullable().optional(),
    max_net_exposure_pct: z.number().nullable().optional(),
    max_open_positions: z.number().nullable().optional(),
    max_open_risk_pct: z.number().nullable().optional(),

    max_daily_loss_pct: z.number().nullable().optional(),
    max_drawdown_pct: z.number().nullable().optional(),
    max_trades_per_day: z.number().nullable().optional(),
    cooldown_after_loss_minutes: z.number().nullable().optional(),

    fractional_quantity_allowed: z.boolean().optional(),
    whole_share_rounding: WholeShareRoundingSchema.optional(),

    min_quantity: z.number().nullable().optional(),
    max_quantity: z.number().nullable().optional(),

    stop_required: z.boolean().optional(),
    reject_if_no_stop: z.boolean().optional(),
    default_stop_policy: z
      .union([z.string(), z.record(z.unknown())])
      .nullable()
      .optional(),

    target_required: z.boolean().optional(),
    runner_allowed: z.boolean().optional(),

    allow_scale_in: z.boolean().optional(),
    allow_scale_out: z.boolean().optional(),
    allow_short: z.boolean().optional(),
    allow_extended_hours: z.boolean().optional(),

    symbol_restrictions: z.array(z.string()).optional(),
    asset_class_restrictions: z.array(z.string()).optional(),
    account_mode_restrictions: z.array(z.string()).optional(),
  })
  .passthrough();
export type RiskPlanConfig = z.infer<typeof RiskPlanConfigSchema>;

export const RiskPlanVersionSchema = z
  .object({
    risk_plan_version_id: z.string(),
    risk_plan_id: z.string(),
    version: z.number(),
    status: RiskPlanVersionStatusSchema,
    config_fingerprint: z.string(),
    config: RiskPlanConfigSchema,
    created_at: z.string(),
    activated_at: z.string().nullable().optional(),
    archived_at: z.string().nullable().optional(),
    notes: z.string().nullable().optional(),
  })
  .passthrough();
export type RiskPlanVersion = z.infer<typeof RiskPlanVersionSchema>;

/**
 * Ephemeral, session-only AI annotation passed from research surfaces
 * (Walk-Forward / Optimization "Save as Risk Plan") into the Create drawer.
 *
 * The backend persists only `ai_summary: str | None` on the RiskPlan
 * (per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §4.1). Warnings are
 * shown in the drawer for review and dropped on save — they are not part
 * of any persisted field.
 */
export interface RiskPlanAiAnnotation {
  summary: string;
  warnings: string[];
}

export const RiskPlanLinkedAccountSchema = z
  .object({
    account_id: z.string(),
    account_name: z.string().nullable().optional(),
    account_mode: z.string().nullable().optional(),
    is_default: z.boolean().optional(),
    last_risk_decision_at: z.string().nullable().optional(),
  })
  .passthrough();
export type RiskPlanLinkedAccount = z.infer<typeof RiskPlanLinkedAccountSchema>;

export const RiskPlanBacktestUsageSchema = z
  .object({
    run_id: z.string(),
    strategy_id: z.string().nullable().optional(),
    strategy_version_id: z.string().nullable().optional(),
    started_at: z.string().nullable().optional(),
    sharpe: z.number().nullable().optional(),
    max_drawdown: z.number().nullable().optional(),
    total_return: z.number().nullable().optional(),
    monte_carlo_summary: z.record(z.unknown()).nullable().optional(),
    warnings: z.array(z.string()).optional(),
  })
  .passthrough();
export type RiskPlanBacktestUsage = z.infer<typeof RiskPlanBacktestUsageSchema>;

export const RiskPlanDecisionStatsSchema = z
  .object({
    total: z.number().optional(),
    approved: z.number().optional(),
    rejected: z.number().optional(),
    reduced: z.number().optional(),
    capped: z.number().optional(),
    skipped: z.number().optional(),
    requires_operator: z.number().optional(),
    top_rejection_reasons: z
      .array(z.object({ reason: z.string(), count: z.number() }).passthrough())
      .optional(),
  })
  .passthrough();
export type RiskPlanDecisionStats = z.infer<typeof RiskPlanDecisionStatsSchema>;

/**
 * RiskPlan summary returned in list view + on the picker.
 * Detail responses extend this with versions / accounts / backtests / ai_notes.
 */
export const RiskPlanSummarySchema = z
  .object({
    risk_plan_id: z.string(),
    name: z.string(),
    description: z.string().nullable().optional(),
    status: RiskPlanStatusSchema,
    risk_score: z.number().min(0).max(10),
    risk_tier: RiskPlanTierSchema,
    source: RiskPlanSourceSchema,
    ai_generated: z.boolean().optional(),
    ai_summary: z.string().nullable().optional(),
    created_at: z.string(),
    updated_at: z.string(),
    created_by: z.string().nullable().optional(),
    active_version_id: z.string().nullable().optional(),
    active_version: RiskPlanVersionSchema.nullable().optional(),
    linked_account_count: z.number().optional(),
    last_used_at: z.string().nullable().optional(),
  })
  .passthrough();
export type RiskPlanSummary = z.infer<typeof RiskPlanSummarySchema>;

export const RiskPlanDetailSchema = RiskPlanSummarySchema.extend({
  versions: z.array(RiskPlanVersionSchema).default([]),
  linked_accounts: z.array(RiskPlanLinkedAccountSchema).default([]),
  backtest_usage: z.array(RiskPlanBacktestUsageSchema).default([]),
  decision_stats: RiskPlanDecisionStatsSchema.nullable().optional(),
}).passthrough();
export type RiskPlanDetail = z.infer<typeof RiskPlanDetailSchema>;

/**
 * Backend wire shape for create/get/patch/activate/archive responses.
 *
 * Backend (Codex) returns `{risk_plan, versions}` plus top-level enrichment
 * fields (`active_version`, `linked_accounts`, `backtest_usage`,
 * `decision_stats`). The adapter in `riskPlans.ts` flattens the envelope
 * into the consumer-facing `RiskPlanDetailSchema` and pulls the enrichment
 * fields through; if the backend ever drops the `risk_plan` wrapper in
 * favour of a fully flat shape, only the adapter changes.
 */
export const RiskPlanDetailEnvelopeSchema = z
  .object({
    risk_plan: RiskPlanSummarySchema,
    versions: z.array(RiskPlanVersionSchema).default([]),
    active_version_id: z.string().nullable().optional(),
    active_version: RiskPlanVersionSchema.nullable().optional(),
    linked_accounts: z.array(RiskPlanLinkedAccountSchema).default([]),
    backtest_usage: z.array(RiskPlanBacktestUsageSchema).default([]),
    decision_stats: RiskPlanDecisionStatsSchema.nullable().optional(),
  })
  .passthrough();
export type RiskPlanDetailEnvelope = z.infer<typeof RiskPlanDetailEnvelopeSchema>;

export const RiskPlanListResponseSchema = z
  .object({
    risk_plans: z.array(RiskPlanSummarySchema),
  })
  .passthrough();
export type RiskPlanListResponse = z.infer<typeof RiskPlanListResponseSchema>;

export const RiskPlanVersionListResponseSchema = z
  .object({
    versions: z.array(RiskPlanVersionSchema),
  })
  .passthrough();
export type RiskPlanVersionListResponse = z.infer<typeof RiskPlanVersionListResponseSchema>;

export const AccountRiskPlanAssignmentSchema = z
  .object({
    account_id: z.string(),
    risk_plan_id: z.string().nullable().optional(),
    risk_plan_version_id: z.string().nullable().optional(),
    risk_plan: RiskPlanSummarySchema.nullable().optional(),
    updated_at: z.string().nullable().optional(),
  })
  .passthrough();
export type AccountRiskPlanAssignment = z.infer<typeof AccountRiskPlanAssignmentSchema>;

export const RiskPlanAiDraftRequestSchema = z
  .object({
    prompt: z.string(),
    operator_session_id: z.string().nullable().optional(),
    metadata: z.record(z.unknown()).nullable().optional(),
  })
  .passthrough();
export type RiskPlanAiDraftRequest = z.infer<typeof RiskPlanAiDraftRequestSchema>;

export const RiskPlanAiDraftResponseSchema = z
  .object({
    risk_plan: RiskPlanSummarySchema,
    risk_plan_version: RiskPlanVersionSchema,
    warnings: z.array(z.string()).default([]),
    ai_provider_id: z.string(),
    ai_provider_name: z.string(),
    boundary_guardrails: z.array(z.string()).default([]),
  })
  .passthrough();
export type RiskPlanAiDraftResponse = z.infer<typeof RiskPlanAiDraftResponseSchema>;

export const CreateRiskPlanRequestSchema = z
  .object({
    name: z.string(),
    description: z.string().nullable().optional(),
    risk_score: z.number().min(0).max(10),
    risk_tier: RiskPlanTierSchema,
    source: RiskPlanSourceSchema.optional(),
    source_run_id: z.string().nullable().optional(),
    source_evidence_type: z.string().nullable().optional(),
    evidence_lineage: z.record(z.unknown()).optional(),
    ai_generated: z.boolean().optional(),
    ai_summary: z.string().nullable().optional(),
    config: RiskPlanConfigSchema,
  })
  .passthrough();
export type CreateRiskPlanRequest = z.infer<typeof CreateRiskPlanRequestSchema>;

export const PatchRiskPlanRequestSchema = z
  .object({
    name: z.string().optional(),
    description: z.string().nullable().optional(),
    risk_score: z.number().min(0).max(10).optional(),
    risk_tier: RiskPlanTierSchema.optional(),
    ai_summary: z.string().nullable().optional(),
  })
  .passthrough();
export type PatchRiskPlanRequest = z.infer<typeof PatchRiskPlanRequestSchema>;

export const NewRiskPlanVersionRequestSchema = z
  .object({
    config: RiskPlanConfigSchema,
    notes: z.string().nullable().optional(),
    activate: z.boolean().optional(),
  })
  .passthrough();
export type NewRiskPlanVersionRequest = z.infer<typeof NewRiskPlanVersionRequestSchema>;

export const PutAccountRiskPlanRequestSchema = z
  .object({
    risk_plan_id: z.string().nullable(),
    risk_plan_version_id: z.string().nullable().optional(),
  })
  .passthrough();
export type PutAccountRiskPlanRequest = z.infer<typeof PutAccountRiskPlanRequestSchema>;

export const RiskPlanFilterSchema = z
  .object({
    status: RiskPlanStatusSchema.optional(),
    tier: RiskPlanTierSchema.optional(),
    source: RiskPlanSourceSchema.optional(),
    minRiskScore: z.number().optional(),
    maxRiskScore: z.number().optional(),
    search: z.string().optional(),
  })
  .partial();
export type RiskPlanFilter = z.infer<typeof RiskPlanFilterSchema>;

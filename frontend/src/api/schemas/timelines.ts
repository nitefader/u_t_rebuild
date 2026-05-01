import { z } from "zod";

/**
 * Mirror of `backend/app/domain/signal_plan.py` cross-cutting types.
 *
 * Operations timeline routes:
 *   GET /api/v1/operations/signal-plans
 *   GET /api/v1/operations/evaluations
 *   GET /api/v1/operations/governor-decisions
 *
 * Schemas use `passthrough` so additive backend fields don't break the UI.
 */

export const SignalPlanIntentSchema = z.enum([
  "open",
  "close",
  "reduce",
  "target",
  "stop",
  "trail",
  "breakeven",
  "runner",
  "logical_exit",
]);

export const SignalPlanSideSchema = z.enum(["long", "short", "flat"]);

export const SignalPlanStatusSchema = z.enum([
  "created",
  "published",
  "expired",
  "partially_executed",
  "executed",
  "superseded",
  "canceled",
  "failed",
]);

export const SignalPlanSchema = z
  .object({
    signal_plan_id: z.string(),
    deployment_id: z.string(),
    strategy_id: z.string(),
    strategy_version_id: z.string(),
    symbol: z.string(),
    side: SignalPlanSideSchema,
    intent: SignalPlanIntentSchema,
    status: SignalPlanStatusSchema,
    opening_signal_plan_id: z.string().nullable().optional(),
    related_position_lineage_id: z.string().nullable().optional(),
    expires_at: z.string().nullable().optional(),
    created_at: z.string(),
    published_at: z.string().nullable().optional(),
    reason: z.string().default(""),
  })
  .passthrough();
export type SignalPlan = z.infer<typeof SignalPlanSchema>;

export const SignalPlanListResponseSchema = z.object({
  signal_plans: z.array(SignalPlanSchema).default([]),
});
export type SignalPlanListResponse = z.infer<typeof SignalPlanListResponseSchema>;

export const AccountEvaluationStatusSchema = z.enum([
  "accepted",
  "rejected",
  "blocked",
  "needs_operator_attention",
  "deferred",
  "stale",
]);

export const AccountParticipationDecisionSchema = z.enum([
  "participate",
  "ignore",
  "reject",
  "defer",
  "requires_operator",
]);

export const AccountSignalPlanEvaluationSchema = z
  .object({
    evaluation_id: z.string(),
    account_id: z.string(),
    signal_plan_id: z.string(),
    deployment_id: z.string(),
    strategy_id: z.string(),
    status: AccountEvaluationStatusSchema,
    participation_decision: AccountParticipationDecisionSchema,
    rejection_reasons: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    created_at: z.string(),
    evaluated_at: z.string().nullable().optional(),
  })
  .passthrough();
export type AccountSignalPlanEvaluation = z.infer<typeof AccountSignalPlanEvaluationSchema>;

export const AccountSignalPlanEvaluationListResponseSchema = z.object({
  evaluations: z.array(AccountSignalPlanEvaluationSchema).default([]),
});
export type AccountSignalPlanEvaluationListResponse = z.infer<
  typeof AccountSignalPlanEvaluationListResponseSchema
>;

export const GovernorDecisionStatusSchema = z.enum([
  "approved",
  "rejected",
  "blocked",
  "degraded",
  "requires_operator",
]);

export const GovernorDecisionTraceSchema = z
  .object({
    governor_decision_id: z.string(),
    account_id: z.string(),
    signal_plan_id: z.string(),
    status: GovernorDecisionStatusSchema,
    approved: z.boolean(),
    reasons: z.array(z.string()).default([]),
    violations: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    evaluated_at: z.string(),
  })
  .passthrough();
export type GovernorDecisionTrace = z.infer<typeof GovernorDecisionTraceSchema>;

export const GovernorDecisionListResponseSchema = z.object({
  governor_decisions: z.array(GovernorDecisionTraceSchema).default([]),
});
export type GovernorDecisionListResponse = z.infer<typeof GovernorDecisionListResponseSchema>;

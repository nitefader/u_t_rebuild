import { z } from "zod";

/**
 * Mirror of `backend/app/domain/signal_plan.py::PositionExplanationContext`.
 *
 * The route is not yet registered (Operation Turtle Shell is building
 * the PositionLineage service). The schema lives here so the moment the
 * endpoint exists, the typed client + drawer wire up without code
 * change. Until then `PositionsApi.explain` returns ApiError(404) and
 * the drawer shows an honest awaiting-backend state.
 */

export const PositionExplanationContextSchema = z
  .object({
    account_id: z.string(),
    position_lineage_id: z.string(),
    symbol: z.string(),
    side: z.enum(["long", "short", "flat"]),
    current_quantity: z.number(),
    average_entry: z.number().nullable().optional(),
    current_market_value: z.number().nullable().optional(),
    unrealized_pnl: z.number().nullable().optional(),
    opening_signal_plan_id: z.string(),
    current_signal_plan_ids: z.array(z.string()).default([]),
    deployment_id: z.string(),
    strategy_id: z.string(),
    account_evaluation_ids: z.array(z.string()).default([]),
    governor_decision_ids: z.array(z.string()).default([]),
    order_ids: z.array(z.string()).default([]),
    fill_ids: z.array(z.string()).default([]),
    active_stop: z.record(z.unknown()).nullable().optional(),
    active_targets: z.array(z.record(z.unknown())).default([]),
    runner_state: z.record(z.unknown()).nullable().optional(),
    logical_exit_state: z.record(z.unknown()).nullable().optional(),
    sync_state: z.record(z.unknown()).default({}),
    unresolved_risks: z.array(z.string()).default([]),
    explanation_generated_at: z.string(),
  })
  .passthrough();
export type PositionExplanationContext = z.infer<typeof PositionExplanationContextSchema>;

export const AiExplainPositionResponseSchema = z
  .object({
    summary: z.string(),
    advisories: z.array(z.string()).default([]),
    copy_context: z.string(),
    generated_at: z.string(),
    advisory_only: z.literal(true),
  })
  .passthrough();
export type AiExplainPositionResponse = z.infer<typeof AiExplainPositionResponseSchema>;

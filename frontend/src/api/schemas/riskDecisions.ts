import { z } from "zod";

/**
 * RiskDecisionCard schemas.
 *
 * RiskPlan belongs to the Account or selected research run. SignalPlan describes
 * the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan,
 * and current account or simulated account state to produce a RiskDecisionCard.
 * No simulated or real order may be created without that RiskDecisionCard.
 *
 * Doctrine: schemas .passthrough() so the typed client tolerates additive
 * fields, with `decision` and `mode` as `z.string()` so future enum values
 * (e.g. operator-introduced statuses) do not crash the read path.
 */

export const RiskCalculationStepSchema = z
  .object({
    name: z.string(),
    formula: z.string(),
    inputs: z.record(z.unknown()).default({}),
    output: z.number(),
  })
  .passthrough();
export type RiskCalculationStep = z.infer<typeof RiskCalculationStepSchema>;

export const RiskDecisionCardSchema = z
  .object({
    risk_decision_id: z.string(),
    mode: z.string(),
    run_id: z.string(),
    session_id: z.string().nullable().optional(),
    account_id: z.string().nullable().optional(),
    simulated_account_id: z.string().nullable().optional(),
    strategy_id: z.string(),
    strategy_version_id: z.string(),
    deployment_id: z.string().nullable().optional(),
    signal_plan_id: z.string(),
    candidate_trade_intent_id: z.string().nullable().optional(),
    feature_snapshot_id: z.string().nullable().optional(),
    symbol: z.string(),
    side: z.string(),
    lifecycle_intent: z.string(),
    timestamp: z.string(),
    risk_plan_id: z.string(),
    risk_plan_version_id: z.string(),
    risk_score: z.number().nullable().optional(),
    risk_tier: z.string().nullable().optional(),
    config_fingerprint: z.string().nullable().optional(),
    account_equity: z.number(),
    account_cash: z.number(),
    buying_power: z.number(),
    current_price: z.number(),
    entry_price: z.number().nullable().optional(),
    stop_price: z.number().nullable().optional(),
    stop_distance: z.number().nullable().optional(),
    stop_distance_pct: z.number().nullable().optional(),
    sizing_method: z.string(),
    formula_used: z.string(),
    raw_quantity: z.number().default(0),
    rounded_quantity: z.number().default(0),
    final_quantity: z.number().default(0),
    final_notional: z.number().default(0),
    rejected_quantity: z.number().nullable().optional(),
    capped_quantity: z.number().nullable().optional(),
    max_loss_estimate: z.number().nullable().optional(),
    risk_amount_requested: z.number().nullable().optional(),
    risk_amount_allowed: z.number().nullable().optional(),
    buying_power_required: z.number().nullable().optional(),
    projected_gross_exposure: z.number().nullable().optional(),
    projected_symbol_exposure: z.number().nullable().optional(),
    projected_open_risk: z.number().nullable().optional(),
    existing_position_quantity: z.number().default(0),
    existing_position_notional: z.number().default(0),
    existing_open_orders_count: z.number().int().default(0),
    existing_open_order_notional: z.number().default(0),
    fractional_quantity_allowed: z.boolean().default(true),
    whole_share_rounding: z.string().default("floor"),
    constraints_applied: z.array(z.string()).default([]),
    violations: z.array(z.string()).default([]),
    warnings: z.array(z.string()).default([]),
    decision: z.string(),
    reason_codes: z.array(z.string()).default([]),
    human_summary: z.string(),
    calculation_steps: z.array(RiskCalculationStepSchema).default([]),
    risk_resolver_version: z.string().default("risk_resolver/v1"),
    created_at: z.string(),
  })
  .passthrough();
export type RiskDecisionCard = z.infer<typeof RiskDecisionCardSchema>;

export const RiskDecisionCardListSchema = z
  .object({
    cards: z.array(RiskDecisionCardSchema).default([]),
  })
  .passthrough();
export type RiskDecisionCardList = z.infer<typeof RiskDecisionCardListSchema>;

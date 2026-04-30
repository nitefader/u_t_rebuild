import { z } from "zod";

/**
 * Account risk config + restrictions schemas.
 *
 * Backed by `/api/v1/broker-accounts/{id}/risk-config` and
 * `/api/v1/broker-accounts/{id}/restrictions`. The schemas use
 * `passthrough` so additive backend fields do not break the UI.
 */

// ---------------------------------------------------------------------------
// Risk Horizon vocabulary (Slice B)
// ---------------------------------------------------------------------------

export const TradingHorizonSchema = z.enum([
  "scalping",
  "intraday",
  "swing",
  "position",
  "other",
]);
export type TradingHorizon = z.infer<typeof TradingHorizonSchema>;

export const TRADING_HORIZON_LABELS: Record<TradingHorizon, string> = {
  scalping: "Scalping",
  intraday: "Intraday",
  swing: "Swing",
  position: "Position",
  other: "Other",
};

// ---------------------------------------------------------------------------
// AccountRiskPlanMap schemas (Slice B)
// ---------------------------------------------------------------------------

export const AccountRiskPlanMapEntrySchema = z
  .object({
    account_id: z.string(),
    horizon: TradingHorizonSchema,
    risk_plan_version_id: z.string(),
    updated_at: z.string(),
  })
  .passthrough();
export type AccountRiskPlanMapEntry = z.infer<typeof AccountRiskPlanMapEntrySchema>;

export const AccountRiskPlanMapSchema = z
  .object({
    account_id: z.string(),
    entries: z.array(AccountRiskPlanMapEntrySchema).default([]),
  })
  .passthrough();
export type AccountRiskPlanMap = z.infer<typeof AccountRiskPlanMapSchema>;

export const AccountRiskPlanMapUpdateRequestSchema = z.object({
  horizon: TradingHorizonSchema,
  risk_plan_version_id: z.string().uuid().nullable(),
});
export type AccountRiskPlanMapUpdateRequest = z.infer<typeof AccountRiskPlanMapUpdateRequestSchema>;

export const PositionSizingMethodSchema = z.enum([
  "fixed_shares",
  "fixed_dollar",
  "risk_percent_equity",
]);
export type PositionSizingMethod = z.infer<typeof PositionSizingMethodSchema>;

export const AccountRiskConfigSchema = z
  .object({
    account_id: z.string(),
    version: z.number(),
    sizing_method: PositionSizingMethodSchema,
    fixed_shares: z.number().nullable().optional(),
    fixed_notional: z.number().nullable().optional(),
    risk_per_trade_pct: z.number().nullable().optional(),
    max_position_notional: z.number().nullable().optional(),
    max_open_positions: z.number().nullable().optional(),
    max_symbol_concentration_pct: z.number().nullable().optional(),
    max_gross_exposure_pct: z.number().nullable().optional(),
    max_net_exposure_pct: z.number().nullable().optional(),
    max_daily_loss_pct: z.number().nullable().optional(),
    max_drawdown_pct: z.number().nullable().optional(),
    fractional_quantity_allowed: z.boolean().optional(),
    whole_share_rounding: z.string().optional(),
    updated_at: z.string(),
  })
  .passthrough();
export type AccountRiskConfig = z.infer<typeof AccountRiskConfigSchema>;

export const AccountRestrictionsSchema = z
  .object({
    account_id: z.string(),
    version: z.number(),
    symbol_blocklist: z.array(z.string()).default([]),
    asset_class_blocklist: z.array(z.string()).default([]),
    long_only: z.boolean().default(false),
    short_only: z.boolean().default(false),
    extended_hours_allowed: z.boolean().default(false),
    time_of_day_windows: z.array(z.record(z.unknown())).default([]),
    notes: z.string().nullable().optional(),
    updated_at: z.string(),
  })
  .passthrough();
export type AccountRestrictions = z.infer<typeof AccountRestrictionsSchema>;

export const AccountRiskCardSchema = z.object({
  risk_config: AccountRiskConfigSchema.nullable().optional(),
  restrictions: AccountRestrictionsSchema.nullable().optional(),
});
export type AccountRiskCard = z.infer<typeof AccountRiskCardSchema>;

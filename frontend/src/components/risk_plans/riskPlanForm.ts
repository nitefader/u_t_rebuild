import type {
  RiskPlanConfig,
  RiskPlanSizingMethod,
  RiskPlanTier,
} from "@/api/schemas/riskPlans";

/**
 * RiskPlanFormState — flat string-state-friendly representation of a
 * RiskPlanConfig, used by the Create/Edit drawer and the AI-draft preview.
 *
 * `null` and `undefined` mean "not set" (rendered as blank input). Booleans
 * stay strict; numeric fields round-trip as strings to keep blank inputs
 * possible without coercing to NaN.
 */
export interface RiskPlanFormState {
  // Identity
  name: string;
  description: string;
  risk_score: number;
  risk_tier: RiskPlanTier;

  // Sizing
  sizing_method: RiskPlanSizingMethod;
  fixed_shares: string;
  fixed_notional: string;
  risk_per_trade_pct: string;
  account_allocation_pct: string;
  max_trade_notional: string;
  min_trade_notional: string;

  // Exposure limits
  max_position_notional: string;
  max_position_pct_of_equity: string;
  max_symbol_exposure_pct: string;
  max_sector_exposure_pct: string;
  max_gross_exposure_pct: string;
  max_net_exposure_pct: string;
  max_open_positions: string;
  max_open_risk_pct: string;

  // Loss limits
  max_daily_loss_pct: string;
  max_drawdown_pct: string;
  max_trades_per_day: string;
  cooldown_after_loss_minutes: string;

  // Quantity rules
  fractional_quantity_allowed: boolean;
  whole_share_rounding: "floor" | "round" | "ceil";
  min_quantity: string;
  max_quantity: string;

  // Stop / target / runner
  stop_required: boolean;
  reject_if_no_stop: boolean;
  default_stop_policy: string;
  target_required: boolean;
  runner_allowed: boolean;

  // Position-rule toggles
  allow_scale_in: boolean;
  allow_scale_out: boolean;
  allow_short: boolean;
  allow_extended_hours: boolean;

  // Restrictions
  symbol_restrictions: string;
  asset_class_restrictions: string;
  account_mode_restrictions: string;
}

export const EMPTY_FORM: RiskPlanFormState = {
  name: "",
  description: "",
  risk_score: 5,
  risk_tier: "balanced",

  sizing_method: "risk_percent",
  fixed_shares: "",
  fixed_notional: "",
  risk_per_trade_pct: "1.0",
  account_allocation_pct: "",
  max_trade_notional: "",
  min_trade_notional: "",

  max_position_notional: "",
  max_position_pct_of_equity: "",
  max_symbol_exposure_pct: "",
  max_sector_exposure_pct: "",
  max_gross_exposure_pct: "",
  max_net_exposure_pct: "",
  max_open_positions: "5",
  max_open_risk_pct: "",

  max_daily_loss_pct: "3.0",
  max_drawdown_pct: "10.0",
  max_trades_per_day: "",
  cooldown_after_loss_minutes: "",

  fractional_quantity_allowed: false,
  whole_share_rounding: "floor",
  min_quantity: "",
  max_quantity: "",

  stop_required: true,
  reject_if_no_stop: true,
  default_stop_policy: "",
  target_required: false,
  runner_allowed: false,

  allow_scale_in: false,
  allow_scale_out: true,
  allow_short: false,
  allow_extended_hours: false,

  symbol_restrictions: "",
  asset_class_restrictions: "",
  account_mode_restrictions: "",
};

function s(n: number | null | undefined): string {
  return n == null ? "" : String(n);
}

export function formStateFromConfig(
  name: string,
  description: string,
  risk_score: number,
  risk_tier: RiskPlanTier,
  c: RiskPlanConfig,
): RiskPlanFormState {
  return {
    name,
    description,
    risk_score,
    risk_tier,
    sizing_method: c.sizing_method,
    fixed_shares: s(c.fixed_shares),
    fixed_notional: s(c.fixed_notional),
    risk_per_trade_pct: s(c.risk_per_trade_pct),
    account_allocation_pct: s(c.account_allocation_pct),
    max_trade_notional: s(c.max_trade_notional),
    min_trade_notional: s(c.min_trade_notional),
    max_position_notional: s(c.max_position_notional),
    max_position_pct_of_equity: s(c.max_position_pct_of_equity),
    max_symbol_exposure_pct: s(c.max_symbol_exposure_pct),
    max_sector_exposure_pct: s(c.max_sector_exposure_pct),
    max_gross_exposure_pct: s(c.max_gross_exposure_pct),
    max_net_exposure_pct: s(c.max_net_exposure_pct),
    max_open_positions: s(c.max_open_positions),
    max_open_risk_pct: s(c.max_open_risk_pct),
    max_daily_loss_pct: s(c.max_daily_loss_pct),
    max_drawdown_pct: s(c.max_drawdown_pct),
    max_trades_per_day: s(c.max_trades_per_day),
    cooldown_after_loss_minutes: s(c.cooldown_after_loss_minutes),
    fractional_quantity_allowed: c.fractional_quantity_allowed ?? false,
    whole_share_rounding: c.whole_share_rounding ?? "floor",
    min_quantity: s(c.min_quantity),
    max_quantity: s(c.max_quantity),
    stop_required: c.stop_required ?? false,
    reject_if_no_stop: c.reject_if_no_stop ?? false,
    default_stop_policy:
      typeof c.default_stop_policy === "string"
        ? c.default_stop_policy
        : c.default_stop_policy
          ? JSON.stringify(c.default_stop_policy)
          : "",
    target_required: c.target_required ?? false,
    runner_allowed: c.runner_allowed ?? false,
    allow_scale_in: c.allow_scale_in ?? false,
    allow_scale_out: c.allow_scale_out ?? true,
    allow_short: c.allow_short ?? false,
    allow_extended_hours: c.allow_extended_hours ?? false,
    symbol_restrictions: (c.symbol_restrictions ?? []).join(", "),
    asset_class_restrictions: (c.asset_class_restrictions ?? []).join(", "),
    account_mode_restrictions: (c.account_mode_restrictions ?? []).join(", "),
  };
}

function n(s: string): number | null {
  if (s.trim() === "") return null;
  const v = Number(s);
  return Number.isFinite(v) ? v : null;
}

function intN(s: string): number | null {
  const v = n(s);
  if (v == null) return null;
  return Math.trunc(v);
}

function csv(s: string): string[] | undefined {
  const trimmed = s
    .split(/[,\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
  return trimmed.length === 0 ? undefined : trimmed;
}

export function configFromFormState(f: RiskPlanFormState): RiskPlanConfig {
  return {
    sizing_method: f.sizing_method,
    fixed_shares: intN(f.fixed_shares),
    fixed_notional: n(f.fixed_notional),
    risk_per_trade_pct: n(f.risk_per_trade_pct),
    account_allocation_pct: n(f.account_allocation_pct),
    max_trade_notional: n(f.max_trade_notional),
    min_trade_notional: n(f.min_trade_notional),
    max_position_notional: n(f.max_position_notional),
    max_position_pct_of_equity: n(f.max_position_pct_of_equity),
    max_symbol_exposure_pct: n(f.max_symbol_exposure_pct),
    max_sector_exposure_pct: n(f.max_sector_exposure_pct),
    max_gross_exposure_pct: n(f.max_gross_exposure_pct),
    max_net_exposure_pct: n(f.max_net_exposure_pct),
    max_open_positions: intN(f.max_open_positions),
    max_open_risk_pct: n(f.max_open_risk_pct),
    max_daily_loss_pct: n(f.max_daily_loss_pct),
    max_drawdown_pct: n(f.max_drawdown_pct),
    max_trades_per_day: intN(f.max_trades_per_day),
    cooldown_after_loss_minutes: intN(f.cooldown_after_loss_minutes),
    fractional_quantity_allowed: f.fractional_quantity_allowed,
    whole_share_rounding: f.whole_share_rounding,
    min_quantity: n(f.min_quantity),
    max_quantity: n(f.max_quantity),
    stop_required: f.stop_required,
    reject_if_no_stop: f.reject_if_no_stop,
    default_stop_policy: f.default_stop_policy.trim() || null,
    target_required: f.target_required,
    runner_allowed: f.runner_allowed,
    allow_scale_in: f.allow_scale_in,
    allow_scale_out: f.allow_scale_out,
    allow_short: f.allow_short,
    allow_extended_hours: f.allow_extended_hours,
    symbol_restrictions: csv(f.symbol_restrictions),
    asset_class_restrictions: csv(f.asset_class_restrictions),
    account_mode_restrictions: csv(f.account_mode_restrictions),
  };
}

/**
 * Validation per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §9.4.
 *
 * Returns `errors` (block save) and `warnings` (operator-visible but
 * non-blocking — covers aggressive-settings warning).
 */
export interface FormValidation {
  errors: { field: keyof RiskPlanFormState | string; message: string }[];
  warnings: { field: keyof RiskPlanFormState | string; message: string }[];
}

export function validateForm(f: RiskPlanFormState): FormValidation {
  const errors: FormValidation["errors"] = [];
  const warnings: FormValidation["warnings"] = [];

  if (!f.name.trim()) {
    errors.push({ field: "name", message: "Name is required." });
  }

  if (f.risk_score < 0 || f.risk_score > 10) {
    errors.push({ field: "risk_score", message: "Risk score must be between 0 and 10." });
  }

  if (f.sizing_method === "risk_percent") {
    const rpt = n(f.risk_per_trade_pct);
    if (rpt == null || rpt <= 0) {
      errors.push({
        field: "risk_per_trade_pct",
        message: "Risk-percent sizing requires a positive risk_per_trade_pct.",
      });
    }
    if (!f.stop_required) {
      errors.push({
        field: "stop_required",
        message:
          "Risk-percent sizing requires `stop_required` — no stop ⇒ no stop distance ⇒ unbounded sizing.",
      });
    }
  }

  if (f.sizing_method === "fixed_shares") {
    const v = intN(f.fixed_shares);
    if (v == null || v <= 0) {
      errors.push({
        field: "fixed_shares",
        message: "Fixed-shares sizing requires a positive integer.",
      });
    }
  }

  if (f.sizing_method === "fixed_notional") {
    const v = n(f.fixed_notional);
    if (v == null || v <= 0) {
      errors.push({
        field: "fixed_notional",
        message: "Fixed-notional sizing requires a positive amount.",
      });
    }
  }

  if (f.sizing_method === "account_percent") {
    const v = n(f.account_allocation_pct);
    if (v == null || v <= 0 || v > 100) {
      errors.push({
        field: "account_allocation_pct",
        message: "Account-percent sizing requires 0 < account_allocation_pct ≤ 100.",
      });
    }
  }

  const rpt = n(f.risk_per_trade_pct);
  if (rpt != null && rpt > 5) {
    warnings.push({
      field: "risk_per_trade_pct",
      message: `Risk per trade ${rpt.toFixed(2)}% is unusually high; most prudent plans stay ≤ 2%.`,
    });
  }

  const mppe = n(f.max_position_pct_of_equity);
  if (mppe != null && mppe > 50) {
    warnings.push({
      field: "max_position_pct_of_equity",
      message: `Max position ${mppe.toFixed(2)}% of equity allows a single name to dominate the book.`,
    });
  }

  const mge = n(f.max_gross_exposure_pct);
  if (mge != null && mge > 200) {
    warnings.push({
      field: "max_gross_exposure_pct",
      message: `Max gross exposure ${mge.toFixed(0)}% is leveraged; verify the broker permits it.`,
    });
  }

  if (f.fractional_quantity_allowed && f.whole_share_rounding !== "floor") {
    errors.push({
      field: "whole_share_rounding",
      message:
        "Fractional quantity allowed conflicts with non-floor whole-share rounding. Set rounding to `floor` or disable fractional.",
    });
  }

  const mdl = n(f.max_daily_loss_pct);
  if (mdl != null && mdl > 10) {
    warnings.push({
      field: "max_daily_loss_pct",
      message: `Max daily loss ${mdl.toFixed(2)}% is aggressive — most plans stop the day at 3-5%.`,
    });
  }

  const tier = f.risk_tier;
  if (tier === "aggressive" || (rpt != null && rpt > 2)) {
    warnings.push({
      field: "risk_tier",
      message:
        "This Risk Plan is aggressive. Verify that operator + Account stops, daily-loss caps, and max-drawdown caps are set before live use.",
    });
  }

  return { errors, warnings };
}

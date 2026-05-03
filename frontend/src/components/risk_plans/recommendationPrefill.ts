import type { RiskPlanFormState } from "./riskPlanForm";
import { EMPTY_FORM } from "./riskPlanForm";
import type { RiskPlanSource, RiskPlanTier } from "@/api/schemas/riskPlans";

export const RESEARCH_OFFLINE_RISK_PLAN_SOURCES = [
  "optimization_generated",
  "walk_forward_recommended",
] as const satisfies readonly RiskPlanSource[];

export function isResearchOfflineRiskPlanSource(source: RiskPlanSource): boolean {
  // disabled: research spine offline until S12.7/S12.8.
  return RESEARCH_OFFLINE_RISK_PLAN_SOURCES.includes(
    source as (typeof RESEARCH_OFFLINE_RISK_PLAN_SOURCES)[number],
  );
}

/**
 * Convert a research recommendation (WF / Optimization) into a
 * RiskPlanFormState prefill.
 *
 * The shape is intentionally permissive — recommendations from different
 * pipelines carry different keys. We map the common ones (`fixed_shares`,
 * `risk_per_trade_pct`, `max_positions`, `max_daily_loss_pct`,
 * `max_drawdown_pct`, `max_symbol_exposure_pct`, `fixed_notional`) onto the
 * full form. Anything else stays at the empty default — the operator
 * reviews and tightens before saving (per non-negotiable §13).
 */
export interface RecommendationPrefillOptions {
  namePrefix: string;
  strategyName?: string | null;
  tier?: RiskPlanTier;
  riskScore?: number;
}

export function recommendationToFormPrefill(
  recommendation: { parameters?: Record<string, unknown> | null } | null | undefined,
  options: RecommendationPrefillOptions,
): Partial<RiskPlanFormState> {
  const params = (recommendation?.parameters ?? {}) as Record<string, unknown>;
  const next: Partial<RiskPlanFormState> = {
    name: buildName(options.namePrefix, options.strategyName ?? null),
    description: options.strategyName
      ? `Recommended Risk Plan from ${options.namePrefix} on ${options.strategyName}.`
      : `Recommended Risk Plan from ${options.namePrefix} run.`,
    risk_tier: options.tier ?? EMPTY_FORM.risk_tier,
    risk_score: options.riskScore ?? EMPTY_FORM.risk_score,
  };

  for (const [k, raw] of Object.entries(params)) {
    if (raw == null) continue;
    if (k === "fixed_shares") {
      next.fixed_shares = String(raw);
      next.sizing_method = "fixed_shares";
    } else if (k === "fixed_notional") {
      next.fixed_notional = String(raw);
      next.sizing_method = "fixed_notional";
    } else if (k === "risk_per_trade_pct") {
      next.risk_per_trade_pct = String(raw);
      next.sizing_method = "risk_percent";
    } else if (k === "account_allocation_pct") {
      next.account_allocation_pct = String(raw);
      next.sizing_method = "account_percent";
    } else if (k === "max_positions" || k === "max_open_positions") {
      next.max_open_positions = String(raw);
    } else if (k === "max_symbol_exposure_pct") {
      next.max_symbol_exposure_pct = String(raw);
    } else if (k === "max_sector_exposure_pct") {
      next.max_sector_exposure_pct = String(raw);
    } else if (k === "max_gross_exposure_pct") {
      next.max_gross_exposure_pct = String(raw);
    } else if (k === "max_net_exposure_pct") {
      next.max_net_exposure_pct = String(raw);
    } else if (k === "max_position_pct_of_equity") {
      next.max_position_pct_of_equity = String(raw);
    } else if (k === "max_position_notional") {
      next.max_position_notional = String(raw);
    } else if (k === "max_daily_loss_pct") {
      next.max_daily_loss_pct = String(raw);
    } else if (k === "max_drawdown_pct") {
      next.max_drawdown_pct = String(raw);
    } else if (k === "max_open_risk_pct") {
      next.max_open_risk_pct = String(raw);
    } else if (k === "max_trades_per_day") {
      next.max_trades_per_day = String(raw);
    } else if (k === "cooldown_after_loss_minutes") {
      next.cooldown_after_loss_minutes = String(raw);
    }
  }

  return next;
}

function buildName(prefix: string, strategyName: string | null): string {
  const ts = new Date();
  const stamp = `${ts.getFullYear()}-${pad(ts.getMonth() + 1)}-${pad(ts.getDate())}`;
  if (strategyName) {
    return `${prefix} · ${strategyName} · ${stamp}`;
  }
  return `${prefix} · ${stamp}`;
}

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

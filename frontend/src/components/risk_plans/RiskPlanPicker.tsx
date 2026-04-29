import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { RiskPlansApi } from "@/api/riskPlans";
import type {
  RiskPlanSummary,
  RiskPlanTier,
} from "@/api/schemas/riskPlans";
import { StatusBadge, type StatusTone } from "@/components/badges/StatusBadge";
import { Select } from "@/components/ui/Select";

/**
 * RiskPlanPicker — operator-facing picker for any research/runtime drawer.
 *
 * Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §9.5: the picker must
 * surface inline:
 *   - Risk Score (0..10)
 *   - Risk Tier
 *   - Sizing Method
 *   - Risk Per Trade
 *   - Max Position Limit
 *   - "View Risk Plan" deep-link
 *
 * Selection model: the picker emits `risk_plan_version_id` so the consuming
 * drawer / form persists the exact version used. Active version is auto-pinned
 * when the operator picks a Risk Plan, but operators can override version via
 * the Risk Plan detail page.
 */
export interface RiskPlanPickerProps {
  /** Currently selected `risk_plan_version_id`. */
  value: string | null | undefined;
  /** Setter receives the new `risk_plan_version_id`. */
  onChange: (next: string | null) => void;
  /** Optional system-default Risk Plan; rendered inline when `value` is empty. */
  systemDefault?: RiskPlanSummary | null;
  /** Drawer label override. Default: "Risk Plan". */
  label?: string;
  /** Optional hint shown below the select. */
  hint?: string;
  /** Disable the input (e.g. while submitting). */
  disabled?: boolean;
  /** Whether the picker is required (banner-level callout when missing). */
  required?: boolean;
  /** Pretend the API has not landed yet — for tests / fallback rendering. */
  placeholderOnly?: boolean;
}

const TIER_TONE: Record<RiskPlanTier, StatusTone> = {
  conservative: "ok",
  balanced: "info",
  aggressive: "danger",
  custom: "neutral",
};

function scoreTone(score: number): StatusTone {
  if (score <= 2) return "ok";
  if (score <= 4) return "info";
  if (score <= 6) return "neutral";
  if (score <= 8) return "warn";
  return "danger";
}

function formatPct(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(2)}%`;
}

function formatPctRaw(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}%`;
}

function formatNotional(v: number | null | undefined): string {
  if (v == null) return "—";
  return `$${v.toLocaleString()}`;
}

function describeMaxPosition(plan: RiskPlanSummary): string {
  const c = plan.active_version?.config;
  if (!c) return "—";
  if (c.max_position_notional != null) return formatNotional(c.max_position_notional);
  if (c.max_position_pct_of_equity != null) {
    return `${formatPctRaw(c.max_position_pct_of_equity)} of equity`;
  }
  if (c.max_open_positions != null) return `≤ ${c.max_open_positions} positions`;
  return "—";
}

export function RiskPlanPicker({
  value,
  onChange,
  systemDefault,
  label = "Risk Plan",
  hint,
  disabled,
  required,
  placeholderOnly,
}: RiskPlanPickerProps): JSX.Element {
  const list = useQuery({
    queryKey: ["risk-plans", "list"],
    queryFn: () => RiskPlansApi.list(),
    enabled: !placeholderOnly,
    refetchInterval: 60_000,
    retry: 1,
  });

  const activeVersionToPlan = useMemo(() => {
    const map = new Map<string, RiskPlanSummary>();
    for (const plan of list.data?.risk_plans ?? []) {
      const versionId = plan.active_version_id ?? plan.active_version?.risk_plan_version_id;
      if (versionId) map.set(versionId, plan);
    }
    return map;
  }, [list.data]);

  const selected = value ? activeVersionToPlan.get(value) : null;
  const showingSystemDefault = !value && Boolean(systemDefault);

  // Group plans into active / draft / archived.
  const active = (list.data?.risk_plans ?? []).filter((p) => p.status === "active");
  const drafts = (list.data?.risk_plans ?? []).filter((p) => p.status === "draft");
  const archived = (list.data?.risk_plans ?? []).filter((p) => p.status === "archived");

  return (
    <div className="space-y-1.5" data-testid="risk-plan-picker">
      <Select
        label={label + (required ? " *" : "")}
        value={value ?? ""}
        disabled={disabled || list.isLoading}
        onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        hint={
          list.isError
            ? `Could not load Risk Plans: ${(list.error as Error)?.message ?? "unknown error"}`
            : list.isLoading
              ? "Loading Risk Plans…"
              : (list.data?.risk_plans ?? []).length === 0
                ? "No Risk Plans yet — create one in Risk Plans."
                : (hint ?? undefined)
        }
      >
        <option value="">
          {showingSystemDefault
            ? `— System Default: ${systemDefault?.name} —`
            : required
              ? "— select a Risk Plan —"
              : "— none —"}
        </option>
        {active.length ? (
          <optgroup label="Active">
            {active.map((p) => (
              <RiskPlanOption key={p.risk_plan_id} plan={p} />
            ))}
          </optgroup>
        ) : null}
        {drafts.length ? (
          <optgroup label="Draft">
            {drafts.map((p) => (
              <RiskPlanOption key={p.risk_plan_id} plan={p} />
            ))}
          </optgroup>
        ) : null}
        {archived.length ? (
          <optgroup label="Archived">
            {archived.map((p) => (
              <RiskPlanOption key={p.risk_plan_id} plan={p} />
            ))}
          </optgroup>
        ) : null}
      </Select>

      {(selected ?? (showingSystemDefault ? systemDefault : null)) ? (
        <RiskPlanInlineCard
          plan={(selected ?? systemDefault) as RiskPlanSummary}
          isSystemDefault={showingSystemDefault}
        />
      ) : null}
    </div>
  );
}

function RiskPlanOption({ plan }: { plan: RiskPlanSummary }): JSX.Element {
  const versionId = plan.active_version_id ?? plan.active_version?.risk_plan_version_id ?? "";
  const sizing = plan.active_version?.config.sizing_method ?? "—";
  return (
    <option value={versionId} disabled={!versionId}>
      {plan.name} · score {plan.risk_score} · {plan.risk_tier} · {sizing}
      {versionId ? "" : " · no active version"}
    </option>
  );
}

export function RiskPlanInlineCard({
  plan,
  isSystemDefault,
}: {
  plan: RiskPlanSummary;
  isSystemDefault: boolean;
}): JSX.Element {
  const config = plan.active_version?.config;
  const sizing = config?.sizing_method ?? "—";
  const riskPerTrade =
    config?.sizing_method === "risk_percent" && config?.risk_per_trade_pct != null
      ? formatPctRaw(config.risk_per_trade_pct)
      : config?.sizing_method === "fixed_shares" && config?.fixed_shares != null
        ? `${config.fixed_shares} shares`
        : config?.sizing_method === "fixed_notional" && config?.fixed_notional != null
          ? formatNotional(config.fixed_notional)
          : config?.sizing_method === "account_percent" && config?.account_allocation_pct != null
            ? `${formatPctRaw(config.account_allocation_pct)} alloc`
            : "—";
  return (
    <div
      className="flex items-start justify-between gap-3 rounded border border-border bg-bg-subtle px-3 py-2 text-xs"
      data-testid="risk-plan-picker-inline"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="font-medium text-fg">{plan.name}</span>
          {isSystemDefault ? (
            <StatusBadge size="sm" tone="info">
              System Default
            </StatusBadge>
          ) : null}
          <StatusBadge size="sm" tone={scoreTone(plan.risk_score)}>
            score {plan.risk_score}
          </StatusBadge>
          <StatusBadge size="sm" tone={TIER_TONE[plan.risk_tier]}>
            {plan.risk_tier}
          </StatusBadge>
        </div>
        <dl className="mt-1.5 grid grid-cols-3 gap-x-3 gap-y-0.5 text-[11px] text-fg-muted">
          <div>
            <dt className="text-fg-subtle">Sizing</dt>
            <dd className="text-fg">{sizing}</dd>
          </div>
          <div>
            <dt className="text-fg-subtle">Risk / trade</dt>
            <dd className="text-fg">{riskPerTrade}</dd>
          </div>
          <div>
            <dt className="text-fg-subtle">Max position</dt>
            <dd className="text-fg">{describeMaxPosition(plan)}</dd>
          </div>
          <div>
            <dt className="text-fg-subtle">Daily loss</dt>
            <dd className="text-fg">{formatPct(config?.max_daily_loss_pct)}</dd>
          </div>
          <div>
            <dt className="text-fg-subtle">Max DD</dt>
            <dd className="text-fg">{formatPct(config?.max_drawdown_pct)}</dd>
          </div>
          <div>
            <dt className="text-fg-subtle">Open positions</dt>
            <dd className="text-fg">{config?.max_open_positions ?? "—"}</dd>
          </div>
        </dl>
      </div>
      <Link
        to={`/risk-plans/${plan.risk_plan_id}`}
        className="inline-flex shrink-0 items-center gap-1 rounded border border-border bg-bg-raised px-2 py-1 text-[11px] font-medium text-fg-muted hover:bg-bg-subtle hover:text-fg"
        target="_blank"
        rel="noreferrer"
      >
        <ExternalLink className="h-3 w-3" aria-hidden="true" />
        View Risk Plan
      </Link>
    </div>
  );
}

import { useId, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield } from "lucide-react";
import { RiskApi, RiskPlanMapApi } from "@/api/risk";
import { RiskPlansApi } from "@/api/riskPlans";
import type { AccountRestrictions, AccountRiskConfig, TradingHorizon } from "@/api/schemas/risk";
import { TradingHorizonSchema } from "@/api/schemas/risk";
import type { RiskPlanSummary } from "@/api/schemas/riskPlans";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { Banner } from "@/components/ui/Banner";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { HorizonRiskPlanPicker } from "@/components/risk_plans/HorizonRiskPlanPicker";
import { formatCurrency, formatPercent, formatTimestamp } from "@/lib/format";

// The 5 horizons in display order.
const HORIZONS = TradingHorizonSchema.options;

/**
 * RiskCardPanel — operator's risk posture for a single Account.
 *
 * Reads `/api/v1/broker-accounts/{id}/risk-config`,
 * `/api/v1/broker-accounts/{id}/restrictions`, and
 * `/api/v1/broker-accounts/{id}/risk-plan-map`.
 */
export function RiskCardPanel({ accountId }: { accountId: string }): JSX.Element {
  const config = useQuery({
    queryKey: ["accounts", accountId, "risk-config"],
    queryFn: () => RiskApi.getRiskConfig(accountId),
    retry: false,
  });
  const restrictions = useQuery({
    queryKey: ["accounts", accountId, "restrictions"],
    queryFn: () => RiskApi.getRestrictions(accountId),
    retry: false,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
            Risk Card
          </span>
        </CardTitle>
        <StatusBadge tone="info">Account-scoped</StatusBadge>
      </CardHeader>
      <CardBody className="space-y-3">
        {config.isLoading || restrictions.isLoading ? (
          <LoadingState title="Loading risk posture" />
        ) : null}

        {config.isError ? (
          <ErrorState
            title="Risk config"
            detail={(config.error as Error)?.message}
            onRetry={() => config.refetch()}
          />
        ) : config.data ? (
          <RiskConfigSummary cfg={config.data} />
        ) : null}

        {restrictions.isError ? (
          <ErrorState
            title="Account restrictions"
            detail={(restrictions.error as Error)?.message}
            onRetry={() => restrictions.refetch()}
          />
        ) : restrictions.data ? (
          <RestrictionsSummary restr={restrictions.data} />
        ) : null}

        <HorizonRiskPlanSection accountId={accountId} />
      </CardBody>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// RiskPlan by Horizon section
// ---------------------------------------------------------------------------

function HorizonRiskPlanSection({ accountId }: { accountId: string }): JSX.Element {
  const qc = useQueryClient();
  const explainerId = useId();
  // Slice B fix F-BUG-2: ref-based lock fires synchronously, before React's
  // disabled-state paint, so a fast operator who clicks two horizons in
  // quick succession serializes the writes instead of racing them through
  // the same endpoint with last-write-wins semantics.
  const inFlightRef = useRef(false);
  const queueRef = useRef<Array<{ horizon: TradingHorizon; riskPlanVersionId: string | null }>>([]);

  const planMap = useQuery({
    queryKey: ["accounts", accountId, "risk-plan-map"],
    queryFn: () => RiskPlanMapApi.get(accountId),
    retry: false,
  });

  const planList = useQuery({
    queryKey: ["risk-plans", "list"],
    queryFn: () => RiskPlansApi.list(),
    retry: false,
    staleTime: 60_000,
  });

  const save = useMutation({
    mutationFn: ({
      horizon,
      riskPlanVersionId,
    }: {
      horizon: TradingHorizon;
      riskPlanVersionId: string | null;
    }) => RiskPlanMapApi.update(accountId, { horizon, risk_plan_version_id: riskPlanVersionId }),
    onSuccess: (updated) => {
      qc.setQueryData(["accounts", accountId, "risk-plan-map"], updated);
    },
    onSettled: () => {
      inFlightRef.current = false;
      // Drain any edits queued while the previous PUT was in flight. Process
      // one at a time, latest-per-horizon (an operator who toggled the same
      // horizon twice mid-flight should land on their final choice).
      const queue = queueRef.current;
      queueRef.current = [];
      if (queue.length === 0) return;
      const collapsed = new Map<TradingHorizon, string | null>();
      for (const item of queue) collapsed.set(item.horizon, item.riskPlanVersionId);
      const next = collapsed.entries().next().value;
      if (next != null) {
        const [horizon, riskPlanVersionId] = next;
        // Re-queue the remaining collapsed entries so onSettled drains them.
        for (const [h, v] of collapsed) {
          if (h !== horizon) queueRef.current.push({ horizon: h, riskPlanVersionId: v });
        }
        inFlightRef.current = true;
        save.mutate({ horizon, riskPlanVersionId });
      }
    },
  });

  const availablePlans: RiskPlanSummary[] = planList.data?.risk_plans ?? [];

  function currentVersionId(horizon: TradingHorizon): string | null {
    const entry = (planMap.data?.entries ?? []).find((e) => e.horizon === horizon);
    return entry?.risk_plan_version_id ?? null;
  }

  function handleChange(horizon: TradingHorizon, versionId: string | null): void {
    if (inFlightRef.current) {
      queueRef.current.push({ horizon, riskPlanVersionId: versionId });
      return;
    }
    inFlightRef.current = true;
    save.mutate({ horizon, riskPlanVersionId: versionId });
  }

  // Slice B fix F-RISK-1: count covered horizons. Zero coverage means EVERY
  // subscribed Deployment will be rejected by the Governor regardless of
  // horizon — surface that as a single-line danger banner above the grid.
  const coveredHorizons = (planMap.data?.entries ?? []).filter(
    (e) => e.risk_plan_version_id != null,
  ).length;
  const allHorizonsUncovered =
    !planMap.isLoading && !planMap.isError && coveredHorizons === 0;

  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">
        RiskPlan by Horizon ({coveredHorizons} of {HORIZONS.length} covered)
      </div>

      <div id={explainerId}>
      <Banner
        severity="info"
        title="How horizon-based RiskPlans work"
        message={
          <span>
            Each Deployment declares a risk horizon (scalping / intraday / swing / position / other).
            When this Account is subscribed, the row below for that horizon picks which RiskPlan is
            enforced. Example: an intraday Deployment with no intraday RiskPlan mapped here will be
            rejected by the Governor at runtime with{" "}
            <code className="text-[11px]">account_missing_risk_plan_for_horizon</code>.
          </span>
        }
      />
      </div>

      {allHorizonsUncovered ? (
        <Banner
          severity="danger"
          title="No horizons mapped"
          message="Zero of the 5 horizons has a RiskPlan assigned. The Governor will reject every SignalPlan for this Account until at least one horizon is mapped."
        />
      ) : null}

      {planMap.isError ? (
        <ErrorState
          title="RiskPlan map"
          detail={(planMap.error as Error)?.message}
          onRetry={() => planMap.refetch()}
        />
      ) : planMap.isLoading || planList.isLoading ? (
        <LoadingState title="Loading horizon map" />
      ) : (
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {HORIZONS.map((horizon) => (
            <HorizonRiskPlanPicker
              key={horizon}
              horizon={horizon}
              selectedRiskPlanVersionId={currentVersionId(horizon)}
              availableRiskPlans={availablePlans}
              onChange={(versionId) => handleChange(horizon, versionId)}
              disabled={save.isPending}
              describedById={explainerId}
            />
          ))}
        </div>
      )}

      {save.isError ? (
        <Banner
          severity="danger"
          title="Could not save horizon mapping"
          message={(save.error as Error)?.message}
        />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Existing risk config + restrictions summary sections
// ---------------------------------------------------------------------------

function RiskConfigSummary({ cfg }: { cfg: AccountRiskConfig }): JSX.Element {
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">Sizing & exposure</div>
      <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
        <KV label="Sizing method" value={cfg.sizing_method} />
        <KV label="Fixed shares" value={cfg.fixed_shares != null ? String(cfg.fixed_shares) : "—"} />
        <KV label="Fixed notional" value={formatCurrency(cfg.fixed_notional ?? null)} />
        <KV
          label="Risk per trade"
          value={cfg.risk_per_trade_pct != null ? formatPercent(cfg.risk_per_trade_pct) : "—"}
        />
        <KV label="Max position" value={formatCurrency(cfg.max_position_notional ?? null)} />
        <KV
          label="Max open positions"
          value={cfg.max_open_positions != null ? String(cfg.max_open_positions) : "—"}
        />
        <KV
          label="Max gross exposure"
          value={cfg.max_gross_exposure_pct != null ? formatPercent(cfg.max_gross_exposure_pct) : "—"}
        />
        <KV
          label="Max net exposure"
          value={cfg.max_net_exposure_pct != null ? formatPercent(cfg.max_net_exposure_pct) : "—"}
        />
        <KV
          label="Symbol concentration"
          value={
            cfg.max_symbol_concentration_pct != null
              ? formatPercent(cfg.max_symbol_concentration_pct)
              : "—"
          }
        />
        <KV
          label="Max daily loss"
          value={cfg.max_daily_loss_pct != null ? formatPercent(cfg.max_daily_loss_pct) : "—"}
        />
        <KV
          label="Max drawdown"
          value={cfg.max_drawdown_pct != null ? formatPercent(cfg.max_drawdown_pct) : "—"}
        />
        <KV
          label="Fractional"
          value={cfg.fractional_quantity_allowed === undefined ? "—" : cfg.fractional_quantity_allowed ? "yes" : "no"}
        />
      </div>
      <div className="text-[11px] text-fg-subtle">Updated {formatTimestamp(cfg.updated_at)}</div>
    </div>
  );
}

function RestrictionsSummary({ restr }: { restr: AccountRestrictions }): JSX.Element {
  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-fg-subtle">Restrictions</div>
      <div className="flex flex-wrap gap-1.5">
        {restr.long_only ? <StatusBadge tone="info">Long only</StatusBadge> : null}
        {restr.short_only ? <StatusBadge tone="info">Short only</StatusBadge> : null}
        {restr.extended_hours_allowed ? (
          <StatusBadge tone="info">Extended hours</StatusBadge>
        ) : (
          <StatusBadge tone="muted">RTH only</StatusBadge>
        )}
        {restr.symbol_blocklist.length > 0 ? (
          <StatusBadge tone="warn">{restr.symbol_blocklist.length} symbol blocks</StatusBadge>
        ) : null}
        {restr.asset_class_blocklist.length > 0 ? (
          <StatusBadge tone="warn">
            {restr.asset_class_blocklist.length} asset blocks
          </StatusBadge>
        ) : null}
        {restr.time_of_day_windows.length > 0 ? (
          <StatusBadge tone="warn">
            {restr.time_of_day_windows.length} time windows
          </StatusBadge>
        ) : null}
      </div>
      {restr.symbol_blocklist.length > 0 ? (
        <div className="flex flex-wrap gap-1">
          {restr.symbol_blocklist.map((sym) => (
            <span
              key={sym}
              className="rounded border border-warn/40 bg-warn-subtle px-1.5 py-0.5 font-mono text-[11px] text-warn"
            >
              {sym}
            </span>
          ))}
        </div>
      ) : null}
      {restr.notes ? <div className="text-xs text-fg-muted">{restr.notes}</div> : null}
      <div className="text-[11px] text-fg-subtle">Updated {formatTimestamp(restr.updated_at)}</div>
    </div>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-fg-subtle">{label}</span>
      <span className="tabular text-fg">{value}</span>
    </div>
  );
}

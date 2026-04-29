import { useMemo, useState } from "react";
import { Activity, BarChart3, LineChart } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import type {
  StrategyDraftLaunchPlan,
  StrategyDraftLaunchPlans,
} from "@/api/schemas/strategyComposer";
import { ApiError, apiFetch } from "@/api/client";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import { RiskPlanPicker } from "@/components/risk_plans/RiskPlanPicker";

/**
 * LaunchPlansCard — surfaces the StrategyDraft.launch_plans block as
 * three operator actions (Open in Chart Lab / Run Backtest / Run
 * Walk-Forward), honoring `ready` + `missing_fields` from the backend.
 *
 * Behavior:
 *   - Chart Lab launch is a deep-link to /chart-lab?symbol=…
 *   - Backtest / Walk-Forward POST to /api/v1/research/jobs/{kind}
 *     with the pre-baked request body. When the backend reports
 *     `missing_fields`, the card renders inline inputs to collect
 *     them before allowing submit (risk_plan_version_id paste field
 *     for backtest; start/end date inputs for both).
 *   - On successful submit, the card surfaces a "Job queued — view in
 *     JobMonitor" success banner with a deep-link to the originating
 *     research surface.
 *
 * Doctrine: this never deploys, attaches an Account, submits a broker
 * order, or claims live readiness. Only research jobs.
 */
export interface LaunchPlansCardProps {
  launchPlans: StrategyDraftLaunchPlans | null | undefined;
  /** Optional override for symbol when the draft has no preselected universe. */
  defaultSymbol?: string;
}

export function LaunchPlansCard({ launchPlans, defaultSymbol }: LaunchPlansCardProps): JSX.Element {
  const chart = launchPlans?.chart_lab ?? null;
  const backtest = launchPlans?.backtest ?? null;
  const walkForward = launchPlans?.walk_forward ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Test this Strategy</CardTitle>
        <StatusBadge tone="info">research only</StatusBadge>
      </CardHeader>
      <CardBody className="space-y-2 text-xs">
        <div className="text-fg-muted">
          These actions create research evidence (Chart Lab preview / Backtest / Walk-Forward).
          They never create a Deployment, attach an Account, or submit a broker order.
        </div>
        <div className="grid grid-cols-1 gap-2">
          <ChartLabRow plan={chart} defaultSymbol={defaultSymbol} />
          <ResearchJobRow
            kind="backtest"
            label="Run Backtest"
            icon={<BarChart3 className="h-3.5 w-3.5" aria-hidden="true" />}
            plan={backtest}
            surfaceLink="/backtests"
          />
          <ResearchJobRow
            kind="walk-forward"
            label="Run Walk-Forward"
            icon={<LineChart className="h-3.5 w-3.5" aria-hidden="true" />}
            plan={walkForward}
            surfaceLink="/walk-forward"
          />
        </div>
      </CardBody>
    </Card>
  );
}

function ChartLabRow({
  plan,
  defaultSymbol,
}: {
  plan: StrategyDraftLaunchPlan | null;
  defaultSymbol?: string;
}): JSX.Element {
  const symbol =
    (plan?.request as { symbol?: string; query?: { symbol?: string } } | undefined)?.symbol ??
    (plan?.request as { query?: { symbol?: string } } | undefined)?.query?.symbol ??
    defaultSymbol ??
    "SPY";
  return (
    <div className="flex items-center gap-2 rounded border border-border px-2 py-1.5">
      <Activity className="h-3.5 w-3.5 text-fg-muted" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium">Open in Chart Lab</div>
        <div className="text-[11px] text-fg-muted">Streams the strategy's signals on a live candle chart.</div>
      </div>
      <Link to={`/chart-lab?symbol=${encodeURIComponent(symbol)}`}>
        <Button size="sm" variant="primary">
          Open
        </Button>
      </Link>
    </div>
  );
}

function ResearchJobRow({
  kind,
  label,
  icon,
  plan,
  surfaceLink,
}: {
  kind: "backtest" | "walk-forward";
  label: string;
  icon: React.ReactNode;
  plan: StrategyDraftLaunchPlan | null;
  surfaceLink: string;
}): JSX.Element {
  const navigate = useNavigate();
  const initialRequest = useMemo(() => extractRequestBody(plan), [plan]);
  const [request, setRequest] = useState<Record<string, unknown>>(initialRequest);

  const missing = (plan?.missing_fields ?? []).filter((f) => !hasField(request, f));
  const ready = (plan?.ready ?? false) && missing.length === 0;

  const submit = useMutation({
    mutationFn: async () => {
      const body = { request, metadata: { source: "strategy_builder_launch" } };
      const res = await apiFetch(`/api/v1/research/jobs/${kind}`, { method: "POST", body });
      return (await res.json()) as { job_id: string };
    },
    onSuccess: () => {
      // Land the operator on the relevant research surface so the
      // JobMonitor pulse-dot picks the new job up immediately.
      navigate(surfaceLink);
    },
  });

  function setField(field: string, value: unknown): void {
    if (field === "risk_plan_version_id") {
      setRequest((prev) => ({ ...prev, risk_plan_version_id: value }));
    } else if (field === "start" || field === "end") {
      setRequest((prev) => ({ ...prev, [field]: value }));
    } else {
      setRequest((prev) => ({ ...prev, [field]: value }));
    }
  }

  return (
    <div className="rounded border border-border px-2 py-1.5">
      <div className="flex items-center gap-2">
        <span className="text-fg-muted">{icon}</span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">{label}</div>
          <div className="text-[11px] text-fg-muted">
            POST {plan?.route ?? `/api/v1/research/jobs/${kind}`}
          </div>
        </div>
        <Button
          size="sm"
          variant={ready ? "primary" : "secondary"}
          disabled={!ready}
          loading={submit.isPending}
          onClick={() => submit.mutate()}
        >
          Run
        </Button>
      </div>

      {missing.length > 0 ? (
        <div className="mt-1.5 space-y-1.5 rounded bg-bg-inset px-2 py-1.5">
          <div className="text-[10.5px] uppercase tracking-wide text-fg-muted">Required to run</div>
          {missing.includes("risk_plan_version_id") ? (
            // Per Nanyel's Human-Readable Frontend Data Rule: never make the
            // operator paste a UUID. RiskPlanPicker shows Risk Plan name +
            // tier + sizing + risk-per-trade inline and emits the
            // risk_plan_version_id under the hood.
            <RiskPlanPicker
              value={(request.risk_plan_version_id as string | undefined) ?? null}
              onChange={(versionId) => setField("risk_plan_version_id", versionId)}
              label="Risk Plan"
              required
            />
          ) : null}
          {missing.includes("start") ? (
            <TextField
              label="Start date (YYYY-MM-DD or ISO)"
              value={(request.start as string | undefined) ?? ""}
              onChange={(e) => setField("start", e.target.value || null)}
              placeholder="2025-01-01"
            />
          ) : null}
          {missing.includes("end") ? (
            <TextField
              label="End date (YYYY-MM-DD or ISO)"
              value={(request.end as string | undefined) ?? ""}
              onChange={(e) => setField("end", e.target.value || null)}
              placeholder="2026-01-01"
            />
          ) : null}
        </div>
      ) : null}

      {submit.isError ? (
        <Banner
          severity="danger"
          title="Could not queue job"
          message={
            submit.error instanceof ApiError
              ? submit.error.detail || submit.error.message
              : String(submit.error)
          }
          className="mt-1.5"
        />
      ) : null}
    </div>
  );
}

function extractRequestBody(plan: StrategyDraftLaunchPlan | null): Record<string, unknown> {
  if (!plan?.request) return {};
  const r = plan.request as Record<string, unknown>;
  // Backend nests: { request: { ...actual fields... } }
  if (r.request && typeof r.request === "object") return { ...(r.request as Record<string, unknown>) };
  return { ...r };
}

function hasField(obj: Record<string, unknown>, field: string): boolean {
  const v = obj[field];
  return v !== null && v !== undefined && v !== "";
}

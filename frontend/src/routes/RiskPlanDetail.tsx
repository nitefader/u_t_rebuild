import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArrowLeft, Copy, GitCompare, Pencil, Sparkles } from "lucide-react";
import { ApiError } from "@/api/client";
import { RiskPlansApi } from "@/api/riskPlans";
import type {
  RiskPlanConfig,
  RiskPlanDetail as RiskPlanDetailT,
  RiskPlanSource,
  RiskPlanStatus,
  RiskPlanTier,
} from "@/api/schemas/riskPlans";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { StatusBadge, type StatusTone } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { RiskPlanDrawer } from "@/components/risk_plans/RiskPlanDrawer";
import { CompareRiskPlansDialog } from "@/components/risk_plans/CompareRiskPlansDialog";
import { PageHeader } from "./PageHeader";
import { formatTimestamp, relativeTime } from "@/lib/format";

const TIER_TONE: Record<RiskPlanTier, StatusTone> = {
  conservative: "ok",
  balanced: "info",
  aggressive: "danger",
  custom: "neutral",
};
const STATUS_TONE: Record<RiskPlanStatus, StatusTone> = {
  draft: "info",
  active: "ok",
  archived: "muted",
};
const SOURCE_LABEL: Record<RiskPlanSource, string> = {
  manual: "manual",
  ai_generated: "AI",
  optimization_generated: "Optimization",
  walk_forward_recommended: "Walk-Forward",
};

function scoreTone(score: number): StatusTone {
  if (score <= 2) return "ok";
  if (score <= 4) return "info";
  if (score <= 6) return "neutral";
  if (score <= 8) return "warn";
  return "danger";
}

export function RiskPlanDetail(): JSX.Element {
  const { riskPlanId = "" } = useParams<{ riskPlanId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [compareOpen, setCompareOpen] = useState(false);

  const detail = useQuery({
    queryKey: ["risk-plans", "detail", riskPlanId],
    queryFn: () => RiskPlansApi.get(riskPlanId),
    enabled: Boolean(riskPlanId),
    refetchInterval: 30_000,
  });
  const allPlans = useQuery({
    queryKey: ["risk-plans", "list"],
    queryFn: () => RiskPlansApi.list(),
    enabled: compareOpen,
  });

  const archive = useMutation({
    mutationFn: () => RiskPlansApi.archive(riskPlanId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["risk-plans"] });
    },
  });
  const duplicate = useMutation({
    mutationFn: async () => {
      const d = detail.data;
      if (!d?.active_version) throw new Error("no active version to duplicate");
      return RiskPlansApi.create({
        name: `${d.name} (copy)`,
        description: d.description ?? null,
        risk_score: d.risk_score,
        risk_tier: d.risk_tier,
        source: d.source ?? "manual",
        config: d.active_version.config,
      });
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ["risk-plans"] });
      navigate(`/risk-plans/${saved.risk_plan_id}`);
    },
  });
  const activateVersion = useMutation({
    mutationFn: (versionId: string) => RiskPlansApi.activate(riskPlanId, versionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["risk-plans"] });
    },
  });

  if (detail.isLoading) return <LoadingState title="Loading Risk Plan" />;
  if (detail.isError) {
    return (
      <ErrorState
        title="Could not load Risk Plan"
        detail={(detail.error as Error)?.message}
        onRetry={() => detail.refetch()}
      />
    );
  }
  const plan = detail.data;
  if (!plan) {
    return (
      <ErrorState title="Risk Plan not found" detail="The requested Risk Plan does not exist." />
    );
  }

  const activeConfig = plan.active_version?.config;

  return (
    <div className="space-y-4">
      <PageHeader
        title={plan.name}
        subtitle={plan.description ?? "Risk Plan detail"}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/risk-plans">
              <Button
                size="sm"
                variant="ghost"
                leftIcon={<ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />}
              >
                Back
              </Button>
            </Link>
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<GitCompare className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setCompareOpen(true)}
            >
              Compare
            </Button>
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Copy className="h-3.5 w-3.5" aria-hidden="true" />}
              loading={duplicate.isPending}
              onClick={() => duplicate.mutate()}
            >
              Duplicate
            </Button>
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Archive className="h-3.5 w-3.5" aria-hidden="true" />}
              loading={archive.isPending}
              disabled={plan.status === "archived"}
              onClick={() => archive.mutate()}
            >
              Archive
            </Button>
            <Button
              size="sm"
              variant="primary"
              leftIcon={<Pencil className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setEditOpen(true)}
            >
              Edit Draft
            </Button>
          </div>
        }
      />

      <Card>
        <div className="flex flex-wrap items-center gap-2 px-4 py-3">
          <StatusBadge tone={STATUS_TONE[plan.status]}>{plan.status}</StatusBadge>
          <StatusBadge tone={scoreTone(plan.risk_score)}>score {plan.risk_score}</StatusBadge>
          <StatusBadge tone={TIER_TONE[plan.risk_tier]}>{plan.risk_tier}</StatusBadge>
          <StatusBadge tone={plan.ai_generated ? "ai" : "neutral"}>
            {SOURCE_LABEL[plan.source]}
          </StatusBadge>
          <span className="text-xs text-fg-muted">
            Created {relativeTime(plan.created_at)}
            {plan.created_by ? ` by ${plan.created_by}` : ""} ·{" "}
            Updated {relativeTime(plan.updated_at)}
          </span>
        </div>
      </Card>

      {archive.error ? (
        <Banner
          severity="danger"
          title="Could not archive"
          message={
            archive.error instanceof ApiError
              ? archive.error.detail || archive.error.message
              : String(archive.error)
          }
        />
      ) : null}

      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="sizing">Sizing</TabsTrigger>
          <TabsTrigger value="exposure">Exposure Limits</TabsTrigger>
          <TabsTrigger value="loss">Loss Limits</TabsTrigger>
          <TabsTrigger value="position-rules">Position Rules</TabsTrigger>
          <TabsTrigger value="accounts">Account Assignments</TabsTrigger>
          <TabsTrigger value="backtests">Backtest Usage</TabsTrigger>
          <TabsTrigger value="decisions">Decision Cards</TabsTrigger>
          <TabsTrigger value="versions">Versions</TabsTrigger>
          <TabsTrigger value="ai">AI Notes</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <OverviewTab plan={plan} />
        </TabsContent>
        <TabsContent value="sizing">
          <FieldGrid title="Sizing" entries={sizingEntries(activeConfig)} />
        </TabsContent>
        <TabsContent value="exposure">
          <FieldGrid title="Exposure limits" entries={exposureEntries(activeConfig)} />
        </TabsContent>
        <TabsContent value="loss">
          <FieldGrid title="Loss limits" entries={lossEntries(activeConfig)} />
        </TabsContent>
        <TabsContent value="position-rules">
          <FieldGrid title="Position rules" entries={positionEntries(activeConfig)} />
        </TabsContent>
        <TabsContent value="accounts">
          <AccountsTab plan={plan} />
        </TabsContent>
        <TabsContent value="backtests">
          <BacktestUsageTab plan={plan} />
        </TabsContent>
        <TabsContent value="decisions">
          <DecisionCardsTab plan={plan} />
        </TabsContent>
        <TabsContent value="versions">
          <VersionsTab
            plan={plan}
            onActivate={(versionId) => activateVersion.mutate(versionId)}
            activatingVersionId={
              activateVersion.isPending ? (activateVersion.variables as string) : null
            }
          />
        </TabsContent>
        <TabsContent value="ai">
          <AiNotesTab plan={plan} />
        </TabsContent>
      </Tabs>

      <RiskPlanDrawer
        mode="edit"
        open={editOpen}
        onOpenChange={setEditOpen}
        plan={plan}
      />
      <CompareRiskPlansDialog
        open={compareOpen}
        onOpenChange={setCompareOpen}
        plans={allPlans.data?.risk_plans ?? []}
        initial={{
          a: plan.risk_plan_id,
          b:
            (allPlans.data?.risk_plans ?? []).find((p) => p.risk_plan_id !== plan.risk_plan_id)
              ?.risk_plan_id ?? plan.risk_plan_id,
        }}
      />
    </div>
  );
}

function OverviewTab({ plan }: { plan: RiskPlanDetailT }): JSX.Element {
  const config = plan.active_version?.config;
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Active version</CardTitle>
          {plan.active_version ? (
            <StatusBadge tone="ok">v{plan.active_version.version}</StatusBadge>
          ) : (
            <StatusBadge tone="warn">no active version</StatusBadge>
          )}
        </CardHeader>
        <CardBody className="space-y-2 text-xs">
          <KeyVal label="Risk plan id" value={<span className="font-mono">{plan.risk_plan_id}</span>} />
          <KeyVal
            label="Active version id"
            value={
              <span className="font-mono">
                {plan.active_version_id ?? plan.active_version?.risk_plan_version_id ?? "—"}
              </span>
            }
          />
          <KeyVal label="Sizing method" value={config?.sizing_method ?? "—"} />
          <KeyVal label="Stop required" value={String(config?.stop_required ?? false)} />
          <KeyVal
            label="Config fingerprint"
            value={<span className="font-mono text-[10px]">{plan.active_version?.config_fingerprint ?? "—"}</span>}
          />
          <KeyVal label="Activated" value={formatTimestamp(plan.active_version?.activated_at ?? null)} />
        </CardBody>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Human explanation</CardTitle>
        </CardHeader>
        <CardBody className="space-y-2 text-xs text-fg">
          {plan.ai_summary ? (
            <p>{plan.ai_summary}</p>
          ) : (
            <p className="text-fg-muted">
              No human summary saved. Edit the plan and add an AI summary or descriptive
              text — operators reading this page should understand intent without diving into
              the config.
            </p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function FieldGrid({
  title,
  entries,
}: {
  title: string;
  entries: Array<[string, React.ReactNode]>;
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardBody>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-xs sm:grid-cols-2 lg:grid-cols-3">
          {entries.map(([k, v]) => (
            <div key={k}>
              <dt className="text-fg-subtle">{k}</dt>
              <dd className="text-fg">{v ?? "—"}</dd>
            </div>
          ))}
        </dl>
      </CardBody>
    </Card>
  );
}

function v(value: unknown): React.ReactNode {
  if (value == null) return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function sizingEntries(c: RiskPlanConfig | undefined): Array<[string, React.ReactNode]> {
  if (!c) return [];
  return [
    ["Sizing method", c.sizing_method],
    ["Risk per trade (%)", v(c.risk_per_trade_pct)],
    ["Account allocation (%)", v(c.account_allocation_pct)],
    ["Fixed shares", v(c.fixed_shares)],
    ["Fixed notional", v(c.fixed_notional)],
    ["Min trade notional", v(c.min_trade_notional)],
    ["Max trade notional", v(c.max_trade_notional)],
    ["Fractional allowed", v(c.fractional_quantity_allowed)],
    ["Whole-share rounding", v(c.whole_share_rounding)],
    ["Min quantity", v(c.min_quantity)],
    ["Max quantity", v(c.max_quantity)],
    ["Stop required", v(c.stop_required)],
    ["Reject if no stop", v(c.reject_if_no_stop)],
    ["Default stop policy", v(c.default_stop_policy)],
  ];
}

function exposureEntries(c: RiskPlanConfig | undefined): Array<[string, React.ReactNode]> {
  if (!c) return [];
  return [
    ["Max position notional", v(c.max_position_notional)],
    ["Max position % of equity", v(c.max_position_pct_of_equity)],
    ["Max symbol exposure (%)", v(c.max_symbol_exposure_pct)],
    ["Max sector exposure (%)", v(c.max_sector_exposure_pct)],
    ["Max gross exposure (%)", v(c.max_gross_exposure_pct)],
    ["Max net exposure (%)", v(c.max_net_exposure_pct)],
    ["Max open positions", v(c.max_open_positions)],
    ["Max open risk (%)", v(c.max_open_risk_pct)],
  ];
}

function lossEntries(c: RiskPlanConfig | undefined): Array<[string, React.ReactNode]> {
  if (!c) return [];
  return [
    ["Max daily loss (%)", v(c.max_daily_loss_pct)],
    ["Max drawdown (%)", v(c.max_drawdown_pct)],
    ["Max trades per day", v(c.max_trades_per_day)],
    ["Cooldown after loss (min)", v(c.cooldown_after_loss_minutes)],
  ];
}

function positionEntries(c: RiskPlanConfig | undefined): Array<[string, React.ReactNode]> {
  if (!c) return [];
  return [
    ["Allow scale-in", v(c.allow_scale_in)],
    ["Allow scale-out", v(c.allow_scale_out)],
    ["Allow short", v(c.allow_short)],
    ["Allow extended hours", v(c.allow_extended_hours)],
    ["Runner allowed", v(c.runner_allowed)],
    ["Target required", v(c.target_required)],
    ["Stop required", v(c.stop_required)],
    ["Symbol restrictions", v(c.symbol_restrictions)],
    ["Asset class restrictions", v(c.asset_class_restrictions)],
    ["Account mode restrictions", v(c.account_mode_restrictions)],
  ];
}

function AccountsTab({ plan }: { plan: RiskPlanDetailT }): JSX.Element {
  const accounts = plan.linked_accounts ?? [];
  if (accounts.length === 0) {
    return (
      <EmptyState
        title="No accounts using this Risk Plan"
        message="Pin this Risk Plan from any Account on the Accounts page."
      />
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Account assignments ({accounts.length})</CardTitle>
      </CardHeader>
      <table className="min-w-full text-xs">
        <thead className="bg-bg-subtle text-fg-muted">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Account</th>
            <th className="px-3 py-2 text-left font-medium">Mode</th>
            <th className="px-3 py-2 text-left font-medium">Default?</th>
            <th className="px-3 py-2 text-left font-medium">Last risk decision</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-bg-raised">
          {accounts.map((a) => (
            <tr key={a.account_id} className="hover:bg-bg-subtle/40">
              <td className="px-3 py-2">
                <Link to={`/accounts`} className="font-medium hover:underline">
                  {a.account_name ?? a.account_id}
                </Link>
              </td>
              <td className="px-3 py-2 text-fg-muted">{a.account_mode ?? "—"}</td>
              <td className="px-3 py-2">
                {a.is_default ? <StatusBadge tone="ok">default</StatusBadge> : "—"}
              </td>
              <td className="px-3 py-2 text-fg-muted">
                {relativeTime(a.last_risk_decision_at ?? null)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function BacktestUsageTab({ plan }: { plan: RiskPlanDetailT }): JSX.Element {
  const usage = plan.backtest_usage ?? [];
  if (usage.length === 0) {
    return (
      <EmptyState
        title="Not used in any backtest yet"
        message="Pick this Risk Plan in the Backtests / Walk-Forward / Optimization drawers to see results here."
      />
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent backtests ({usage.length})</CardTitle>
      </CardHeader>
      <table className="min-w-full text-xs">
        <thead className="bg-bg-subtle text-fg-muted">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Run</th>
            <th className="px-3 py-2 text-left font-medium">Sharpe</th>
            <th className="px-3 py-2 text-left font-medium">Max DD</th>
            <th className="px-3 py-2 text-left font-medium">Total return</th>
            <th className="px-3 py-2 text-left font-medium">Started</th>
            <th className="px-3 py-2 text-left font-medium">Warnings</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-bg-raised">
          {usage.map((u) => (
            <tr key={u.run_id} className="hover:bg-bg-subtle/40">
              <td className="px-3 py-2">
                <Link to={`/backtests`} className="font-mono hover:underline">
                  {u.run_id.slice(0, 8)}…
                </Link>
              </td>
              <td className="px-3 py-2 text-fg-muted">{u.sharpe?.toFixed(2) ?? "—"}</td>
              <td className="px-3 py-2 text-fg-muted">
                {u.max_drawdown != null ? (u.max_drawdown * 100).toFixed(2) + "%" : "—"}
              </td>
              <td className="px-3 py-2 text-fg-muted">
                {u.total_return != null ? (u.total_return * 100).toFixed(2) + "%" : "—"}
              </td>
              <td className="px-3 py-2 text-fg-muted">{relativeTime(u.started_at ?? null)}</td>
              <td className="px-3 py-2">
                {(u.warnings ?? []).length > 0 ? (
                  <StatusBadge tone="warn">{(u.warnings ?? []).length}</StatusBadge>
                ) : (
                  "—"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function DecisionCardsTab({ plan }: { plan: RiskPlanDetailT }): JSX.Element {
  const stats = plan.decision_stats;
  if (!stats || (stats.total ?? 0) === 0) {
    return (
      <EmptyState
        title="No decision cards yet"
        message="Each sized SignalPlan that uses this Risk Plan emits a RiskDecisionCard. Cards become visible here as soon as Backtest / Sim Lab / Paper / Live runs hit the resolver."
      />
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Decision counts</CardTitle>
        </CardHeader>
        <CardBody>
          <dl className="grid grid-cols-2 gap-3 text-xs">
            <KeyVal label="Total" value={String(stats.total ?? 0)} />
            <KeyVal label="Approved" value={String(stats.approved ?? 0)} />
            <KeyVal label="Rejected" value={String(stats.rejected ?? 0)} />
            <KeyVal label="Reduced" value={String(stats.reduced ?? 0)} />
            <KeyVal label="Capped" value={String(stats.capped ?? 0)} />
            <KeyVal label="Skipped" value={String(stats.skipped ?? 0)} />
            <KeyVal label="Requires operator" value={String(stats.requires_operator ?? 0)} />
          </dl>
        </CardBody>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Top rejection reasons</CardTitle>
        </CardHeader>
        <CardBody>
          {stats.top_rejection_reasons && stats.top_rejection_reasons.length > 0 ? (
            <ul className="space-y-1 text-xs">
              {stats.top_rejection_reasons.map((r, i) => (
                <li key={i} className="flex items-center justify-between border-b border-border/40 pb-1 last:border-0">
                  <span>{r.reason}</span>
                  <StatusBadge tone="warn">{r.count}</StatusBadge>
                </li>
              ))}
            </ul>
          ) : (
            <span className="text-xs text-fg-muted">No rejections in the recent window.</span>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function VersionsTab({
  plan,
  onActivate,
  activatingVersionId,
}: {
  plan: RiskPlanDetailT;
  onActivate: (versionId: string) => void;
  activatingVersionId: string | null;
}): JSX.Element {
  const versions = (plan.versions ?? []).slice().sort((a, b) => b.version - a.version);
  if (versions.length === 0) {
    return <EmptyState title="No versions yet" message="Saving the first edit creates the initial version." />;
  }
  const activeId = plan.active_version_id ?? plan.active_version?.risk_plan_version_id;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Version history ({versions.length})</CardTitle>
      </CardHeader>
      <table className="min-w-full text-xs">
        <thead className="bg-bg-subtle text-fg-muted">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Version</th>
            <th className="px-3 py-2 text-left font-medium">Status</th>
            <th className="px-3 py-2 text-left font-medium">Fingerprint</th>
            <th className="px-3 py-2 text-left font-medium">Created</th>
            <th className="px-3 py-2 text-left font-medium">Activated</th>
            <th className="px-3 py-2 text-left font-medium">Notes</th>
            <th className="px-3 py-2 text-left font-medium">Action</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border bg-bg-raised">
          {versions.map((v_) => {
            const isActive = v_.risk_plan_version_id === activeId;
            return (
              <tr key={v_.risk_plan_version_id} className="hover:bg-bg-subtle/40">
                <td className="px-3 py-2 font-mono">v{v_.version}</td>
                <td className="px-3 py-2">
                  <StatusBadge tone={isActive ? "ok" : v_.status === "deprecated" ? "muted" : "info"}>
                    {isActive ? "active" : v_.status}
                  </StatusBadge>
                </td>
                <td className="px-3 py-2 font-mono text-[10px]">
                  {v_.config_fingerprint?.slice(0, 12)}
                </td>
                <td className="px-3 py-2 text-fg-muted">{relativeTime(v_.created_at)}</td>
                <td className="px-3 py-2 text-fg-muted">{relativeTime(v_.activated_at ?? null)}</td>
                <td className="px-3 py-2 text-fg-muted">{v_.notes ?? "—"}</td>
                <td className="px-3 py-2">
                  {!isActive ? (
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={activatingVersionId === v_.risk_plan_version_id}
                      onClick={() => onActivate(v_.risk_plan_version_id)}
                    >
                      Activate
                    </Button>
                  ) : (
                    <span className="text-fg-subtle">—</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function AiNotesTab({ plan }: { plan: RiskPlanDetailT }): JSX.Element {
  if (!plan.ai_generated && !plan.ai_summary) {
    return (
      <EmptyState
        title="No AI notes for this Risk Plan"
        message="If you generate this plan with AI or attach an AI summary during Save-as-Risk-Plan from a research run, it appears here."
      />
    );
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="inline-flex items-center gap-1.5">
            <Sparkles className="h-3.5 w-3.5 text-ai" aria-hidden="true" />
            AI summary
          </span>
        </CardTitle>
      </CardHeader>
      <CardBody className="space-y-2 text-xs">
        {plan.ai_summary ? (
          <p>{plan.ai_summary}</p>
        ) : (
          <p className="text-fg-muted">No summary saved.</p>
        )}
        <div className="grid grid-cols-2 gap-3 pt-2 text-fg-muted">
          <KeyVal label="AI generated" value={plan.ai_generated ? "yes" : "no"} />
          <KeyVal label="Source" value={plan.source} />
          <KeyVal label="Created" value={relativeTime(plan.created_at)} />
        </div>
      </CardBody>
    </Card>
  );
}

function KeyVal({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-fg-subtle">{label}</span>
      <span className="text-right font-medium text-fg">{value}</span>
    </div>
  );
}

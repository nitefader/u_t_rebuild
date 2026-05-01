/**
 * DeploymentDetail — per-deployment detail view.
 *
 * Shows deployment metadata, bound versions, horizon, watchlists, and accounts.
 * Right rail: binding history (newest-first).
 * "Rebind" button at top-right opens RebindDeploymentDrawer.
 */
import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, RefreshCw } from "lucide-react";
import { DeploymentsApi } from "@/api/deployments";
import { WatchlistsApi } from "@/api/watchlists";
import { AccountsApi } from "@/api/accounts";
import type { DeploymentBindingHistoryEntry } from "@/api/schemas/deployments";
import { TRADING_HORIZON_LABELS } from "@/api/schemas/risk";
import { ROUTE_DEPLOYMENTS } from "@/strategy_ide_v4/routes";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { RebindDeploymentDrawer } from "./RebindDeploymentDrawer";
import { relativeTime } from "@/lib/format";

function fieldLabel(key: string): string {
  const map: Record<string, string> = {
    strategy_version_id: "Strategy (legacy)",
    strategy_version_v4_id: "Strategy v4",
    strategy_controls_version_id: "Controls",
    execution_plan_version_id: "Execution Plan",
    risk_plan_version_id: "Risk Plan",
  };
  return map[key] ?? key;
}

function BindingHistoryEntry({
  entry,
}: {
  entry: DeploymentBindingHistoryEntry;
}): JSX.Element {
  const changed = Object.keys(entry.after).filter(
    (k) => entry.before[k] !== entry.after[k],
  );

  return (
    <div className="border-b border-border/50 py-3 last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-fg-muted">{relativeTime(entry.timestamp)}</span>
        <span className="text-[11px] text-fg-subtle">{entry.actor}</span>
        {entry.effective !== "now" ? (
          <StatusBadge tone="info" size="sm">
            {entry.effective === "next_session" ? "next session" : entry.effective}
          </StatusBadge>
        ) : null}
      </div>
      <div className="mt-1.5 space-y-1">
        {changed.map((key) => (
          <div key={key} className="text-xs">
            <span className="text-fg-muted">{fieldLabel(key)}:</span>{" "}
            <span className="text-fg-subtle line-through">
              {entry.before[key] ? entry.before[key]!.slice(0, 8) + "…" : "—"}
            </span>{" "}
            <span className="text-fg">
              {entry.after[key] ? entry.after[key]!.slice(0, 8) + "…" : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DeploymentDetail(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [rebindOpen, setRebindOpen] = useState(false);

  const deploymentQ = useQuery({
    queryKey: ["deployments", "detail", id],
    queryFn: () => DeploymentsApi.get(id!),
    enabled: Boolean(id),
    refetchInterval: 15_000,
  });
  const historyQ = useQuery({
    queryKey: ["deployments", "binding-history", id],
    queryFn: () => DeploymentsApi.getBindingHistory(id!),
    enabled: Boolean(id),
    refetchInterval: 30_000,
  });
  const watchlistsQ = useQuery({
    queryKey: ["watchlists", "list"],
    queryFn: () => WatchlistsApi.list(),
    staleTime: 60_000,
  });
  const accountsQ = useQuery({
    queryKey: ["accounts", "list"],
    queryFn: () => AccountsApi.list(),
    staleTime: 60_000,
  });

  if (!id) {
    navigate(ROUTE_DEPLOYMENTS);
    return <></>;
  }

  if (deploymentQ.isLoading) {
    return <LoadingState title="Loading deployment…" />;
  }
  if (deploymentQ.isError || !deploymentQ.data) {
    return (
      <ErrorState
        title="Could not load deployment"
        detail={(deploymentQ.error as Error)?.message}
        onRetry={() => deploymentQ.refetch()}
      />
    );
  }

  const deployment = deploymentQ.data.deployment;
  const watchlistMap = Object.fromEntries(
    (watchlistsQ.data?.watchlists ?? []).map((w) => [w.watchlist_id, w.name]),
  );
  const accountMap = Object.fromEntries(
    (accountsQ.data?.accounts ?? []).map((a) => [a.id, a.display_name]),
  );
  const isActive = deployment.lifecycle_status === "active";

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link
            to={ROUTE_DEPLOYMENTS}
            className="flex items-center gap-1 text-sm text-fg-muted hover:text-fg"
          >
            <ChevronLeft className="h-4 w-4" />
            Deployments
          </Link>
          <span className="text-fg-subtle">/</span>
          <span className="text-sm font-medium">{deployment.name}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
            onClick={() => {
              void qc.invalidateQueries({ queryKey: ["deployments", "detail", id] });
              void qc.invalidateQueries({ queryKey: ["deployments", "binding-history", id] });
            }}
          >
            Refresh
          </Button>
          {isActive ? (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setRebindOpen(true)}
            >
              Rebind
            </Button>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* Main column */}
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <div className="px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="text-lg font-semibold">{deployment.name}</span>
                <StatusBadge
                  tone={
                    deployment.lifecycle_status === "active"
                      ? "ok"
                      : deployment.lifecycle_status === "paused"
                        ? "warn"
                        : deployment.lifecycle_status === "stopped"
                          ? "muted"
                          : "info"
                  }
                >
                  {deployment.lifecycle_status}
                </StatusBadge>
              </div>
              {deployment.description ? (
                <div className="mt-1 text-sm text-fg-muted">{deployment.description}</div>
              ) : null}
            </div>
            <div className="grid grid-cols-2 gap-3 border-t border-border/70 px-4 py-3 text-xs sm:grid-cols-3">
              <MetaField
                label="Risk Horizon"
                value={
                  deployment.risk_horizon
                    ? TRADING_HORIZON_LABELS[deployment.risk_horizon]
                    : "—"
                }
              />
              <MetaField
                label="Started"
                value={deployment.started_at ? relativeTime(deployment.started_at) : "—"}
              />
              <MetaField
                label="Stopped"
                value={deployment.stopped_at ? relativeTime(deployment.stopped_at) : "—"}
              />
            </div>
          </Card>

          {/* Bound versions */}
          <Card>
            <div className="px-4 py-3">
              <div className="text-sm font-semibold">Bound Versions</div>
            </div>
            <div className="grid grid-cols-1 gap-2 border-t border-border/70 px-4 py-3 text-xs sm:grid-cols-2">
              <MetaField
                label="Strategy (legacy)"
                value={
                  deployment.strategy_version_id
                    ? deployment.strategy_version_id.slice(0, 8) + "…"
                    : "—"
                }
              />
              <MetaField
                label="Strategy v4"
                value={
                  deployment.strategy_version_v4_id
                    ? deployment.strategy_version_v4_id.slice(0, 8) + "…"
                    : "—"
                }
              />
              <MetaField
                label="Controls"
                value={
                  deployment.strategy_controls_version_id
                    ? deployment.strategy_controls_version_id.slice(0, 8) + "…"
                    : "—"
                }
              />
              <MetaField
                label="Execution Plan"
                value={
                  deployment.execution_plan_version_id
                    ? deployment.execution_plan_version_id.slice(0, 8) + "…"
                    : "—"
                }
              />
              <MetaField
                label="Risk Plan"
                value={
                  deployment.risk_plan_version_id
                    ? deployment.risk_plan_version_id.slice(0, 8) + "…"
                    : "—"
                }
              />
            </div>
          </Card>

          {/* Watchlists */}
          <Card>
            <div className="px-4 py-3 text-sm font-semibold">Entry Watchlists</div>
            <div className="border-t border-border/70 px-4 py-3">
              {deployment.watchlist_ids.length === 0 ? (
                <div className="text-xs text-fg-muted">None</div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {deployment.watchlist_ids.map((wid) => (
                    <StatusBadge key={wid} tone="neutral" size="sm">
                      {watchlistMap[wid] ?? wid.slice(0, 8) + "…"}
                    </StatusBadge>
                  ))}
                </div>
              )}
            </div>
          </Card>

          {/* Accounts */}
          <Card>
            <div className="px-4 py-3 text-sm font-semibold">Subscribed Accounts</div>
            <div className="border-t border-border/70 px-4 py-3">
              {deployment.subscribed_account_ids.length === 0 ? (
                <div className="text-xs text-fg-muted">None</div>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {deployment.subscribed_account_ids.map((aid) => (
                    <StatusBadge key={aid} tone="neutral" size="sm">
                      {accountMap[aid] ?? aid.slice(0, 8) + "…"}
                    </StatusBadge>
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Binding history rail */}
        <div className="lg:col-span-1">
          <Card>
            <div className="px-4 py-3 text-sm font-semibold">Binding History</div>
            <div className="border-t border-border/70 px-4 py-2">
              {historyQ.isLoading ? (
                <div className="py-4 text-xs text-fg-muted">Loading…</div>
              ) : historyQ.isError ? (
                <div className="py-4 text-xs text-red-500">
                  {(historyQ.error as Error)?.message}
                </div>
              ) : (historyQ.data?.entries ?? []).length === 0 ? (
                <div className="py-4 text-xs text-fg-muted">
                  No rebind history yet. Use Rebind to hot-swap Controls or Execution Plan.
                </div>
              ) : (
                (historyQ.data?.entries ?? []).map((entry) => (
                  <BindingHistoryEntry key={entry.entry_id} entry={entry} />
                ))
              )}
            </div>
          </Card>
        </div>
      </div>

      {isActive ? (
        <RebindDeploymentDrawer
          open={rebindOpen}
          onOpenChange={setRebindOpen}
          deployment={deployment}
        />
      ) : null}
    </div>
  );
}

function MetaField({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-fg-subtle">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

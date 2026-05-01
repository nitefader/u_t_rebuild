import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Pause, Play, Plus, Square, Trash2 } from "lucide-react";
import { EditDeploymentDrawer } from "./EditDeploymentDrawer";
import { RebindDeploymentDrawer } from "./RebindDeploymentDrawer";
import { ApiError } from "@/api/client";
import { AccountsApi } from "@/api/accounts";
import { DeploymentsApi } from "@/api/deployments";
import { StrategiesApi } from "@/api/strategies";
import { WatchlistsApi } from "@/api/watchlists";
import { listAllHeads } from "@/api/strategiesV4";
import type { Deployment } from "@/api/schemas/deployments";
import type { Strategy, StrategyVersionRecord } from "@/api/schemas/strategies";
import { TRADING_HORIZON_LABELS, type TradingHorizon } from "@/api/schemas/risk";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DangerConfirm } from "@/components/ui/DangerConfirm";
import { HoldToArmConfirm } from "@/components/ui/HoldToArmConfirm";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { PulseDot } from "@/components/ui/PulseDot";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { PageHeader } from "./PageHeader";
import { relativeTime } from "@/lib/format";
import { ROUTE_DEPLOYMENTS_NEW, deploymentDetailPath } from "@/strategy_ide_v4/routes";

export function Deployments(): JSX.Element {
  const navigate = useNavigate();
  const list = useQuery({
    queryKey: ["deployments", "list"],
    queryFn: () => DeploymentsApi.list(),
    refetchInterval: 15_000,
  });
  const watchlists = useQuery({
    queryKey: ["watchlists", "list"],
    queryFn: () => WatchlistsApi.list(),
    staleTime: 60_000,
  });
  const strategies = useQuery({
    queryKey: ["strategies", "list"],
    queryFn: () => StrategiesApi.list(),
    staleTime: 60_000,
  });
  const strategiesV4 = useQuery({
    queryKey: ["strategies-v4", "heads"],
    queryFn: listAllHeads,
    staleTime: 60_000,
  });
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const qc = useQueryClient();

  // Unified strategy name lookup: v4 heads take priority over legacy.
  const strategyNameById: Record<string, string> = useMemo(() => {
    const map: Record<string, string> = {};
    for (const s of strategies.data?.strategies ?? []) {
      if (s.latest_version_id) map[s.latest_version_id] = s.name;
      for (const fid of s.frozen_version_ids ?? []) {
        map[fid] = s.name;
      }
    }
    for (const h of strategiesV4.data ?? []) {
      map[h.strategy_v4_id] = h.name;
      map[h.head_version_id] = h.name;
    }
    return map;
  }, [strategies.data, strategiesV4.data]);

  const deployments = list.data?.deployments ?? [];
  const selectedDeployments = deployments.filter((d) => selectedIds.includes(d.deployment_id));

  useEffect(() => {
    if (!list.data) return;
    const available = new Set(list.data.deployments.map((d) => d.deployment_id));
    setSelectedIds((prev) => prev.filter((id) => available.has(id)));
  }, [list.data]);

  const bulkDelete = useMutation({
    mutationFn: async () => {
      const targets = selectedDeployments;
      const results = await Promise.allSettled(targets.map((d) => DeploymentsApi.delete(d.deployment_id)));
      return targets.map((deployment, index) => ({ deployment, result: results[index] }));
    },
    onSuccess: (results) => {
      const deleted = results.filter(
        (item): item is { deployment: Deployment; result: PromiseFulfilledResult<unknown> } =>
          item.result.status === "fulfilled",
      );
      const failed = results.filter(
        (item): item is { deployment: Deployment; result: PromiseRejectedResult } =>
          item.result.status === "rejected",
      );
      setSelectedIds((prev) =>
        prev.filter((id) => !deleted.some((item) => item.deployment.deployment_id === id)),
      );
      setBulkMessage(
        failed.length === 0
          ? `Deleted ${deleted.length} deployment${deleted.length === 1 ? "" : "s"}.`
          : `Deleted ${deleted.length}; ${failed.length} blocked. ${failed
              .map((item) => `${item.deployment.name}: ${errorText(item.result.reason)}`)
              .join(" ")}`,
      );
      void qc.invalidateQueries({ queryKey: ["deployments", "list"] });
    },
  });

  function toggleSelected(id: string, checked: boolean): void {
    setBulkMessage(null);
    setSelectedIds((prev) =>
      checked ? Array.from(new Set([...prev, id])) : prev.filter((existing) => existing !== id),
    );
  }

  function setAllSelected(checked: boolean): void {
    setBulkMessage(null);
    setSelectedIds(checked ? deployments.map((d) => d.deployment_id) : []);
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Deployments"
        subtitle="Running Strategy publishers. Entries come from Watchlists. Exits come from Account-owned Positions scoped to this Deployment."
        explainSlug="deployments"
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => navigate(ROUTE_DEPLOYMENTS_NEW)}
          >
            New Deployment
          </Button>
        }
      />

      {bulkMessage ? <Banner severity="info" title="Bulk delete result" message={bulkMessage} /> : null}

      {list.isLoading ? (
        <LoadingState title="Loading deployments" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load deployments"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : (list.data?.deployments.length ?? 0) === 0 ? (
        <EmptyState
          title="No deployments yet"
          message="Create a Deployment from a Strategy version, one or more Entry Watchlists, and the Accounts that should subscribe."
          action={
            <Button size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
              New Deployment
            </Button>
          }
        />
      ) : (
        <>
          <BulkDeploymentBar
            selectedCount={selectedIds.length}
            totalCount={deployments.length}
            allSelected={selectedIds.length > 0 && selectedIds.length === deployments.length}
            onSelectAll={setAllSelected}
            onClear={() => setAllSelected(false)}
            onDelete={() => setBulkDeleteOpen(true)}
            busy={bulkDelete.isPending}
          />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {deployments.map((d) => (
            <DeploymentCard
              key={d.deployment_id}
              d={d}
              watchlists={watchlists.data?.watchlists ?? []}
              strategies={strategies.data?.strategies ?? []}
              strategyNameById={strategyNameById}
              selected={selectedIds.includes(d.deployment_id)}
              onSelectedChange={(checked) => toggleSelected(d.deployment_id, checked)}
            />
          ))}
          </div>
        </>
      )}

      <CreateDeploymentDrawer open={createOpen} onOpenChange={setCreateOpen} />
      {/* createOpen kept for legacy drawer fallback; primary path is the 6-step screen */}
      <HoldToArmConfirm
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title={`Delete ${selectedDeployments.length} selected deployment${selectedDeployments.length === 1 ? "" : "s"}?`}
        message={
          <span>
            Bulk delete uses the same guard as single delete. Only draft or stopped Deployments can be deleted;
            active or paused rows are reported as blocked. Hold the verifier for two seconds to unlock delete.
          </span>
        }
        actionLabel="Delete Selected"
        tone="danger"
        busy={bulkDelete.isPending}
        onConfirm={async () => {
          await bulkDelete.mutateAsync();
          setBulkDeleteOpen(false);
        }}
      />
    </div>
  );
}

function BulkDeploymentBar({
  selectedCount,
  totalCount,
  allSelected,
  onSelectAll,
  onClear,
  onDelete,
  busy,
}: {
  selectedCount: number;
  totalCount: number;
  allSelected: boolean;
  onSelectAll: (checked: boolean) => void;
  onClear: () => void;
  onDelete: () => void;
  busy: boolean;
}): JSX.Element {
  return (
    <div className="flex flex-wrap items-center gap-2 rounded border border-border bg-bg-raised px-3 py-2 text-xs">
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={allSelected}
          onChange={(event) => onSelectAll(event.target.checked)}
          aria-label="Select all deployments"
        />
        <span>Select all</span>
      </label>
      <span className="text-fg-muted">
        {selectedCount} of {totalCount} selected
      </span>
      <Button size="sm" variant="danger" disabled={selectedCount === 0} loading={busy} onClick={onDelete}>
        Bulk delete
      </Button>
      {selectedCount > 0 ? (
        <Button size="sm" variant="ghost" onClick={onClear}>
          Clear
        </Button>
      ) : null}
      <span className="ml-auto text-[11px] text-fg-subtle">
        Active and paused Deployments stay protected.
      </span>
    </div>
  );
}

function lifecycleTone(status: Deployment["lifecycle_status"]): "ok" | "warn" | "muted" | "info" {
  switch (status) {
    case "active":
      return "ok";
    case "paused":
      return "warn";
    case "stopped":
      return "muted";
    default:
      return "info";
  }
}

function DeploymentCard({
  d,
  watchlists,
  strategies,
  strategyNameById,
  selected,
  onSelectedChange,
}: {
  d: Deployment;
  watchlists: { watchlist_id: string; name: string; kind: string }[];
  strategies: Strategy[];
  strategyNameById: Record<string, string>;
  selected: boolean;
  onSelectedChange: (checked: boolean) => void;
}): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [stopOpen, setStopOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [rebindOpen, setRebindOpen] = useState(false);

  const start = useMutation({
    mutationFn: () => DeploymentsApi.start(d.deployment_id, "operator start"),
    onSettled: () => qc.invalidateQueries({ queryKey: ["deployments", "list"] }),
  });
  const pause = useMutation({
    mutationFn: () => DeploymentsApi.pause(d.deployment_id, "operator pause"),
    onSettled: () => qc.invalidateQueries({ queryKey: ["deployments", "list"] }),
  });
  const resume = useMutation({
    mutationFn: () => DeploymentsApi.resume(d.deployment_id, "operator resume"),
    onSettled: () => qc.invalidateQueries({ queryKey: ["deployments", "list"] }),
  });
  const stop = useMutation({
    mutationFn: (reason: string) => DeploymentsApi.stop(d.deployment_id, reason),
    onSettled: () => qc.invalidateQueries({ queryKey: ["deployments", "list"] }),
  });
  const remove = useMutation({
    mutationFn: () => DeploymentsApi.delete(d.deployment_id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["deployments", "list"] }),
  });

  const tone = lifecycleTone(d.lifecycle_status);
  const isActive = d.lifecycle_status === "active";
  const watchlistNames = d.watchlist_ids.map(
    (id) => watchlists.find((w) => w.watchlist_id === id)?.name ?? "Watchlist loading",
  );
  // Prefer v4 name, fall back to legacy strategy name lookup.
  const strategyName = (() => {
    if (d.strategy_version_v4_id && strategyNameById[d.strategy_version_v4_id]) {
      return strategyNameById[d.strategy_version_v4_id];
    }
    if (d.strategy_version_id) {
      return (
        strategyNameById[d.strategy_version_id] ??
        strategies.find(
          (s) =>
            s.latest_version_id === d.strategy_version_id ||
            s.frozen_version_ids.includes(d.strategy_version_id!),
        )?.name ??
        "Strategy version"
      );
    }
    return "Strategy version";
  })();

  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <label className="mt-1 flex items-center" title={`Select ${d.name}`}>
          <input
            type="checkbox"
            checked={selected}
            onChange={(event) => onSelectedChange(event.target.checked)}
            aria-label={`Select deployment ${d.name}`}
          />
        </label>
        <div className="min-w-0 flex-1">
          <div className="font-semibold tracking-tight">{d.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge tone={tone}>{d.lifecycle_status}</StatusBadge>
            <span className="flex items-center gap-1 text-xs text-fg-muted">
              <PulseDot tone={tone === "muted" ? "muted" : tone} pulse={isActive} size="sm" />
              {isActive ? "publishing" : "idle"}
            </span>
            <StatusBadge tone="neutral">{d.subscribed_account_ids.length} accounts</StatusBadge>
            <StatusBadge tone="neutral">{watchlistNames.length} entry lists</StatusBadge>
          </div>
        </div>
      </div>
      {d.description ? (
        <div className="px-4 py-2 text-xs text-fg-muted">{d.description}</div>
      ) : null}
      <div className="grid grid-cols-2 gap-2 px-4 py-2 text-xs">
        <div className="flex flex-col gap-0.5">
          <span className="text-fg-subtle">Strategy</span>
          <span>{strategyName}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-fg-subtle">Started</span>
          <span>{d.started_at ? relativeTime(d.started_at) : "—"}</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <span className="text-fg-subtle">Horizon</span>
          <span>
            {d.risk_horizon ? TRADING_HORIZON_LABELS[d.risk_horizon] : "—"}
          </span>
        </div>
      </div>
      <div className="px-4 pb-2 text-xs">
        <div className="text-fg-subtle">Entry Watchlists</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {watchlistNames.slice(0, 3).map((name) => (
            <StatusBadge key={name} tone="neutral" size="sm">
              {name}
            </StatusBadge>
          ))}
          {watchlistNames.length > 3 ? (
            <StatusBadge tone="muted" size="sm">
              +{watchlistNames.length - 3}
            </StatusBadge>
          ) : null}
        </div>
        <div className="mt-1 text-[11px] text-fg-muted">
          Entries come from Watchlists. Exits come from Account-owned Positions scoped to this Deployment.
        </div>
      </div>
      <div className="flex flex-wrap gap-1 border-t border-border/70 px-4 py-2">
        {d.lifecycle_status === "draft" || d.lifecycle_status === "stopped" ? (
          <Button
            size="sm"
            variant="ok"
            leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => start.mutate()}
            loading={start.isPending}
          >
            Start
          </Button>
        ) : null}
        {d.lifecycle_status === "paused" ? (
          <Button
            size="sm"
            variant="ok"
            leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => resume.mutate()}
            loading={resume.isPending}
          >
            Resume
          </Button>
        ) : null}
        {d.lifecycle_status === "active" ? (
          <Button
            size="sm"
            variant="secondary"
            leftIcon={<Pause className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => pause.mutate()}
            loading={pause.isPending}
          >
            Pause
          </Button>
        ) : null}
        {d.lifecycle_status !== "stopped" ? (
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Square className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setStopOpen(true)}
          >
            Stop
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={() => setEditOpen(true)}>
          Edit
        </Button>
        {d.lifecycle_status === "active" ? (
          <Button size="sm" variant="secondary" onClick={() => setRebindOpen(true)}>
            Rebind
          </Button>
        ) : null}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => navigate(deploymentDetailPath(d.deployment_id))}
        >
          Details
        </Button>
        {d.lifecycle_status === "draft" || d.lifecycle_status === "stopped" ? (
          <Button
            size="sm"
            variant="danger"
            leftIcon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setDeleteOpen(true)}
          >
            Delete
          </Button>
        ) : null}
      </div>

      <EditDeploymentDrawer open={editOpen} onOpenChange={setEditOpen} deployment={d} />
      {d.lifecycle_status === "active" ? (
        <RebindDeploymentDrawer
          open={rebindOpen}
          onOpenChange={setRebindOpen}
          deployment={d}
        />
      ) : null}

      <HoldToArmConfirm
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Delete deployment "${d.name}"?`}
        message={<span>Only DRAFT or STOPPED Deployments can be deleted. Hold the verifier for two seconds to unlock delete.</span>}
        actionLabel="Delete Deployment"
        tone="danger"
        busy={remove.isPending}
        onConfirm={async () => {
          await remove.mutateAsync();
          setDeleteOpen(false);
        }}
      />
      <DangerConfirm
        open={stopOpen}
        onOpenChange={setStopOpen}
        title={`Stop deployment "${d.name}"?`}
        message={<span>Type <strong>{d.name}</strong> to confirm. Existing Account positions are unaffected; flatten through Operations if needed.</span>}
        expected={d.name}
        actionLabel="Stop Deployment"
        tone="danger"
        busy={stop.isPending}
        onConfirm={async (reason) => {
          await stop.mutateAsync(reason);
          setStopOpen(false);
        }}
      />
    </Card>
  );
}

function CreateDeploymentDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();

  const strategies = useQuery({ queryKey: ["strategies", "list"], queryFn: () => StrategiesApi.list(), enabled: open });
  const watchlists = useQuery({ queryKey: ["watchlists", "list"], queryFn: () => WatchlistsApi.list(), enabled: open });
  const accounts = useQuery({ queryKey: ["accounts", "list"], queryFn: () => AccountsApi.list(), enabled: open });

  const [name, setName] = useState("");
  const [strategyId, setStrategyId] = useState<string>("");
  const [strategyVersionId, setStrategyVersionId] = useState<string>("");
  const [watchlistIds, setWatchlistIds] = useState<string[]>([]);
  const [accountIds, setAccountIds] = useState<string[]>([]);
  const [riskHorizon, setRiskHorizon] = useState<TradingHorizon | "">("");
  const [error, setError] = useState<string | null>(null);

  const versions = useQuery({
    queryKey: ["strategies", "versions", strategyId],
    queryFn: () => StrategiesApi.listVersions(strategyId),
    enabled: open && Boolean(strategyId),
  });
  const deployableVersions: StrategyVersionRecord[] = useMemo(
    () => versions.data ?? [],
    [versions.data],
  );

  function reset(): void {
    setName("");
    setStrategyId("");
    setStrategyVersionId("");
    setWatchlistIds([]);
    setAccountIds([]);
    setRiskHorizon("");
    setError(null);
  }

  const create = useMutation({
    mutationFn: () =>
      DeploymentsApi.create({
        name: name.trim(),
        description: null,
        strategy_version_id: strategyVersionId,
        watchlist_ids: watchlistIds,
        subscribed_account_ids: accountIds,
        runtime_overrides: {},
        risk_horizon: riskHorizon !== "" ? riskHorizon : null,
      }),
    onSuccess: () => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["deployments", "list"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const valid =
    name.trim().length > 0 &&
    strategyVersionId.length > 0 &&
    watchlistIds.length > 0 &&
    accountIds.length > 0;

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>New Deployment</DrawerTitle>
          <DrawerDescription>
            Pick a Strategy version, one or more Entry Watchlists, and the Accounts that should subscribe.
            The Deployment publishes SignalPlans; each Account decides independently.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not create" message={error} /> : null}
          <TextField label="Display name" value={name} onChange={(e) => setName(e.target.value)} />
          <Select
            label="Strategy"
            value={strategyId}
            onChange={(e) => {
              setStrategyId(e.target.value);
              setStrategyVersionId("");
            }}
          >
            <option value="">Select strategy…</option>
            {(strategies.data?.strategies ?? []).map((s: Strategy) => (
              <option key={s.strategy_id} value={s.strategy_id}>
                {s.name} ({s.version_count} version{s.version_count === 1 ? "" : "s"})
              </option>
            ))}
          </Select>
          <Select
            label="Strategy version"
            value={strategyVersionId}
            onChange={(e) => setStrategyVersionId(e.target.value)}
            disabled={!strategyId}
          >
            <option value="">{strategyId ? "Select version…" : "pick a strategy first"}</option>
            {deployableVersions.map((v) => (
              <option key={v.strategy_version_id} value={v.strategy_version_id}>
                v{v.version} - {v.status === "frozen" && v.frozen_at ? `frozen ${relativeTime(v.frozen_at)}` : v.status}
              </option>
            ))}
          </Select>
          {strategyId && deployableVersions.length === 0 ? (
            <Banner
              severity="warning"
              title="No Strategy versions"
              message="Create a Strategy version before attaching this Deployment."
            />
          ) : null}

          <Select
            label="Risk horizon"
            value={riskHorizon}
            onChange={(e) => setRiskHorizon(e.target.value as TradingHorizon | "")}
            hint="Optional — if left blank, falls back to the Strategy's trading horizon. Deployment chooses horizon; Account chooses RiskPlan; Governor enforces."
          >
            <option value="">— use Strategy default —</option>
            {(Object.entries(TRADING_HORIZON_LABELS) as [TradingHorizon, string][]).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </Select>
          {/* Slice B fix B-RISK-1: when no explicit horizon is declared, the
              Governor will NOT fire the missing-plan rejection rule. Surface
              this so the operator knows enforcement is opt-in. */}
          {riskHorizon === "" ? (
            <Banner
              severity="warning"
              title="Per-horizon RiskPlan enforcement is OFF"
              message="With no explicit risk horizon, the Governor will not require subscribed Accounts to map a RiskPlan for this Deployment. Only AccountRiskConfig limits and the Strategy default horizon's plan (if any) apply."
            />
          ) : null}

          <div>
            <div className="text-xs text-fg-muted">Entry Watchlists</div>
            <div className="mt-1 grid max-h-32 grid-cols-1 gap-1 overflow-y-auto rounded border border-border bg-bg-inset p-2 text-sm">
              {(watchlists.data?.watchlists ?? []).map((w) => (
                <label key={w.watchlist_id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={watchlistIds.includes(w.watchlist_id)}
                    onChange={(e) =>
                      setWatchlistIds((prev) =>
                        e.target.checked
                          ? [...prev, w.watchlist_id]
                          : prev.filter((id) => id !== w.watchlist_id),
                      )
                    }
                  />
                  <span className="truncate">{w.name}</span>
                  <span className="ml-auto text-xs text-fg-muted">{w.kind}</span>
                </label>
              ))}
              {(watchlists.data?.watchlists ?? []).length === 0 ? (
                <span className="text-xs text-fg-muted">No watchlists yet — create one in Watchlists.</span>
              ) : null}
            </div>
          </div>

          <div>
            <div className="text-xs text-fg-muted">Subscribed accounts</div>
            <div className="mt-1 grid max-h-32 grid-cols-1 gap-1 overflow-y-auto rounded border border-border bg-bg-inset p-2 text-sm">
              {(accounts.data?.accounts ?? []).map((a) => (
                <label key={a.id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={accountIds.includes(a.id)}
                    onChange={(e) =>
                      setAccountIds((prev) =>
                        e.target.checked ? [...prev, a.id] : prev.filter((id) => id !== a.id),
                      )
                    }
                  />
                  <span className="truncate">{a.display_name}</span>
                  <span className="ml-auto text-xs text-fg-muted">
                    {a.mode === "BROKER_LIVE" ? "Live" : "Paper"}
                  </span>
                </label>
              ))}
              {(accounts.data?.accounts ?? []).length === 0 ? (
                <span className="text-xs text-fg-muted">No accounts yet — add one in Accounts.</span>
              ) : null}
            </div>
          </div>
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!valid}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Create Deployment
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.detail || e.message : e instanceof Error ? e.message : String(e);
}

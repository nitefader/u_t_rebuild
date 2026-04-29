import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Plus, Square, Trash2 } from "lucide-react";
import { EditDeploymentDrawer } from "./EditDeploymentDrawer";
import { ApiError } from "@/api/client";
import { AccountsApi } from "@/api/accounts";
import { DeploymentsApi } from "@/api/deployments";
import { StrategiesApi } from "@/api/strategies";
import { WatchlistsApi } from "@/api/watchlists";
import type { Deployment } from "@/api/schemas/deployments";
import type { Strategy, StrategyVersionRecord } from "@/api/schemas/strategies";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DangerConfirm } from "@/components/ui/DangerConfirm";
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

export function Deployments(): JSX.Element {
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
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Deployments"
        subtitle="Running Strategy publishers. Entries from Watchlist, exits from Account-owned Positions filtered by deployment_id."
        explainSlug="deployments"
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setCreateOpen(true)}
          >
            New Deployment
          </Button>
        }
      />

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
          message="Create a Deployment from a Strategy version, one or more Watchlists, and the Accounts that should subscribe."
          action={
            <Button size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
              New Deployment
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {list.data?.deployments.map((d) => (
            <DeploymentCard
              key={d.deployment_id}
              d={d}
              watchlists={watchlists.data?.watchlists ?? []}
              strategies={strategies.data?.strategies ?? []}
            />
          ))}
        </div>
      )}

      <CreateDeploymentDrawer open={createOpen} onOpenChange={setCreateOpen} />
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
}: {
  d: Deployment;
  watchlists: { watchlist_id: string; name: string; kind: string }[];
  strategies: Strategy[];
}): JSX.Element {
  const qc = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [stopOpen, setStopOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);

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
  const strategyName =
    strategies.find(
      (s) => s.latest_version_id === d.strategy_version_id || s.frozen_version_ids.includes(d.strategy_version_id),
    )?.name ?? "Strategy version";

  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <div className="min-w-0">
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
          Entries come from Watchlists. Exits come from Account Positions scoped by this deployment.
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

      <DangerConfirm
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Delete deployment "${d.name}"?`}
        message={<span>Type <strong>{d.name}</strong> to confirm. Only DRAFT or STOPPED deployments can be deleted.</span>}
        expected={d.name}
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
            Pick a Strategy version, one or more Watchlists, and the Accounts that should subscribe.
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

          <div>
            <div className="text-xs text-fg-muted">Watchlists</div>
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

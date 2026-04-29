import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Archive, Camera, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { ApiError } from "@/api/client";
import { WatchlistsApi } from "@/api/watchlists";
import type { Watchlist, WatchlistKind, WatchlistSnapshot } from "@/api/schemas/watchlists";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
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
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { DiscoveryScheduleControls } from "@/components/screener/DiscoveryScheduleControls";
import { PageHeader } from "./PageHeader";
import { relativeTime } from "@/lib/format";

export function Watchlists(): JSX.Element {
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: ["watchlists", "list"],
    queryFn: () => WatchlistsApi.list(),
    refetchInterval: 30_000,
  });
  const [createOpen, setCreateOpen] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkArchiveOpen, setBulkArchiveOpen] = useState(false);
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false);
  const [bulkMessage, setBulkMessage] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const watchlists = list.data?.watchlists ?? [];
  const selectedWatchlists = watchlists.filter((w) => selectedIds.includes(w.watchlist_id));

  useEffect(() => {
    const requestedWatchlist = searchParams.get("watchlist");
    if (requestedWatchlist) setSelectedId(requestedWatchlist);
  }, [searchParams]);

  useEffect(() => {
    if (!list.data) return;
    const available = new Set(list.data.watchlists.map((w) => w.watchlist_id));
    setSelectedIds((prev) => prev.filter((id) => available.has(id)));
  }, [list.data]);

  const bulkArchive = useMutation({
    mutationFn: async () => {
      const targets = selectedWatchlists;
      const results = await Promise.allSettled(targets.map((w) => WatchlistsApi.archive(w.watchlist_id)));
      return targets.map((watchlist, index) => ({ watchlist, result: results[index] }));
    },
    onSuccess: (results) => handleBulkResult("Archived", results),
  });

  const bulkDelete = useMutation({
    mutationFn: async () => {
      const targets = selectedWatchlists;
      const results = await Promise.allSettled(targets.map((w) => WatchlistsApi.delete(w.watchlist_id)));
      return targets.map((watchlist, index) => ({ watchlist, result: results[index] }));
    },
    onSuccess: (results) => handleBulkResult("Deleted", results),
  });

  function handleBulkResult(
    verb: "Archived" | "Deleted",
    results: Array<{ watchlist: Watchlist; result: PromiseSettledResult<unknown> }>,
  ): void {
    const succeeded = results.filter(
      (item): item is { watchlist: Watchlist; result: PromiseFulfilledResult<unknown> } =>
        item.result.status === "fulfilled",
    );
    const failed = results.filter(
      (item): item is { watchlist: Watchlist; result: PromiseRejectedResult } =>
        item.result.status === "rejected",
    );
    if (verb === "Deleted") {
      setSelectedIds((prev) =>
        prev.filter((id) => !succeeded.some((item) => item.watchlist.watchlist_id === id)),
      );
    }
    setBulkMessage(
      failed.length === 0
        ? `${verb} ${succeeded.length} Watchlist${succeeded.length === 1 ? "" : "s"}.`
        : `${verb} ${succeeded.length}; ${failed.length} blocked. ${failed
            .map((item) => `${item.watchlist.name}: ${errorText(item.result.reason)}`)
            .join(" ")}`,
    );
    void qc.invalidateQueries({ queryKey: ["watchlists", "list"] });
  }

  function toggleSelected(id: string, checked: boolean): void {
    setBulkMessage(null);
    setSelectedIds((prev) =>
      checked ? Array.from(new Set([...prev, id])) : prev.filter((existing) => existing !== id),
    );
  }

  function setAllSelected(checked: boolean): void {
    setBulkMessage(null);
    setSelectedIds(checked ? watchlists.map((w) => w.watchlist_id) : []);
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Watchlists"
        subtitle="Entry universes only. Deployments read these for entries; exits come from Account-owned Positions."
        explainSlug="watchlists"
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setCreateOpen(true)}
          >
            New Watchlist
          </Button>
        }
      />

      <Banner
        severity="info"
        title="Entries only"
        message="Refreshing a dynamic Watchlist reruns discovery evidence. It does not close, manage, or sync open broker Positions."
      />
      {bulkMessage ? <Banner severity="info" title="Bulk action result" message={bulkMessage} /> : null}

      {list.isLoading ? (
        <LoadingState title="Loading watchlists" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load watchlists"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : (list.data?.watchlists.length ?? 0) === 0 ? (
        <EmptyState
          title="No watchlists yet"
          message="Create a static list here or save matches from a Screener run as a static or dynamic Watchlist."
          action={
            <Button size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
              New Watchlist
            </Button>
          }
        />
      ) : (
        <>
          <BulkWatchlistBar
            selectedCount={selectedIds.length}
            totalCount={watchlists.length}
            allSelected={selectedIds.length > 0 && selectedIds.length === watchlists.length}
            onSelectAll={setAllSelected}
            onClear={() => setAllSelected(false)}
            onArchive={() => setBulkArchiveOpen(true)}
            onDelete={() => setBulkDeleteOpen(true)}
            busy={bulkArchive.isPending || bulkDelete.isPending}
          />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {watchlists.map((w) => (
            <WatchlistCard
              key={w.watchlist_id}
              w={w}
              onOpen={() => setSelectedId(w.watchlist_id)}
              selected={selectedIds.includes(w.watchlist_id)}
              onSelectedChange={(checked) => toggleSelected(w.watchlist_id, checked)}
            />
          ))}
          </div>
        </>
      )}

      <CreateWatchlistDrawer open={createOpen} onOpenChange={setCreateOpen} />
      <WatchlistDetailDrawer
        watchlistId={selectedId}
        onOpenChange={(open) => {
          if (!open) {
            setSelectedId(null);
            if (searchParams.has("watchlist")) setSearchParams({}, { replace: true });
          }
        }}
      />
      <DangerConfirm
        open={bulkArchiveOpen}
        onOpenChange={setBulkArchiveOpen}
        title={`Archive ${selectedWatchlists.length} selected Watchlist${selectedWatchlists.length === 1 ? "" : "s"}?`}
        message={
          <span>
            Archive preserves Watchlist and snapshot history. Active Deployment references remain protected.
            Type <strong>ARCHIVE {selectedWatchlists.length}</strong> to confirm.
          </span>
        }
        expected={`ARCHIVE ${selectedWatchlists.length}`}
        actionLabel="Archive Selected"
        tone="danger"
        busy={bulkArchive.isPending}
        onConfirm={async () => {
          await bulkArchive.mutateAsync();
          setBulkArchiveOpen(false);
        }}
      />
      <DangerConfirm
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title={`Delete ${selectedWatchlists.length} selected Watchlist${selectedWatchlists.length === 1 ? "" : "s"}?`}
        message={
          <span>
            Delete is allowed only when the backend confirms no active Deployment reference and no snapshot audit history.
            Type <strong>DELETE {selectedWatchlists.length}</strong> to confirm.
          </span>
        }
        expected={`DELETE ${selectedWatchlists.length}`}
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

function BulkWatchlistBar({
  selectedCount,
  totalCount,
  allSelected,
  onSelectAll,
  onClear,
  onArchive,
  onDelete,
  busy,
}: {
  selectedCount: number;
  totalCount: number;
  allSelected: boolean;
  onSelectAll: (checked: boolean) => void;
  onClear: () => void;
  onArchive: () => void;
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
          aria-label="Select all watchlists"
        />
        <span>Select all</span>
      </label>
      <span className="text-fg-muted">
        {selectedCount} of {totalCount} selected
      </span>
      <Button size="sm" variant="secondary" disabled={selectedCount === 0} loading={busy} onClick={onArchive}>
        Archive selected
      </Button>
      <Button size="sm" variant="danger" disabled={selectedCount === 0} loading={busy} onClick={onDelete}>
        Bulk delete
      </Button>
      {selectedCount > 0 ? (
        <Button size="sm" variant="ghost" onClick={onClear}>
          Clear
        </Button>
      ) : null}
      <span className="ml-auto text-[11px] text-fg-subtle">
        Snapshot history and active Deployment references stay protected.
      </span>
    </div>
  );
}

function WatchlistCard({
  w,
  onOpen,
  selected,
  onSelectedChange,
}: {
  w: Watchlist;
  onOpen: () => void;
  selected: boolean;
  onSelectedChange: (checked: boolean) => void;
}): JSX.Element {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <label className="mt-1 flex items-center" title={`Select ${w.name}`}>
          <input
            type="checkbox"
            checked={selected}
            onChange={(event) => onSelectedChange(event.target.checked)}
            aria-label={`Select watchlist ${w.name}`}
          />
        </label>
        <div className="min-w-0 flex-1">
          <div className="font-semibold tracking-tight">{w.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge tone={w.kind === "dynamic" ? "info" : "neutral"}>{w.kind}</StatusBadge>
            <StatusBadge tone={w.status === "archived" ? "muted" : "ok"}>{w.status}</StatusBadge>
            <StatusBadge tone="neutral">{sourceLabel(w)}</StatusBadge>
            <StatusBadge tone="neutral">{w.snapshot_count} snapshots</StatusBadge>
          </div>
        </div>
      </div>
      {w.description ? <div className="px-4 py-2 text-xs text-fg-muted">{w.description}</div> : null}
      <div className="px-4 pb-2 text-[11px] text-fg-subtle">
        {w.kind === "dynamic" ? "Refreshable discovery source" : `${w.static_symbols.length} symbols`}
      </div>
      <div className="flex items-center justify-between border-t border-border/70 px-4 py-2 text-xs text-fg-muted">
        <span>Updated {relativeTime(w.updated_at)}</span>
        <Button size="sm" variant="secondary" onClick={onOpen}>
          Open
        </Button>
      </div>
    </Card>
  );
}

function CreateWatchlistDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const kind: WatchlistKind = "static";
  const [symbolsInput, setSymbolsInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setName("");
    setDescription("");
    setSymbolsInput("");
    setError(null);
  }

  const create = useMutation({
    mutationFn: () => {
      const symbols = parseSymbols(symbolsInput);
      return WatchlistsApi.create({
        name: name.trim(),
        description: description.trim() || null,
        kind,
        static_symbols: symbols,
        dynamic_rules: null,
      });
    },
    onSuccess: () => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["watchlists", "list"] });
    },
    onError: (e) => setError(errorText(e)),
  });

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
          <DrawerTitle>New Watchlist</DrawerTitle>
          <DrawerDescription>
            Static lists freeze symbols. Dynamic Watchlists are normally created from a Screener run so refresh evidence is auditable.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not create" message={error} /> : null}
          <Banner
            severity="info"
            title="Dynamic lists come from Screener runs"
            message="Manual Watchlist creation is static. Save matches from a Screener run to create an auditable dynamic refresh Watchlist."
          />
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <TextField
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <TextField
            label="Symbols (comma or space separated)"
            value={symbolsInput}
            onChange={(e) => setSymbolsInput(e.target.value)}
            placeholder="AAPL, MSFT, GOOGL"
          />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!name.trim() || parseSymbols(symbolsInput).length === 0}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Create Watchlist
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function WatchlistDetailDrawer({
  watchlistId,
  onOpenChange,
}: {
  watchlistId: string | null;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: ["watchlists", "detail", watchlistId],
    queryFn: () => WatchlistsApi.get(watchlistId!),
    enabled: watchlistId != null,
  });
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [draftDescription, setDraftDescription] = useState("");
  const [draftSymbols, setDraftSymbols] = useState<string[]>([]);
  const [addInput, setAddInput] = useState("");
  const [editError, setEditError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const w = detail.data?.watchlist;
  const latestSnapshot = latestSnapshotFrom(detail.data?.snapshots ?? []);
  const visibleSymbols =
    w?.kind === "dynamic" && latestSnapshot
      ? latestSnapshot.symbols
      : editing
      ? draftSymbols
      : w?.static_symbols ?? [];

  useEffect(() => {
    if (!w || editing) return;
    setDraftName(w.name);
    setDraftDescription(w.description ?? "");
    setDraftSymbols([...w.static_symbols]);
  }, [w, editing]);

  const snap = useMutation({
    mutationFn: () => WatchlistsApi.takeSnapshot(watchlistId!, "operator-triggered snapshot"),
    onSuccess: () => setActionError(null),
    onError: (e) => setActionError(errorText(e)),
    onSettled: () => invalidateWatchlist(qc, watchlistId),
  });
  const refresh = useMutation({
    mutationFn: () => WatchlistsApi.refresh(watchlistId!, "operator-triggered refresh"),
    onSuccess: () => setActionError(null),
    onError: (e) => setActionError(errorText(e)),
    onSettled: () => invalidateWatchlist(qc, watchlistId),
  });
  const archive = useMutation({
    mutationFn: () => WatchlistsApi.archive(watchlistId!),
    onSuccess: () => {
      setActionError(null);
      invalidateWatchlist(qc, watchlistId);
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: () => WatchlistsApi.delete(watchlistId!),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["watchlists", "list"] });
      onOpenChange(false);
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const save = useMutation({
    mutationFn: () => {
      if (!w) throw new Error("watchlist not loaded");
      return WatchlistsApi.update(w.watchlist_id, {
        name: draftName.trim(),
        description: draftDescription.trim() || null,
        kind: w.kind,
        static_symbols: draftSymbols,
        dynamic_rules: w.dynamic_rules ?? null,
      });
    },
    onSuccess: () => {
      setEditing(false);
      setEditError(null);
      invalidateWatchlist(qc, watchlistId);
    },
    onError: (e) => setEditError(errorText(e)),
  });

  function addSymbolsFromInput(): void {
    const next = parseSymbols(addInput);
    if (next.length === 0) return;
    setDraftSymbols((prev) => Array.from(new Set([...prev, ...next])));
    setAddInput("");
  }

  function removeSymbol(sym: string): void {
    setDraftSymbols((prev) => prev.filter((s) => s !== sym));
  }

  return (
    <Drawer open={watchlistId != null} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>{w?.name ?? "Watchlist"}</DrawerTitle>
          <DrawerDescription>
            Entry Watchlist detail. Refresh or snapshot creates auditable history for Deployment entry evaluation.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {detail.isLoading ? <LoadingState title="Loading" /> : null}
          {detail.isError ? (
            <ErrorState title="Could not load watchlist" detail={(detail.error as Error)?.message} onRetry={() => detail.refetch()} />
          ) : null}
          {actionError ? <Banner severity="danger" title="Action failed" message={actionError} /> : null}
          {w ? (
            <Card>
              <CardHeader>
                <CardTitle>Details</CardTitle>
                <span className="flex flex-wrap items-center gap-2">
                  <StatusBadge tone={w.kind === "dynamic" ? "info" : "neutral"}>{w.kind}</StatusBadge>
                  <StatusBadge tone={w.status === "archived" ? "muted" : "ok"}>{w.status}</StatusBadge>
                  <StatusBadge tone="neutral">{sourceLabel(w)}</StatusBadge>
                  {!editing ? (
                    <Button size="sm" variant="ghost" leftIcon={<Pencil className="h-3.5 w-3.5" aria-hidden="true" />} onClick={() => setEditing(true)}>
                      Edit
                    </Button>
                  ) : null}
                </span>
              </CardHeader>
              <CardBody className="space-y-2">
                {editing ? (
                  <>
                    <TextField label="Name" value={draftName} onChange={(e) => setDraftName(e.target.value)} />
                    <TextField label="Description (optional)" value={draftDescription} onChange={(e) => setDraftDescription(e.target.value)} />
                  </>
                ) : (
                  <>
                    <div className="text-xs text-fg-muted">Name</div>
                    <div>{w.name}</div>
                    <div className="mt-2 text-xs text-fg-muted">Description</div>
                    <div>{w.description ?? "-"}</div>
                  </>
                )}
              </CardBody>
            </Card>
          ) : null}
          {w ? (
            <DiscoveryScheduleControls
              targetKind="watchlist_refresh"
              targetName={w.name}
              watchlistId={w.watchlist_id}
            />
          ) : null}
          {w ? (
            <Card>
              <CardHeader>
                <CardTitle>
                  {w.kind === "dynamic" ? "Current refresh symbols" : "Symbols"} ({visibleSymbols.length})
                </CardTitle>
                {editError ? <StatusBadge tone="danger">save failed</StatusBadge> : null}
              </CardHeader>
              <CardBody className="space-y-2">
                {editing && editError ? <Banner severity="danger" title="Update failed" message={editError} /> : null}
                {w.kind === "dynamic" && latestSnapshot ? (
                  <div className="rounded bg-bg-inset px-2 py-1 text-[11px] text-fg-muted">
                    From {latestSnapshot.source_label ?? latestSnapshot.note ?? "latest refresh"} / taken {relativeTime(latestSnapshot.taken_at)}
                  </div>
                ) : null}
                {editing && w.kind === "static" ? (
                  <div className="flex items-end gap-2">
                    <TextField
                      label="Add symbols (comma or space separated)"
                      value={addInput}
                      onChange={(e) => setAddInput(e.target.value.toUpperCase())}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addSymbolsFromInput();
                        }
                      }}
                      placeholder="MSFT GOOGL"
                      className="flex-1"
                    />
                    <Button size="sm" variant="secondary" onClick={addSymbolsFromInput} disabled={!addInput.trim()}>
                      Add
                    </Button>
                  </div>
                ) : null}
                {visibleSymbols.length === 0 ? (
                  <EmptyState title="No static symbols" message={w.kind === "dynamic" ? "Dynamic symbols come from refresh snapshots." : "Edit to add symbols."} />
                ) : (
                  <div className="flex flex-wrap gap-1.5">
                    {visibleSymbols.map((sym) => (
                      <span key={sym} className="inline-flex items-center gap-1 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-[11px]">
                        {sym}
                        {editing && w.kind === "static" ? (
                          <button type="button" aria-label={`Remove ${sym}`} onClick={() => removeSymbol(sym)} className="text-fg-subtle hover:text-danger">
                            x
                          </button>
                        ) : null}
                      </span>
                    ))}
                  </div>
                )}
              </CardBody>
            </Card>
          ) : null}
          {detail.data && detail.data.snapshots.length > 0 ? (
            <SnapshotsCard snapshots={detail.data.snapshots} />
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          {editing ? (
            <>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setEditing(false);
                  setEditError(null);
                  if (w) {
                    setDraftName(w.name);
                    setDraftDescription(w.description ?? "");
                    setDraftSymbols([...w.static_symbols]);
                  }
                  setAddInput("");
                }}
              >
                Cancel
              </Button>
              <Button size="sm" variant="primary" disabled={!draftName.trim()} loading={save.isPending} onClick={() => save.mutate()}>
                Save
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="primary"
                size="sm"
                leftIcon={w?.kind === "dynamic" ? <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" /> : <Camera className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() => (w?.kind === "dynamic" ? refresh.mutate() : snap.mutate())}
                loading={refresh.isPending || snap.isPending}
                disabled={!w || w.status === "archived"}
              >
                {w?.kind === "dynamic" ? "Refresh" : "Take Snapshot"}
              </Button>
              <Button
                variant="secondary"
                size="sm"
                leftIcon={<Archive className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() => archive.mutate()}
                loading={archive.isPending}
                disabled={!w || w.status === "archived"}
              >
                Archive
              </Button>
              <Button
                variant="danger"
                size="sm"
                leftIcon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() => setDeleteOpen(true)}
              >
                Delete
              </Button>
            </>
          )}
        </DrawerFooter>
      </DrawerContent>
      <DangerConfirm
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Delete watchlist "${w?.name ?? ""}"?`}
        message={
          <span>
            Archive preserves run and snapshot history. Delete is allowed only when the backend confirms no active
            reference depends on this Watchlist. Type <strong>{w?.name}</strong> to confirm.
          </span>
        }
        expected={w?.name ?? ""}
        actionLabel="Delete Watchlist"
        tone="danger"
        busy={remove.isPending}
        onConfirm={async () => {
          await remove.mutateAsync();
          setDeleteOpen(false);
        }}
      />
    </Drawer>
  );
}

function SnapshotsCard({ snapshots }: { snapshots: WatchlistSnapshot[] }): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Snapshots</CardTitle>
        <StatusBadge>{snapshots.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        <table className="ut-table">
          <thead>
            <tr>
              <th>Taken</th>
              <th>Source</th>
              <th>Symbols</th>
              <th>Diff</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {snapshots.map((s) => (
              <tr key={s.watchlist_snapshot_id}>
                <td className="text-fg-muted">{relativeTime(s.taken_at)}</td>
                <td className="text-fg-muted">{s.source_label ?? s.note ?? "manual snapshot"}</td>
                <td className="tabular">{s.symbols.length}</td>
                <td className="text-fg-muted">{snapshotDiffText(s)}</td>
                <td className="text-fg-muted">{evidenceSummary(s.evidence)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

function sourceLabel(w: Watchlist): string {
  if (w.kind !== "dynamic") return "static entries";
  const source = w.dynamic_rules?.source_type ?? "manual_rules";
  if (source === "screener_version") return "Screener refresh";
  if (source === "template") return "Template refresh";
  return "manual rules";
}

function snapshotDiffText(snapshot: WatchlistSnapshot): string {
  return `+${snapshot.added_symbols.length} / -${snapshot.removed_symbols.length} / =${snapshot.stayed_symbols.length}`;
}

function evidenceSummary(record: Record<string, unknown>): string {
  const keys = Object.keys(record);
  if (keys.length === 0) return "retained by backend";
  return keys.slice(0, 3).join(", ");
}

function latestSnapshotFrom(snapshots: WatchlistSnapshot[]): WatchlistSnapshot | null {
  if (snapshots.length === 0) return null;
  return [...snapshots].sort((a, b) => b.taken_at.localeCompare(a.taken_at))[0] ?? null;
}

function invalidateWatchlist(qc: ReturnType<typeof useQueryClient>, watchlistId: string | null): void {
  void qc.invalidateQueries({ queryKey: ["watchlists", "list"] });
  void qc.invalidateQueries({ queryKey: ["watchlists", "detail", watchlistId] });
}

function parseSymbols(input: string): string[] {
  return input
    .split(/[,\s]+/)
    .map((sym) => sym.trim().toUpperCase())
    .filter(Boolean);
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.detail || e.message : String(e);
}

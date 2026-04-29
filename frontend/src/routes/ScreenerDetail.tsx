import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArrowLeft, GitCompare, Play, RefreshCw, Save, Trash2 } from "lucide-react";
import { ApiError } from "@/api/client";
import { ScreenerApi } from "@/api/screener";
import { WatchlistsApi } from "@/api/watchlists";
import type {
  SaveAsWatchlistRequest,
  Screener,
  ScreenerCriterion,
  ScreenerRun,
  ScreenerRunDiff,
  ScreenerUniverseSource,
  ScreenerVersion,
} from "@/api/schemas/screener";
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
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { CriteriaEditor } from "@/components/screener/CriteriaEditor";
import { DiscoveryScheduleControls } from "@/components/screener/DiscoveryScheduleControls";
import { ExpressionPreview } from "@/components/screener/ExpressionPreview";
import { ResultsTable } from "@/components/screener/ResultsTable";
import { UniverseSourcePicker } from "@/components/screener/UniverseSourcePicker";
import { PageHeader } from "./PageHeader";
import { formatTimestamp, relativeTime } from "@/lib/format";

/**
 * ScreenerDetail: run, rerun, compare, archive, and save entry Watchlists.
 *
 * Guardrails:
 * - Deployment still emits SignalPlans only.
 * - Screeners never submit orders and never manage exits.
 * - Dynamic Watchlists are refreshable entry universes, not position truth.
 */
export function ScreenerDetail(): JSX.Element {
  const params = useParams();
  const screenerId = params.screenerId ?? "";
  const navigate = useNavigate();
  const qc = useQueryClient();

  const detail = useQuery({
    queryKey: ["screeners", "detail", screenerId],
    queryFn: () => ScreenerApi.get(screenerId),
    enabled: Boolean(screenerId),
  });
  const runs = useQuery({
    queryKey: ["screeners", "runs", screenerId],
    queryFn: () => ScreenerApi.listRuns(screenerId),
    enabled: Boolean(screenerId),
    refetchInterval: 15_000,
  });
  const fields = useQuery({
    queryKey: ["screener", "fields"],
    queryFn: () => ScreenerApi.fields(),
    staleTime: 5 * 60_000,
  });
  const watchlists = useQuery({
    queryKey: ["watchlists", "list"],
    queryFn: () => WatchlistsApi.list(),
    staleTime: 60_000,
  });

  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [saveOpen, setSaveOpen] = useState(false);
  const [diff, setDiff] = useState<ScreenerRunDiff | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: () => ScreenerApi.run(screenerId, {}),
    onSuccess: (r) => {
      setActiveRunId(r.id);
      setDiff(null);
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["screeners", "detail", screenerId] });
      void qc.invalidateQueries({ queryKey: ["screeners", "runs", screenerId] });
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const rerun = useMutation({
    mutationFn: (runId: string) => ScreenerApi.rerun(runId, {}),
    onSuccess: (r) => {
      setActiveRunId(r.id);
      setDiff(null);
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["screeners", "detail", screenerId] });
      void qc.invalidateQueries({ queryKey: ["screeners", "runs", screenerId] });
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const archive = useMutation({
    mutationFn: () => ScreenerApi.archive(screenerId),
    onSuccess: () => {
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["screeners"] });
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const deleteMutation = useMutation({
    mutationFn: () => ScreenerApi.delete(screenerId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["screeners", "list"] });
      navigate("/screeners");
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const diffMutation = useMutation({
    mutationFn: ({ runId, againstRunId }: { runId: string; againstRunId: string }) =>
      ScreenerApi.diffRuns(runId, againstRunId),
    onSuccess: (resp) => {
      setDiff(resp);
      setActionError(null);
    },
    onError: (e) => setActionError(errorText(e)),
  });

  const runList = runs.data?.runs ?? [];
  useEffect(() => {
    if (!activeRunId && runList.length > 0) setActiveRunId(runList[0].id);
  }, [runList, activeRunId]);

  const activeRun = runList.find((r) => r.id === activeRunId) ?? runList[0] ?? null;
  const previousRun = useMemo(() => {
    if (!activeRun) return null;
    const idx = runList.findIndex((r) => r.id === activeRun.id);
    return idx >= 0
      ? (runList[idx + 1] ?? null)
      : (runList.find((r) => r.id !== activeRun.id) ?? null);
  }, [activeRun, runList]);

  const screener = detail.data?.screener;
  const versions = detail.data?.versions ?? [];
  const latestVersion: ScreenerVersion | undefined = versions[versions.length - 1];

  return (
    <div className="space-y-4">
      <PageHeader
        title={screener?.name ?? "Screener"}
        subtitle="Discovery and entry-universe management. Exits remain Account-owned Position evaluation."
        explainSlug="screener-detail"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Link to="/screeners">
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />}
              >
                Back
              </Button>
            </Link>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setEditOpen(true)}
              disabled={!latestVersion}
            >
              Customize version
            </Button>
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Archive className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => archive.mutate()}
              loading={archive.isPending}
              disabled={!screener || screener.status === "archived"}
            >
              Archive
            </Button>
            <Button
              size="sm"
              variant="primary"
              leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => run.mutate()}
              loading={run.isPending}
              disabled={!latestVersion || screener?.status === "archived"}
            >
              Run latest version
            </Button>
          </div>
        }
      />

      {detail.isLoading ? <LoadingState title="Loading screener" /> : null}
      {detail.isError ? (
        <ErrorState
          title="Could not load screener"
          detail={(detail.error as Error)?.message}
          onRetry={() => detail.refetch()}
        />
      ) : null}
      {actionError ? (
        <Banner severity="danger" title="Action failed" message={actionError} />
      ) : null}

      {screener && latestVersion ? (
        <ScreenerOverview
          screener={screener}
          version={latestVersion}
          watchlistName={watchlistNameFor(latestVersion, watchlists.data?.watchlists ?? [])}
          onDelete={() => setDeleteOpen(true)}
        />
      ) : null}

      {screener && latestVersion ? (
        <DiscoveryScheduleControls
          targetKind="screener_run"
          targetName={`${screener.name} v${latestVersion.version}`}
          screenerId={screener.id}
          screenerVersionId={latestVersion.id}
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Recent runs</CardTitle>
          <StatusBadge tone="neutral">{runList.length}</StatusBadge>
        </CardHeader>
        <CardBody className="space-y-2">
          {runList.length === 0 ? (
            <EmptyState
              title="No runs yet"
              message="Run the Screener to compute feature and broker capability evidence for the universe."
              action={
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => run.mutate()}
                  loading={run.isPending}
                  leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
                >
                  Run latest version
                </Button>
              }
            />
          ) : (
            <RunTabs
              runs={runList}
              activeRunId={activeRun?.id ?? null}
              onSelect={(id) => {
                setActiveRunId(id);
                setDiff(null);
              }}
            />
          )}
        </CardBody>
      </Card>

      {activeRun ? (
        <Card>
          <CardHeader>
            <CardTitle>
              Results: {activeRun.matched_count} match
              {activeRun.matched_count === 1 ? "" : "es"} of {activeRun.universe_size}
            </CardTitle>
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] text-fg-muted">
                Selected run: {relativeTime(activeRun.started_at)}
              </span>
              <StatusBadge tone="neutral">{runKindLabel(activeRun.run_kind)}</StatusBadge>
              {activeRun.cache_hit_rate !== null && activeRun.cache_hit_rate !== undefined ? (
                <StatusBadge tone="info">
                  cache {(activeRun.cache_hit_rate * 100).toFixed(0)}%
                </StatusBadge>
              ) : null}
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() => rerun.mutate(activeRun.id)}
                loading={rerun.isPending}
              >
                Rerun selected run
              </Button>
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<GitCompare className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() =>
                  previousRun &&
                  diffMutation.mutate({ runId: activeRun.id, againstRunId: previousRun.id })
                }
                loading={diffMutation.isPending}
                disabled={!previousRun}
              >
                Compare with previous run
              </Button>
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<Save className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() => setSaveOpen(true)}
                disabled={activeRun.matched_count === 0}
              >
                Save matched symbols as Watchlist
              </Button>
            </span>
          </CardHeader>
          <CardBody className="space-y-3">
            <RunEvidence run={activeRun} />
            {diff ? <RunDiffPanel diff={diff} /> : null}
            <ResultsTable results={[...activeRun.results]} metrics={fields.data?.fields ?? []} />
          </CardBody>
        </Card>
      ) : null}

      {screener && latestVersion ? (
        <DangerConfirm
          open={deleteOpen}
          onOpenChange={setDeleteOpen}
          title={`Delete screener "${screener.name}"?`}
          message={
            <span>
              Archive first when history matters. Delete is allowed only when the backend confirms
              no retained run lineage depends on this Screener. Type{" "}
              <strong>{screener.name}</strong> to confirm.
            </span>
          }
          expected={screener.name}
          actionLabel="Delete Screener"
          tone="danger"
          busy={deleteMutation.isPending}
          onConfirm={async () => {
            await deleteMutation.mutateAsync();
            setDeleteOpen(false);
          }}
        />
      ) : null}

      {screener && latestVersion ? (
        <NewVersionDrawer
          open={editOpen}
          onOpenChange={setEditOpen}
          screenerId={screenerId}
          baseVersion={latestVersion}
          screenerName={screener.name}
        />
      ) : null}

      {activeRun ? (
        <SaveAsWatchlistDrawer open={saveOpen} onOpenChange={setSaveOpen} run={activeRun} />
      ) : null}
    </div>
  );
}

function ScreenerOverview({
  screener,
  version,
  watchlistName,
  onDelete,
}: {
  screener: Screener;
  version: ScreenerVersion;
  watchlistName: string | null;
  onDelete: () => void;
}): JSX.Element {
  const criteriaCount = criteriaFromVersion(version).length;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Overview</CardTitle>
        <span className="flex flex-wrap items-center gap-2">
          <StatusBadge
            tone={
              screener.status === "active"
                ? "ok"
                : screener.status === "archived"
                  ? "muted"
                  : "info"
            }
          >
            {prettyKey(screener.status)}
          </StatusBadge>
          <StatusBadge tone="neutral">v{version.version}</StatusBadge>
          <StatusBadge tone="info">{criteriaCount} rules</StatusBadge>
          <Button
            variant="danger"
            size="sm"
            leftIcon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={onDelete}
          >
            Delete
          </Button>
        </span>
      </CardHeader>
      <CardBody className="grid grid-cols-1 gap-3 text-xs md:grid-cols-3">
        <div>
          <div className="text-fg-muted">Universe source</div>
          <div className="mt-0.5">{describeUniverse(version.universe_source, watchlistName)}</div>
        </div>
        <div>
          <div className="text-fg-muted">Sort by</div>
          <div className="mt-0.5">
            {version.sort_metric
              ? `${prettyKey(version.sort_metric)} / ${version.sort_descending ? "High to low" : "Low to high"}`
              : "Matched first"}
          </div>
        </div>
        <div>
          <div className="text-fg-muted">Created</div>
          <div className="mt-0.5" title={version.created_at}>
            {formatTimestamp(version.created_at)}
          </div>
        </div>
      </CardBody>
    </Card>
  );
}

function RunTabs({
  runs,
  activeRunId,
  onSelect,
}: {
  runs: ScreenerRun[];
  activeRunId: string | null;
  onSelect: (id: string) => void;
}): JSX.Element {
  return (
    <div className="flex flex-wrap gap-1">
      {runs.slice(0, 10).map((r) => (
        <button
          key={r.id}
          type="button"
          onClick={() => onSelect(r.id)}
          className={
            r.id === activeRunId
              ? "rounded border border-accent bg-accent/20 px-2 py-1 text-[11px] text-accent"
              : "rounded border border-border bg-bg-raised px-2 py-1 text-[11px] text-fg-muted hover:text-fg"
          }
          title={r.started_at}
        >
          <span className="font-medium">{relativeTime(r.started_at)}</span>
          <StatusBadge
            tone={r.status === "completed" ? "ok" : r.status === "failed" ? "danger" : "neutral"}
            size="sm"
            className="ml-1"
          >
            {prettyKey(r.status)}
          </StatusBadge>
          <span className="ml-1 text-fg-muted">
            {r.matched_count}/{r.universe_size}
          </span>
        </button>
      ))}
    </div>
  );
}

function RunEvidence({ run }: { run: ScreenerRun }): JSX.Element {
  const freshness = sourceRecordSummary(run.source_freshness);
  const evidence = sourceRecordSummary(run.source_evidence);
  return (
    <div className="grid grid-cols-1 gap-2 rounded border border-border bg-bg-inset/40 p-2 text-[11px] md:grid-cols-3">
      <div>
        <div className="font-semibold uppercase tracking-wide text-fg-muted">Sources</div>
        <div className="mt-1 flex flex-wrap gap-1">
          {run.sources_used.length ? (
            run.sources_used.map((source) => (
              <StatusBadge key={source} tone="info" size="sm">
                {sourceLabelFromKey(source)}
              </StatusBadge>
            ))
          ) : (
            <span className="text-fg-subtle">No source evidence recorded</span>
          )}
        </div>
      </div>
      <div>
        <div className="font-semibold uppercase tracking-wide text-fg-muted">Freshness</div>
        <div className="mt-1 text-fg-muted">{freshness || "not reported"}</div>
      </div>
      <div>
        <div className="font-semibold uppercase tracking-wide text-fg-muted">Audit</div>
        <div className="mt-1 text-fg-muted">
          {run.parent_run_id ? "Rerun lineage recorded" : "Initial run"} /{" "}
          {evidence || "provider evidence retained"}
        </div>
      </div>
    </div>
  );
}

function RunDiffPanel({ diff }: { diff: ScreenerRunDiff }): JSX.Element {
  return (
    <div className="grid grid-cols-2 gap-2 rounded border border-border bg-bg-raised p-2 text-xs md:grid-cols-4">
      <DiffBucket label="Added" symbols={diff.added} tone="ok" />
      <DiffBucket label="Removed" symbols={diff.removed} tone="warn" />
      <DiffBucket label="Stayed" symbols={diff.stayed} tone="neutral" />
      <DiffBucket label="Newly failed" symbols={diff.newly_failed} tone="danger" />
    </div>
  );
}

function DiffBucket({
  label,
  symbols,
  tone,
}: {
  label: string;
  symbols: string[];
  tone: "ok" | "warn" | "danger" | "neutral";
}): JSX.Element {
  return (
    <div>
      <div className="flex items-center gap-1">
        <StatusBadge tone={tone} size="sm">
          {symbols.length}
        </StatusBadge>
        <span className="font-medium">{label}</span>
      </div>
      <div className="mt-1 truncate text-[11px] text-fg-muted">
        {symbols.slice(0, 8).join(", ") || "-"}
      </div>
    </div>
  );
}

function NewVersionDrawer({
  open,
  onOpenChange,
  screenerId,
  baseVersion,
  screenerName,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  screenerId: string;
  baseVersion: ScreenerVersion;
  screenerName: string;
}): JSX.Element {
  const qc = useQueryClient();
  const fields = useQuery({
    queryKey: ["screener", "fields"],
    queryFn: () => ScreenerApi.fields(),
    staleTime: 5 * 60_000,
  });
  const [criteria, setCriteria] = useState<ScreenerCriterion[]>(() =>
    criteriaFromVersion(baseVersion),
  );
  const [universe, setUniverse] = useState(baseVersion.universe_source);
  const [name, setName] = useState(baseVersion.name);
  const [error, setError] = useState<string | null>(null);
  const expressionLocked =
    Boolean(baseVersion.expression) && !isFlatEditableExpression(baseVersion.expression);

  const create = useMutation({
    mutationFn: () =>
      ScreenerApi.addVersion(screenerId, {
        name: name.trim(),
        description: baseVersion.description ?? null,
        tags: [...baseVersion.tags],
        universe_source: universe,
        criteria: expressionLocked ? [...baseVersion.criteria] : criteria,
        expression: expressionLocked ? baseVersion.expression : null,
        timeframe: baseVersion.timeframe,
        source_preference: baseVersion.source_preference,
        sort_metric: baseVersion.sort_metric ?? null,
        sort_descending: baseVersion.sort_descending,
        max_results: baseVersion.max_results,
      }),
    onSuccess: () => {
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["screeners"] });
    },
    onError: (e) => setError(errorText(e)),
  });

  useEffect(() => {
    if (open) {
      setCriteria(criteriaFromVersion(baseVersion));
      setUniverse(baseVersion.universe_source);
      setName(baseVersion.name);
      setError(null);
    }
  }, [open, baseVersion]);

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-w-3xl">
        <DrawerHeader>
          <DrawerTitle>Customize version: {screenerName}</DrawerTitle>
          <DrawerDescription>
            Existing versions stay immutable. This creates a new version you can run, schedule, and
            save as a Watchlist later.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? (
            <Banner severity="danger" title="Could not save version" message={error} />
          ) : null}
          <TextField label="Version name" value={name} onChange={(e) => setName(e.target.value)} />
          <UniverseSourcePicker value={universe} onChange={setUniverse} />
          {expressionLocked ? (
            <div className="space-y-2">
              <Banner
                severity="info"
                title="Compiled logic preserved"
                message="This version keeps the ALL/ANY/NOT tree intact. Use AI Composer or a template when you need to change grouped logic."
              />
              <ExpressionPreview
                expression={baseVersion.expression}
                title="Preserved boolean tree"
              />
            </div>
          ) : (
            <div className="space-y-2">
              {baseVersion.expression ? (
                <Banner
                  severity="info"
                  title="Template logic converted to editable rules"
                  message="You can add, remove, or change the criteria here. Saving creates a new Screener version."
                />
              ) : null}
              <CriteriaEditor
                value={criteria}
                onChange={setCriteria}
                metrics={fields.data?.fields ?? []}
              />
            </div>
          )}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!name.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Save customized version
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function SaveAsWatchlistDrawer({
  open,
  onOpenChange,
  run,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  run: ScreenerRun;
}): JSX.Element {
  const navigate = useNavigate();
  const [name, setName] = useState(`Screener matches - ${relativeTime(run.started_at)}`);
  const [description, setDescription] = useState<string>("");
  const [kind, setKind] = useState<SaveAsWatchlistRequest["kind"]>("static");
  const [error, setError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setName(`Screener matches - ${relativeTime(run.started_at)}`);
      setDescription("");
      setKind("static");
      setError(null);
      setSavedId(null);
    }
  }, [open, run.started_at]);

  const save = useMutation({
    mutationFn: () =>
      ScreenerApi.saveRunAsWatchlist(run.id, {
        name: name.trim(),
        description: description.trim() || null,
        only_matched: true,
        kind,
      }),
    onSuccess: (resp) => setSavedId(resp.watchlist_id),
    onError: (e) => setError(errorText(e)),
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-w-md">
        <DrawerHeader>
          <DrawerTitle>Save matched symbols as Watchlist</DrawerTitle>
          <DrawerDescription>
            Creates a new entry Watchlist. Static freezes symbols; dynamic refreshes from this
            Screener lineage.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not save" message={error} /> : null}
          {savedId ? (
            <Banner
              severity="success"
              title="Watchlist created"
              message={
                <span>
                  {run.matched_count} matched symbols saved.{" "}
                  <button
                    className="underline"
                    onClick={() => navigate(`/watchlists?watchlist=${savedId}`)}
                  >
                    Open created Watchlist
                  </button>
                </span>
              }
            />
          ) : (
            <>
              <TextField
                label="Watchlist name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <TextField
                label="Description (optional)"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="From Screener run"
              />
              <Select
                label="Watchlist kind"
                value={kind}
                onChange={(e) => setKind(e.target.value as SaveAsWatchlistRequest["kind"])}
              >
                <option value="static">Static entry list</option>
                <option value="dynamic">Dynamic Screener refresh</option>
              </Select>
              <div className="rounded bg-bg-inset px-2 py-1 text-[11px] text-fg-muted">
                {run.matched_count} matched symbols will be included. Dynamic refreshes rerun
                discovery; it does not manage open Positions.
              </div>
            </>
          )}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {!savedId ? (
            <Button
              variant="primary"
              size="sm"
              loading={save.isPending}
              disabled={!name.trim() || run.matched_count === 0}
              onClick={() => save.mutate()}
            >
              Create Watchlist
            </Button>
          ) : null}
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function describeUniverse(source: ScreenerUniverseSource, watchlistName: string | null): string {
  if (source.kind === "market_list")
    return `Alpaca Market List / ${prettyKey(source.market_list_key ?? "market_list")}`;
  if (source.kind === "preset") return `Preset / ${prettyKey(source.preset ?? "preset")}`;
  if (source.kind === "watchlist") return `Watchlist / ${watchlistName ?? "loading"}`;
  return `Explicit / ${(source.symbols ?? []).length} symbols`;
}

function prettyKey(key: string): string {
  return key
    .split("_")
    .join(" ")
    .split(".")
    .join(" ")
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => (w.toLowerCase() === "alpaca" ? "Alpaca" : w.charAt(0).toUpperCase() + w.slice(1)))
    .join(" ");
}

function runKindLabel(kind: string): string {
  if (kind === "run") return "Initial run";
  if (kind === "rerun") return "Rerun";
  if (kind === "scheduled") return "Scheduled run";
  return prettyKey(kind);
}

function watchlistNameFor(
  version: ScreenerVersion,
  watchlists: { watchlist_id: string; name: string }[],
): string | null {
  const id = version.universe_source.watchlist_id;
  if (!id) return null;
  return watchlists.find((w) => w.watchlist_id === id)?.name ?? null;
}

function criteriaFromVersion(version: ScreenerVersion): ScreenerCriterion[] {
  if (version.criteria.length) return [...version.criteria];
  return criteriaFromExpression(version.expression);
}

function criteriaFromExpression(expr: unknown): ScreenerCriterion[] {
  const node = expr as {
    kind?: string;
    criterion?: ScreenerCriterion | null;
    children?: unknown[];
  } | null;
  if (!node || typeof node !== "object") return [];
  if (node.kind === "criterion" && node.criterion) return [node.criterion];
  return (node.children ?? []).flatMap(criteriaFromExpression);
}

function isFlatEditableExpression(expr: unknown): boolean {
  const node = expr as {
    kind?: string;
    criterion?: ScreenerCriterion | null;
    children?: unknown[];
  } | null;
  if (!node || typeof node !== "object") return true;
  if (node.kind === "criterion") return Boolean(node.criterion);
  if (node.kind !== "all") return false;
  return (node.children ?? []).every((child) => {
    const childNode = child as { kind?: string; criterion?: ScreenerCriterion | null } | null;
    return Boolean(childNode && childNode.kind === "criterion" && childNode.criterion);
  });
}

function sourceRecordSummary(record: Record<string, unknown>): string {
  return Object.entries(record)
    .slice(0, 3)
    .map(([key, value]) => {
      if (value && typeof value === "object") {
        const obj = value as Record<string, unknown>;
        return sourceObjectSummary(key, obj);
      }
      return `${sourceLabelFromKey(key)}: ${String(value)}`;
    })
    .join(" / ");
}

function sourceObjectSummary(key: string, obj: Record<string, unknown>): string {
  const label = sourceLabelFromKey(key);
  const asOf = typeof obj.as_of === "string" ? formatTimestamp(obj.as_of) : null;
  const feed = typeof obj.feed === "string" ? obj.feed.toUpperCase() : null;
  const provider = typeof obj.provider === "string" ? prettyKey(obj.provider) : null;
  const status = typeof obj.status === "string" ? prettyKey(obj.status) : null;
  const source = typeof obj.source === "string" ? sourceLabelFromKey(obj.source) : null;
  const details = [asOf, feed, provider, status, source].filter(Boolean);
  return details.length ? `${label}: ${details.join(", ")}` : label;
}

function sourceLabelFromKey(key: string): string {
  const labels: Record<string, string> = {
    alpaca: "Alpaca",
    alpaca_assets: "Alpaca asset capability",
    alpaca_market_list: "Alpaca market list",
    alpaca_bars: "Alpaca bars",
    data_center: "Data Center cache",
    historical_dataset: "Historical dataset",
    screener_run: "Screener run",
  };
  return labels[key] ?? prettyKey(key);
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.detail || e.message : String(e);
}

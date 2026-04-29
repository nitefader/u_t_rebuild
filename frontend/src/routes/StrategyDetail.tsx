import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Lock, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { StrategiesApi } from "@/api/strategies";
import { DeploymentsApi } from "@/api/deployments";
import {
  type Strategy,
  type StrategyResponse,
  type StrategyVersionRecord,
} from "@/api/schemas/strategies";
import type { StrategyDraftLaunchPlans } from "@/api/schemas/strategyComposer";
import type { Deployment } from "@/api/schemas/deployments";
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
import { AwaitingApiBanner, isAwaiting } from "@/components/empty/AwaitingApi";
import { LaunchPlansCard } from "@/components/strategy_builder/LaunchPlansCard";
import { PageHeader } from "./PageHeader";
import { formatTimestamp, relativeTime } from "@/lib/format";

/**
 * StrategyDetail — first-class operator page for a single Strategy.
 *
 * Renders lineage (versions table), publish state, and the deployments
 * that subscribe to each version. "Add Version" and "Edit draft" link
 * into the dedicated full-page StrategyBuilder route, so the operator
 * gets the full screen for visual rule authoring instead of a cramped
 * drawer.
 */
export function StrategyDetail(): JSX.Element {
  const params = useParams();
  const strategyId = params.strategyId ?? "";
  const navigate = useNavigate();
  const qc = useQueryClient();

  const detail = useQuery({
    queryKey: ["strategies", "detail", strategyId],
    queryFn: () => StrategiesApi.get(strategyId),
    enabled: Boolean(strategyId),
  });
  const deployments = useQuery({
    queryKey: ["deployments", "list"],
    queryFn: () => DeploymentsApi.list(),
    refetchInterval: 30_000,
  });

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [launchVersion, setLaunchVersion] = useState<StrategyVersionRecord | null>(null);

  // The composer route navigates here with location.state.composerSavedToast
  // after a successful save. We render a one-shot Banner with a "Verify in
  // Backtest" deep-link, then clear the state so a refresh doesn't re-show.
  const location = useLocation();
  const composerToast = (location.state as { composerSavedToast?: ComposerSavedToast } | null)
    ?.composerSavedToast;
  const [savedToast, setSavedToast] = useState<ComposerSavedToast | null>(composerToast ?? null);
  useEffect(() => {
    if (composerToast) {
      window.history.replaceState({}, "");
    }
  }, [composerToast]);

  const deprecate = useMutation({
    mutationFn: () => StrategiesApi.deprecate(strategyId),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["strategies"] });
    },
  });
  const freeze = useMutation({
    mutationFn: (versionId: string) => StrategiesApi.freezeVersion(strategyId, versionId),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["strategies"] });
    },
  });
  const remove = useMutation({
    mutationFn: () => StrategiesApi.delete(strategyId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["strategies", "list"] });
      navigate("/strategies");
    },
  });

  const strategyName = detail.data?.strategy.name ?? "Strategy";

  return (
    <div className="space-y-4">
      <PageHeader
        title={strategyName}
        subtitle="Strategy detail · versions, lineage, deployments using each version, and launch into Chart Lab / Backtest / Walk-Forward."
        explainSlug="strategy-detail"
        actions={
          <div className="flex items-center gap-2">
            <Link to="/strategies">
              <Button
                variant="ghost"
                size="sm"
                leftIcon={<ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />}
              >
                Back to Strategies
              </Button>
            </Link>
            <Link to="/strategies/compose">
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
              >
                AI Composer
              </Button>
            </Link>
            <Link to={`/strategies/${strategyId}/builder/new`}>
              <Button
                size="sm"
                variant="primary"
                leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
                disabled={!detail.data}
              >
                Add Version
              </Button>
            </Link>
          </div>
        }
      />

      {savedToast ? (
        <Banner
          severity="success"
          title="Saved as draft"
          message={
            <span className="flex items-center gap-3">
              <span>{savedToast.name} saved. Verify it before deployment.</span>
              <Link to={savedToast.verifyInBacktestHref} className="underline">
                Verify in Backtest
              </Link>
              <button
                type="button"
                onClick={() => setSavedToast(null)}
                className="ml-auto text-[10.5px] text-fg-muted underline hover:text-fg"
              >
                Dismiss
              </button>
            </span>
          }
        />
      ) : null}
      {detail.isLoading ? <LoadingState title="Loading strategy" /> : null}
      {detail.isError ? (
        <ErrorState
          title="Could not load strategy"
          detail={(detail.error as Error)?.message}
          onRetry={() => detail.refetch()}
        />
      ) : null}
      {detail.data ? (
        <StrategyDetailBody
          response={detail.data}
          deployments={deployments.data?.deployments ?? []}
          deploymentsAwaiting={isAwaiting(deployments.error)}
          deploymentsError={
            deployments.isError && !isAwaiting(deployments.error)
              ? (deployments.error as Error)?.message
              : null
          }
          onLaunchVersion={(v) => setLaunchVersion(v)}
          onFreeze={(versionId) => freeze.mutate(versionId)}
          freezing={freeze.isPending}
          onDeprecate={() => deprecate.mutate()}
          deprecating={deprecate.isPending}
          onDelete={() => setDeleteOpen(true)}
        />
      ) : null}

      <DangerConfirm
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Delete strategy "${strategyName}"?`}
        message={
          <span>
            Type <strong>{strategyName}</strong> to confirm. Strategies with frozen versions cannot
            be deleted; deprecate them instead.
          </span>
        }
        expected={strategyName}
        actionLabel="Delete Strategy"
        tone="danger"
        busy={remove.isPending}
        onConfirm={async () => {
          await remove.mutateAsync();
          setDeleteOpen(false);
        }}
      />

      {launchVersion ? (
        <LaunchVersionDrawer
          open
          onOpenChange={(open) => {
            if (!open) setLaunchVersion(null);
          }}
          version={launchVersion}
          strategyId={strategyId}
        />
      ) : null}
    </div>
  );
}

interface ComposerSavedToast {
  name: string;
  versionId: string;
  verifyInBacktestHref: string;
}

interface BodyProps {
  response: StrategyResponse;
  deployments: Deployment[];
  deploymentsAwaiting: boolean;
  deploymentsError: string | null;
  onLaunchVersion: (v: StrategyVersionRecord) => void;
  onFreeze: (versionId: string) => void;
  freezing: boolean;
  onDeprecate: () => void;
  deprecating: boolean;
  onDelete: () => void;
}

function StrategyDetailBody(props: BodyProps): JSX.Element {
  const {
    response,
    deployments,
    deploymentsAwaiting,
    deploymentsError,
    onLaunchVersion,
    onFreeze,
    freezing,
    onDeprecate,
    deprecating,
    onDelete,
  } = props;
  const { strategy, versions } = response;

  const sortedVersions = useMemo(
    () => [...versions].sort((a, b) => a.version - b.version),
    [versions],
  );
  const frozen = sortedVersions.filter((v) => v.status === "frozen");
  const latestPublished = frozen.length ? frozen[frozen.length - 1] : null;
  const latestEditable =
    sortedVersions.find((v) => v.status === "draft") ??
    latestPublished ??
    sortedVersions[sortedVersions.length - 1] ??
    null;

  const deploymentsByVersion = useMemo(() => {
    const map = new Map<string, Deployment[]>();
    for (const d of deployments) {
      const arr = map.get(d.strategy_version_id) ?? [];
      arr.push(d);
      map.set(d.strategy_version_id, arr);
    }
    return map;
  }, [deployments]);

  return (
    <div className="space-y-3">
      <Card>
        <CardHeader>
          <CardTitle>Overview</CardTitle>
          <span className="flex items-center gap-2">
            <StatusBadge tone={strategyStatusTone(strategy)}>{strategy.status}</StatusBadge>
            <Button
              variant="ghost"
              size="sm"
              onClick={onDeprecate}
              loading={deprecating}
              disabled={strategy.status === "deprecated"}
            >
              Deprecate
            </Button>
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
            <div className="text-fg-muted">Description</div>
            <div className="mt-0.5 break-words">{strategy.description ?? "—"}</div>
          </div>
          <div>
            <div className="text-fg-muted">Tags / capabilities</div>
            <div className="mt-0.5">{strategy.tags.length ? strategy.tags.join(", ") : "—"}</div>
          </div>
          <div>
            <div className="text-fg-muted">Created</div>
            <div className="mt-0.5" title={strategy.created_at}>
              {formatTimestamp(strategy.created_at)}
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Launch plans for the latest editable / frozen version */}
      {latestEditable ? (
        <LaunchPlansCard
          launchPlans={makeLaunchPlans(latestEditable, strategy.strategy_id)}
          defaultSymbol="SPY"
        />
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Latest published</CardTitle>
          {latestPublished ? (
            <StatusBadge tone="ok">v{latestPublished.version}</StatusBadge>
          ) : (
            <StatusBadge tone="warn">none yet</StatusBadge>
          )}
        </CardHeader>
        <CardBody className="text-xs">
          {latestPublished ? (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <div>
                <div className="text-fg-muted">Version name</div>
                <div className="mt-0.5">
                  {latestPublished.payload.name || `v${latestPublished.version}`}
                </div>
              </div>
              <div>
                <div className="text-fg-muted">Published at</div>
                <div className="mt-0.5" title={latestPublished.frozen_at ?? undefined}>
                  {formatTimestamp(latestPublished.frozen_at)}
                </div>
              </div>
              <div>
                <div className="text-fg-muted">Published by</div>
                <div className="mt-0.5">
                  {latestPublished.frozen_by ?? (
                    <span
                      className="text-fg-subtle"
                      title="Awaiting backend X-Operator-Session-Id capture on /freeze."
                    >
                      system
                    </span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <EmptyState
              title="No frozen version yet"
              message="Add a version, then freeze it to publish. Deployments can only point at a frozen version."
              action={
                <Link to={`/strategies/${strategy.strategy_id}/builder/new`}>
                  <Button size="sm" variant="primary">
                    Add Version
                  </Button>
                </Link>
              }
            />
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Versions &amp; lineage</CardTitle>
          <span className="flex items-center gap-2">
            <StatusBadge>{sortedVersions.length}</StatusBadge>
            <StatusBadge tone="ok">{frozen.length} frozen</StatusBadge>
            <Link to={`/strategies/${strategy.strategy_id}/builder/new`}>
              <Button
                size="sm"
                variant="primary"
                leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              >
                Add Version
              </Button>
            </Link>
          </span>
        </CardHeader>
        <CardBody className="p-0">
          {deploymentsError ? (
            <div className="px-4 pt-3">
              <Banner severity="danger" title="Could not load deployments" message={deploymentsError} />
            </div>
          ) : null}
          {deploymentsAwaiting ? (
            <div className="px-4 pt-3">
              <AwaitingApiBanner
                title="Deployments listing awaiting backend"
                endpoint="GET /api/v1/deployments"
                message="Deployments-using-version column will populate the moment Operation Turtle Shell registers the route."
              />
            </div>
          ) : null}
          {sortedVersions.length === 0 ? (
            <div className="p-4">
              <EmptyState
                title="No versions"
                message="Add the first version below or use the AI Composer to generate one from a plain-English prompt."
                action={
                  <div className="flex gap-2">
                    <Link to={`/strategies/${strategy.strategy_id}/builder/new`}>
                      <Button size="sm" variant="primary">
                        Add Version
                      </Button>
                    </Link>
                    <Link to="/strategies/compose">
                      <Button
                        size="sm"
                        variant="secondary"
                        leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
                      >
                        AI Composer
                      </Button>
                    </Link>
                  </div>
                }
              />
            </div>
          ) : (
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Version</th>
                  <th>Status</th>
                  <th>Published</th>
                  <th>Published by</th>
                  <th>Rules (entry / exit)</th>
                  <th>Deployments using</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {sortedVersions.map((v) => {
                  const using = deploymentsByVersion.get(v.strategy_version_id) ?? [];
                  const isFrozen = v.status === "frozen";
                  return (
                    <tr key={v.strategy_version_id}>
                      <td className="font-medium">
                        <span title={v.strategy_version_id}>v{v.version}</span>
                        {v.payload.name ? (
                          <span className="ml-1 text-fg-muted">· {v.payload.name}</span>
                        ) : null}
                      </td>
                      <td>
                        <StatusBadge tone={isFrozen ? "ok" : "info"}>{v.status}</StatusBadge>
                      </td>
                      <td className="text-fg-muted" title={v.frozen_at ?? undefined}>
                        {v.frozen_at ? relativeTime(v.frozen_at) : "—"}
                      </td>
                      <td className="text-fg-muted">
                        {v.frozen_by ?? (isFrozen ? "system" : "—")}
                      </td>
                      <td className="text-fg-muted">
                        {v.payload.entry_rules.length} / {v.payload.exit_rules.length}
                      </td>
                      <td className="text-fg-muted">
                        {using.length === 0 ? (
                          <span className="text-fg-subtle">none</span>
                        ) : (
                          <ul className="m-0 space-y-0.5">
                            {using.map((d) => (
                              <li key={d.deployment_id}>
                                <Link
                                  to="/deployments"
                                  className="hover:underline"
                                  title={d.deployment_id}
                                >
                                  {d.name}
                                </Link>
                                <span className="ml-1 text-fg-subtle">· {d.lifecycle_status}</span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </td>
                      <td className="text-right">
                        <span className="inline-flex items-center gap-1">
                          <Button size="sm" variant="ghost" onClick={() => onLaunchVersion(v)}>
                            Launch
                          </Button>
                          {!isFrozen ? (
                            <Link
                              to={`/strategies/${strategy.strategy_id}/builder/${v.strategy_version_id}`}
                            >
                              <Button
                                size="sm"
                                variant="secondary"
                                leftIcon={<Pencil className="h-3.5 w-3.5" aria-hidden="true" />}
                              >
                                Edit
                              </Button>
                            </Link>
                          ) : null}
                          {isFrozen ? (
                            <StatusBadge tone="ok">Frozen</StatusBadge>
                          ) : (
                            <Button
                              size="sm"
                              variant="ok"
                              leftIcon={<Lock className="h-3.5 w-3.5" aria-hidden="true" />}
                              onClick={() => onFreeze(v.strategy_version_id)}
                              loading={freezing}
                            >
                              Publish
                            </Button>
                          )}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </CardBody>
        {sortedVersions.find((v) => v.status === "draft") ? (
          <div className="border-t border-border/70 px-4 py-2 text-[11px] text-fg-muted">
            The draft version edits in place; freezing it promotes to published. Past frozen versions are immutable.
          </div>
        ) : null}
      </Card>
    </div>
  );
}

function strategyStatusTone(strategy: Strategy): "ok" | "muted" | "info" {
  if (strategy.status === "deprecated") return "muted";
  if (strategy.status === "active") return "ok";
  return "info";
}

function LaunchVersionDrawer({
  open,
  onOpenChange,
  version,
  strategyId,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  version: StrategyVersionRecord;
  strategyId: string;
}): JSX.Element {
  const launchPlans = useMemo(() => makeLaunchPlans(version, strategyId), [version, strategyId]);
  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-w-2xl">
        <DrawerHeader>
          <DrawerTitle>
            Test v{version.version}
            {version.payload.name ? ` · ${version.payload.name}` : ""}
          </DrawerTitle>
          <DrawerDescription>
            Queue a research job for this Strategy version. Jobs run asynchronously — close this drawer
            at any time and watch the JobMonitor pulse-dot for completion.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          <LaunchPlansCard launchPlans={launchPlans} defaultSymbol="SPY" />
          {version.payload.feature_refs.length > 0 ? (
            <TextField
              label="Feature refs (informational)"
              value={version.payload.feature_refs.join(", ")}
              disabled
            />
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

/**
 * Build a StrategyDraftLaunchPlans for any saved StrategyVersion, mirroring
 * the shape the backend composer returns. This lets the LaunchPlansCard
 * handle BOTH composer-fresh drafts AND library Strategies uniformly.
 */
function makeLaunchPlans(
  version: StrategyVersionRecord,
  strategyId: string,
): StrategyDraftLaunchPlans {
  const symbol = version.payload.feature_refs.find((r) => /^[A-Z]+$/.test(r)) ?? "SPY";
  return {
    chart_lab: {
      surface: "chart_lab",
      method: "GET",
      route: "/api/v1/chart-lab/stream",
      request: { symbol, query: { symbol } },
      ready: true,
      missing_fields: [],
    },
    backtest: {
      surface: "backtest",
      method: "POST",
      route: "/api/v1/research/jobs/backtest",
      request: {
        request: {
          strategy_id: strategyId,
          strategy_version_id: version.strategy_version_id,
          risk_plan_version_id: null,
          symbols: [symbol],
          timeframe: "5m",
          start: null,
          end: null,
          initial_capital: 100000,
        },
      },
      ready: false,
      missing_fields: ["risk_plan_version_id", "start", "end"],
    },
    walk_forward: {
      surface: "walk_forward",
      method: "POST",
      route: "/api/v1/research/jobs/walk-forward",
      request: {
        request: {
          strategy_id: strategyId,
          strategy_version_id: version.strategy_version_id,
          symbols: [symbol],
          timeframe: "5m",
          start: null,
          end: null,
          initial_capital: 100000,
        },
      },
      ready: false,
      missing_fields: ["start", "end"],
    },
  };
}

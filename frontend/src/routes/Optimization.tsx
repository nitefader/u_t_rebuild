import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import { OptimizationApi } from "@/api/researchRuns";
import { StrategiesApi } from "@/api/strategies";
import type {
  OptimizationCandidate,
  OptimizationHeatmap,
  OptimizationRun,
} from "@/api/schemas/researchRuns";
import {
  OptimizationCandidateSchema,
  OptimizationHeatmapSchema,
} from "@/api/schemas/researchRuns";
import type { Strategy } from "@/api/schemas/strategies";
import { Button } from "@/components/ui/Button";
import {
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  KpiCard,
} from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { EmptyState } from "@/components/empty/EmptyState";
import { AwaitingApiOrError } from "@/components/empty/AwaitingApi";
import { CandidateTable } from "@/components/optimization/CandidateTable";
import { HypothesisBanner } from "@/components/optimization/HypothesisBanner";
import { SaveAsRiskPlanButton } from "@/components/risk_plans/SaveAsRiskPlanButton";
import { recommendationToFormPrefill } from "@/components/risk_plans/recommendationPrefill";
import { LandscapeHeatmap } from "@/components/optimization/LandscapeHeatmap";
import { RunOptimizationDrawer } from "@/components/optimization/RunOptimizationDrawer";
import { JobMonitor } from "@/components/jobs/JobMonitor";
import { RoadmapCard } from "@/components/roadmap/RoadmapCard";
import { OPTIMIZATION_ROADMAP } from "@/components/roadmap/researchRoadmap";
import { PageHeader } from "./PageHeader";
import { formatQuantity, relativeTime } from "@/lib/format";

/**
 * Optimization — operator results surface.
 *
 * Doctrine: hypothesis generation, NOT ship-readiness. Every detail page
 * leads with the HypothesisBanner that warns operators to validate with
 * Walk-Forward before deploying. The recommended workflow is
 * Backtest → Optimization → Walk-Forward → Sim Lab → Deploy.
 */
export function Optimization(): JSX.Element {
  const list = useQuery({
    queryKey: ["optimization", "runs"],
    queryFn: () => OptimizationApi.list(),
    refetchInterval: 30_000,
  });
  const strategies = useQuery({
    queryKey: ["strategies", "list"],
    queryFn: () => StrategiesApi.list(),
    refetchInterval: 60_000,
  });

  const runs = list.data?.runs ?? [];
  const directory = useMemo(
    () => buildStrategyMap(strategies.data?.strategies ?? []),
    [strategies.data?.strategies],
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  if (selectedId) {
    const run = runs.find((r) => r.run_id === selectedId) ?? null;
    return (
      <OptimizationDetail
        runId={selectedId}
        run={run}
        directory={directory}
        onBack={() => setSelectedId(null)}
      />
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Optimization"
        subtitle="Parameter sweeps over the unified spine. Hypothesis search — every winner needs Walk-Forward validation before deployment."
        explainSlug="optimization"
        actions={
          <div className="flex items-center gap-2">
            <JobMonitor kind="optimization" />
            <Button
              size="sm"
              leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setDrawerOpen(true)}
            >
              Run new optimization
            </Button>
          </div>
        }
      />
      <RunOptimizationDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        onCreated={() => {
          // Async run dispatched; the JobMonitor will surface progress and
          // the list page auto-refreshes once the job completes.
        }}
      />

      {list.isLoading ? <LoadingState title="Loading optimization runs" /> : null}
      {list.isError ? (
        <AwaitingApiOrError
          title="Optimization runs"
          endpoint="GET /api/v1/optimization/runs"
          awaitingMessage="The optimization runs endpoint is not registered yet."
          error={list.error}
          onRetry={() => list.refetch()}
        />
      ) : null}
      {list.data && runs.length === 0 ? (
        <EmptyState
          title="No optimization runs yet"
          message="Trigger one with 'Run new optimization' — pick a parameter grid and watch the landscape develop."
        />
      ) : null}
      {runs.length > 0 ? (
        <RunsTable runs={runs} directory={directory} onOpen={setSelectedId} />
      ) : null}

      <RoadmapCard surface="Optimization" items={OPTIMIZATION_ROADMAP} />
    </div>
  );
}

interface StrategyDirectory {
  name: (id: string | null | undefined) => string;
}

function buildStrategyMap(strategies: Strategy[]): StrategyDirectory {
  const byId = new Map<string, Strategy>();
  for (const s of strategies) byId.set(s.strategy_id, s);
  return {
    name: (id) => {
      if (!id) return "—";
      return byId.get(id)?.name ?? `${id.slice(0, 8)}…`;
    },
  };
}

function RunsTable({
  runs,
  directory,
  onOpen,
}: {
  runs: OptimizationRun[];
  directory: StrategyDirectory;
  onOpen: (runId: string) => void;
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent optimization runs</CardTitle>
        <StatusBadge>{runs.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        <table className="ut-table">
          <thead>
            <tr>
              <th>Created</th>
              <th>Strategy</th>
              <th>Objective</th>
              <th>Candidates</th>
              <th>Best score</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => {
              const m = (r.best_metrics ?? {}) as Record<string, unknown>;
              const winnerScore =
                typeof m.winner_score === "number" && Number.isFinite(m.winner_score)
                  ? (m.winner_score as number).toFixed(3)
                  : "—";
              return (
                <tr key={r.run_id}>
                  <td className="text-fg-muted" title={r.created_at}>
                    {relativeTime(r.created_at)}
                  </td>
                  <td>{directory.name(r.strategy_id)}</td>
                  <td className="text-fg-muted">{r.objective}</td>
                  <td className="tabular text-fg-muted">{formatQuantity(r.candidate_count)}</td>
                  <td className="tabular">{winnerScore}</td>
                  <td className="text-right">
                    <Button size="sm" variant="secondary" onClick={() => onOpen(r.run_id)}>
                      Open
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

function OptimizationDetail({
  runId,
  run,
  directory,
  onBack,
}: {
  runId: string;
  run: OptimizationRun | null;
  directory: StrategyDirectory;
  onBack: () => void;
}): JSX.Element {
  const detail = useQuery({
    queryKey: ["optimization", "detail", runId],
    queryFn: () => OptimizationApi.get(runId),
    initialData: run ?? undefined,
  });
  const live = detail.data;
  const strategyName = directory.name(live?.strategy_id);

  const metrics = (live?.best_metrics ?? {}) as Record<string, unknown>;
  const candidates = readCandidates(metrics);
  const heatmap = readHeatmap(metrics);
  const handoff = readHandoff(metrics);
  const winnerScore =
    typeof metrics.winner_score === "number" && Number.isFinite(metrics.winner_score)
      ? (metrics.winner_score as number).toFixed(3)
      : "—";
  const winnerSharpe =
    typeof (live?.best_metrics as Record<string, unknown>)?.sharpe === "number"
      ? ((live?.best_metrics as Record<string, unknown>).sharpe as number).toFixed(3)
      : "—";
  const winnerMaxDd =
    typeof (live?.best_metrics as Record<string, unknown>)?.max_drawdown === "number"
      ? `${(((live?.best_metrics as Record<string, unknown>).max_drawdown as number) * 100).toFixed(2)}%`
      : "—";

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${strategyName} · optimization`}
        subtitle={live ? `${live.candidate_count} candidates · objective ${live.objective}` : "—"}
        explainSlug="optimization"
        actions={
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={onBack}
          >
            Back to runs
          </Button>
        }
      />

      <HypothesisBanner walkForwardHandoff={handoff} />

      {!live ? <LoadingState title="Loading run" /> : null}

      {live ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <KpiCard label="Winner score" value={winnerScore} />
          <KpiCard label="Winner Sharpe" value={winnerSharpe} />
          <KpiCard label="Winner max-DD" value={winnerMaxDd} tone="danger" />
          <KpiCard label="Candidates evaluated" value={String(live.candidate_count)} />
        </div>
      ) : null}

      {live ? (
        <Card>
          <CardHeader>
            <CardTitle>Winner parameters</CardTitle>
            <SaveAsRiskPlanButton
              source="optimization_generated"
              prefill={recommendationToFormPrefill(
                { parameters: live.best_parameters as Record<string, unknown> | null },
                {
                  namePrefix: "Optimization",
                  strategyName,
                  tier: "balanced",
                },
              )}
              aiSummary={`Optimization winner over ${live.candidate_count} candidates · objective ${live.objective}. Validate with Walk-Forward before live use.`}
              aiWarnings={[
                "Optimization output is hypothesis only — Walk-Forward validation required before deployment.",
              ]}
              label="Save winner as Risk Plan"
            />
          </CardHeader>
          <CardBody>
            <div className="font-mono text-sm">{formatParameters(live.best_parameters)}</div>
          </CardBody>
        </Card>
      ) : null}

      {heatmap ? <LandscapeHeatmap heatmap={heatmap} /> : null}

      {candidates.length > 0 ? (
        <CandidateTable candidates={candidates} title="Candidate landscape (sorted by score)" />
      ) : null}

      <RoadmapCard surface="Optimization" items={OPTIMIZATION_ROADMAP} />
    </div>
  );
}

function readCandidates(metrics: Record<string, unknown>): OptimizationCandidate[] {
  const raw = metrics?.candidates;
  if (!Array.isArray(raw)) return [];
  const out: OptimizationCandidate[] = [];
  for (const item of raw) {
    const parsed = OptimizationCandidateSchema.safeParse(item);
    if (parsed.success) out.push(parsed.data);
  }
  return out;
}

function readHeatmap(metrics: Record<string, unknown>): OptimizationHeatmap | null {
  const raw = metrics?.heatmap;
  if (!raw) return null;
  const parsed = OptimizationHeatmapSchema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}

function readHandoff(metrics: Record<string, unknown>): Record<string, unknown> | null {
  const raw = metrics?.follow_up_walk_forward_request;
  if (!raw || typeof raw !== "object") return null;
  return raw as Record<string, unknown>;
}

function formatParameters(params: Record<string, unknown>): string {
  const entries = Object.entries(params);
  if (!entries.length) return "—";
  return entries.map(([k, v]) => `${k}=${v}`).join("  ·  ");
}

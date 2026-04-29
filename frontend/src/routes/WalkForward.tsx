import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import { WalkForwardApi } from "@/api/researchRuns";
import { StrategiesApi } from "@/api/strategies";
import type {
  WalkForwardCandidateRow,
  WalkForwardRiskPlanRecommendation,
  WalkForwardRun,
} from "@/api/schemas/researchRuns";
import {
  WalkForwardCandidateRowSchema,
  WalkForwardRiskPlanRecommendationSchema,
} from "@/api/schemas/researchRuns";
import type { Strategy } from "@/api/schemas/strategies";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle, KpiCard } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { EmptyState } from "@/components/empty/EmptyState";
import { AwaitingApiOrError, AwaitingApiBanner } from "@/components/empty/AwaitingApi";
import { RunWalkForwardDrawer } from "@/components/walkforward/RunWalkForwardDrawer";
import { RecommendedRiskPlanCard } from "@/components/walkforward/RecommendedRiskPlanCard";
import { RiskPlanCandidateTable } from "@/components/walkforward/RiskPlanCandidateTable";
import { JobMonitor } from "@/components/jobs/JobMonitor";
import { RoadmapCard } from "@/components/roadmap/RoadmapCard";
import { WALK_FORWARD_ROADMAP } from "@/components/roadmap/researchRoadmap";
import { PageHeader } from "./PageHeader";
import { formatPercent, formatQuantity, relativeTime } from "@/lib/format";

/**
 * Walk-Forward — operator results summary (gate E6).
 *
 * Renders durable walk-forward runs from `/api/v1/walk-forward/runs`
 * and a per-run summary panel: median OOS Sharpe, OOS-vs-IS decay,
 * regime fit score, recommend / reject. The summary reads additive
 * keys off the `metrics` JsonDict so it surfaces whatever Codex ships
 * without a schema change. Per-fold IS/OOS, decay plot, parameter
 * stability heatmap, and OOS regime breakdown live behind explicit
 * `AwaitingApiOrError` panels pinned to gate rows E1–E5 until those
 * backend artifacts land.
 */
export function WalkForward(): JSX.Element {
  const list = useQuery({
    queryKey: ["walk-forward", "runs"],
    queryFn: () => WalkForwardApi.list(),
    refetchInterval: 30_000,
  });
  const strategies = useQuery({
    queryKey: ["strategies", "list"],
    queryFn: () => StrategiesApi.list(),
    refetchInterval: 60_000,
  });

  const directory = useMemo(
    () => buildStrategyMap(strategies.data?.strategies ?? []),
    [strategies.data?.strategies],
  );

  const runs = list.data?.runs ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);

  if (selectedId) {
    const run = runs.find((r) => r.run_id === selectedId) ?? null;
    return (
      <WalkForwardDetail
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
        title="Walk-Forward"
        subtitle="Rolling-window validation on the unified spine. Each fold runs IS+OOS replays via the same engine Backtest uses; the recommendation aggregates fold OOS evidence and emits a recommended risk plan."
        explainSlug="walk-forward"
        actions={
          <div className="flex items-center gap-2">
            <JobMonitor kind="walk_forward" />
            <Button
              size="sm"
              leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setDrawerOpen(true)}
            >
              Run new walk-forward
            </Button>
          </div>
        }
      />
      <RunWalkForwardDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        onCreated={() => {
          // Async run dispatched; the JobMonitor will surface progress and
          // the list page auto-refreshes once the job completes.
        }}
      />

      {list.isLoading ? <LoadingState title="Loading walk-forward runs" /> : null}
      {list.isError ? (
        <AwaitingApiOrError
          title="Walk-forward runs"
          endpoint="GET /api/v1/walk-forward/runs"
          awaitingMessage="The walk-forward runs endpoint is not registered yet. Read-only catalog flips on automatically when Codex's evidence path lands."
          error={list.error}
          onRetry={() => list.refetch()}
        />
      ) : null}
      {list.data && runs.length === 0 ? (
        <EmptyState
          title="No walk-forward runs yet"
          message="Runs persist as research evidence. Trigger one from a frozen Strategy version; results show median OOS Sharpe, OOS-vs-IS decay, regime fit score, and recommend/reject."
        />
      ) : null}
      {runs.length > 0 ? (
        <RunsTable runs={runs} directory={directory} onOpen={setSelectedId} />
      ) : null}

      <RoadmapCard surface="Walk-Forward" items={WALK_FORWARD_ROADMAP} />
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
  runs: WalkForwardRun[];
  directory: StrategyDirectory;
  onOpen: (runId: string) => void;
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent walk-forward runs</CardTitle>
        <StatusBadge>{runs.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        <table className="ut-table">
          <thead>
            <tr>
              <th>Created</th>
              <th>Strategy</th>
              <th>Folds (passed / total)</th>
              <th>Recommendation</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => {
              const summary = readSummary(r);
              return (
                <tr key={r.run_id}>
                  <td className="text-fg-muted" title={r.created_at}>
                    {relativeTime(r.created_at)}
                  </td>
                  <td>{directory.name(r.strategy_id)}</td>
                  <td className="tabular text-fg-muted">
                    {formatQuantity(r.passed_window_count)} / {formatQuantity(r.window_count)}
                  </td>
                  <td>
                    <RecommendationBadge value={summary.recommendation} />
                  </td>
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

function WalkForwardDetail({
  runId,
  run,
  directory,
  onBack,
}: {
  runId: string;
  run: WalkForwardRun | null;
  directory: StrategyDirectory;
  onBack: () => void;
}): JSX.Element {
  const detail = useQuery({
    queryKey: ["walk-forward", "detail", runId],
    queryFn: () => WalkForwardApi.get(runId),
    initialData: run ?? undefined,
  });

  const live = detail.data;
  const summary = live ? readSummary(live) : null;
  const strategyName = directory.name(live?.strategy_id);

  return (
    <div className="space-y-4">
      <PageHeader
        title={`${strategyName} · walk-forward`}
        subtitle={live ? `Folds passed ${live.passed_window_count} / ${live.window_count}` : "—"}
        explainSlug="walk-forward"
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

      {!live ? <LoadingState title="Loading run" /> : null}

      {summary ? <SummaryGrid summary={summary} run={live!} /> : null}

      {live ? (
        <RecommendedRiskPlanCard
          recommended={readRecommended(live)}
          recommendation={readRecommendation(live)}
          strategyName={strategyName}
        />
      ) : null}

      {live ? (
        <RiskPlanCandidateTable
          candidates={readCandidates(live)}
          foldCount={readFoldCount(live)}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Per-fold IS / OOS metrics (E1 + E2)</CardTitle>
            <StatusBadge tone="muted">awaiting</StatusBadge>
          </CardHeader>
          <CardBody>
            <AwaitingApiBanner
              title="Per-fold metrics awaiting backend"
              endpoint={`GET /api/v1/walk-forward/runs/${runId}/folds`}
              message="Per-fold IS metrics + OOS metrics + decay (Sharpe IS − Sharpe OOS, hit rate decay, expectancy decay) populate here when Codex registers the route."
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Parameter stability heatmap (E3)</CardTitle>
            <StatusBadge tone="muted">awaiting</StatusBadge>
          </CardHeader>
          <CardBody>
            <AwaitingApiBanner
              title="Stability heatmap awaiting backend"
              endpoint={`GET /api/v1/walk-forward/runs/${runId}/parameter-stability`}
              message="Heatmap of parameter values across folds populates here when Codex registers the route."
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>OOS regime breakdown per fold (E4)</CardTitle>
            <StatusBadge tone="muted">awaiting</StatusBadge>
          </CardHeader>
          <CardBody>
            <AwaitingApiBanner
              title="OOS regime breakdown awaiting backend"
              endpoint={`GET /api/v1/walk-forward/runs/${runId}/oos-regime-breakdown`}
              message="Per-fold regime exposure (which regimes did this strategy actually see OOS?) populates here when Codex registers the route."
            />
          </CardBody>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Equity curve · IS / OOS shading (E5)</CardTitle>
            <StatusBadge tone="muted">awaiting</StatusBadge>
          </CardHeader>
          <CardBody>
            <AwaitingApiBanner
              title="Equity curve awaiting backend"
              endpoint={`GET /api/v1/walk-forward/runs/${runId}/equity-curve`}
              message="Equity curve with IS/OOS shading lands when the per-fold endpoint is wired."
            />
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function SummaryGrid({ summary, run }: { summary: SummaryView; run: WalkForwardRun }): JSX.Element {
  const passRate = run.window_count > 0 ? run.passed_window_count / run.window_count : null;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <KpiCard
        label="Median OOS Sharpe"
        value={summary.medianOosSharpe != null ? summary.medianOosSharpe.toFixed(2) : "—"}
        tone={summary.medianOosSharpe == null ? "neutral" : summary.medianOosSharpe >= 1 ? "ok" : "warn"}
        sublabel={summary.medianOosSharpe == null ? "awaiting backend metric" : "across OOS folds"}
      />
      <KpiCard
        label="OOS-vs-IS decay"
        value={
          summary.oosIsDecay != null
            ? `${summary.oosIsDecay > 0 ? "+" : ""}${summary.oosIsDecay.toFixed(2)}`
            : "—"
        }
        tone={summary.oosIsDecay == null ? "neutral" : summary.oosIsDecay <= 0 ? "danger" : "ok"}
        sublabel={summary.oosIsDecay == null ? "awaiting backend metric" : "Sharpe(IS) − Sharpe(OOS)"}
      />
      <KpiCard
        label="Regime fit score"
        value={summary.regimeFitScore != null ? summary.regimeFitScore.toFixed(2) : "—"}
        tone={
          summary.regimeFitScore == null
            ? "neutral"
            : summary.regimeFitScore >= 0.6
              ? "ok"
              : summary.regimeFitScore >= 0.3
                ? "warn"
                : "danger"
        }
        sublabel={
          summary.regimeFitScore == null
            ? "awaiting F5 backend metric"
            : "weighted Sharpe by regime exposure"
        }
      />
      <KpiCard
        label="Folds passed"
        value={`${run.passed_window_count} / ${run.window_count}`}
        tone={
          passRate == null
            ? "neutral"
            : passRate >= 0.7
              ? "ok"
              : passRate >= 0.4
                ? "warn"
                : "danger"
        }
        sublabel={passRate == null ? "—" : formatPercent(passRate * 100)}
      />
    </div>
  );
}

function RecommendationBadge({ value }: { value: string | null }): JSX.Element {
  if (!value) return <StatusBadge tone="muted">awaiting</StatusBadge>;
  const v = value.toLowerCase();
  if (v.startsWith("recom") || v === "approve" || v === "promote" || v === "pass") {
    return <StatusBadge tone="ok">{value}</StatusBadge>;
  }
  if (v.startsWith("reject") || v === "fail") {
    return <StatusBadge tone="danger">{value}</StatusBadge>;
  }
  return <StatusBadge tone="warn">{value}</StatusBadge>;
}

interface SummaryView {
  medianOosSharpe: number | null;
  oosIsDecay: number | null;
  regimeFitScore: number | null;
  recommendation: string | null;
}

function readSummary(run: WalkForwardRun): SummaryView {
  const m = run.metrics ?? {};
  const decayBlock = (m.is_oos_decay ?? {}) as Record<string, unknown>;
  return {
    medianOosSharpe: numericOr(m.median_oos_sharpe ?? m.oos_sharpe_median ?? m.median_oos_sharpe_ratio),
    oosIsDecay: numericOr(
      decayBlock.sharpe ?? m.oos_vs_is_decay ?? m.sharpe_decay ?? m.is_minus_oos_sharpe,
    ),
    regimeFitScore: numericOr(m.regime_fit_score ?? m.regime_fit),
    recommendation: stringOr(m.recommendation ?? m.recommend ?? m.verdict),
  };
}

function readRecommendation(run: WalkForwardRun): string | null {
  return stringOr((run.metrics as Record<string, unknown>)?.recommendation);
}

function readRecommended(run: WalkForwardRun): WalkForwardRiskPlanRecommendation | null {
  const raw = (run.metrics as Record<string, unknown>)?.recommended_risk_plan;
  if (!raw) return null;
  const parsed = WalkForwardRiskPlanRecommendationSchema.safeParse(raw);
  return parsed.success ? parsed.data : null;
}

function readCandidates(run: WalkForwardRun): WalkForwardCandidateRow[] {
  const raw = (run.metrics as Record<string, unknown>)?.candidates;
  if (!Array.isArray(raw)) return [];
  const rows: WalkForwardCandidateRow[] = [];
  for (const item of raw) {
    const parsed = WalkForwardCandidateRowSchema.safeParse(item);
    if (parsed.success) rows.push(parsed.data);
  }
  return rows;
}

function readFoldCount(run: WalkForwardRun): number {
  const m = run.metrics as Record<string, unknown>;
  const value = m?.fold_count;
  return typeof value === "number" && Number.isFinite(value) ? value : run.window_count ?? 0;
}

function numericOr(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function stringOr(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}

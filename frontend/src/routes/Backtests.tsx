import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Plus } from "lucide-react";
import { BacktestsApi } from "@/api/researchRuns";
import { StrategiesApi } from "@/api/strategies";
import type {
  BacktestMetricsResponse,
  BacktestResultsResponse,
  BacktestRun,
  DrawdownPoint,
  EquityPoint,
  MonteCarloResult,
  PerSymbolBreakdown,
  TradeLedgerEntry,
} from "@/api/schemas/researchRuns";
import { MonteCarloResultSchema } from "@/api/schemas/researchRuns";
import { RunBacktestDrawer } from "@/components/backtests/RunBacktestDrawer";
import { MonteCarloCard } from "@/components/backtests/MonteCarloCard";
import { RiskDecisionCardDrawer } from "@/components/backtests/RiskDecisionCardDrawer";
import { JobMonitor } from "@/components/jobs/JobMonitor";
import { RoadmapCard } from "@/components/roadmap/RoadmapCard";
import { BACKTESTS_ROADMAP } from "@/components/roadmap/researchRoadmap";
import type { Strategy, StrategyVersionRecord } from "@/api/schemas/strategies";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle, KpiCard } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { AwaitingApiOrError, isAwaiting } from "@/components/empty/AwaitingApi";
import { Sparkline } from "@/components/charts/Sparkline";
import { PageHeader } from "./PageHeader";
import {
  formatCurrency,
  formatPercent,
  formatQuantity,
  formatTimestamp,
  relativeTime,
} from "@/lib/format";

/**
 * Backtests — operator-grade results surface (gate B7 + B8).
 *
 * Lists durable runs from /api/v1/research/backtests and drills into a
 * single run's results + metrics. Renders B3 (equity curve, drawdown,
 * trade ledger, per-symbol breakdown) + B4 (CAGR / Sharpe / Sortino /
 * Calmar / max DD / hit rate / profit factor / expectancy / exposure /
 * turnover / time-in-market) + B6 (per-regime metric table). Every
 * primary label is human-readable: Strategy display name, version
 * label, symbol ticker — never a UUID.
 *
 * Schemas .passthrough() so additive backend fields cannot reject the
 * typed client.
 */
export function Backtests(): JSX.Element {
  const list = useQuery({
    queryKey: ["backtests", "list"],
    queryFn: () => BacktestsApi.list(),
    refetchInterval: 15_000,
  });

  // Strategy directory for human-readable labels — sliced fanout via
  // the existing Strategies list (already passthrough-safe).
  const strategies = useQuery({
    queryKey: ["strategies", "list"],
    queryFn: () => StrategiesApi.list(),
    refetchInterval: 60_000,
  });

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState<boolean>(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const initialRiskPlanVersionId = searchParams.get("risk_plan_version_id");

  useEffect(() => {
    if (initialRiskPlanVersionId) {
      setDrawerOpen(true);
    }
  }, [initialRiskPlanVersionId]);

  const directory = useMemo(
    () => buildStrategyDirectory(strategies.data?.strategies ?? []),
    [strategies.data?.strategies],
  );

  if (selectedRunId) {
    const run = list.data?.runs.find((r) => r.run_id === selectedRunId) ?? null;
    return (
      <BacktestDetail
        runId={selectedRunId}
        run={run}
        directory={directory}
        onBack={() => setSelectedRunId(null)}
      />
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Backtests"
        subtitle="Deterministic replay against historical data. Backtests share the runtime's Feature Engine, Signal Engine, SignalPlanBuilder, RiskResolver, RiskDecisionCard. Research evidence only — never live promotion."
        explainSlug="backtests"
        actions={
          <div className="flex items-center gap-2">
            <JobMonitor kind="backtest" />
            <Button
              size="sm"
              leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setDrawerOpen(true)}
            >
              Run new backtest
            </Button>
          </div>
        }
      />
      <RunBacktestDrawer
        open={drawerOpen}
        onOpenChange={(next) => {
          setDrawerOpen(next);
          if (!next && initialRiskPlanVersionId) {
            const sp = new URLSearchParams(searchParams);
            sp.delete("risk_plan_version_id");
            setSearchParams(sp, { replace: true });
          }
        }}
        defaultRiskPlanVersionId={initialRiskPlanVersionId}
        onCreated={() => {
          // Async run dispatched; the JobMonitor will surface progress and
          // the list page auto-refreshes once the job completes.
        }}
      />

      {list.isLoading ? <LoadingState title="Loading backtest runs" /> : null}
      {list.isError ? (
        <AwaitingApiOrError
          title="Backtest runs"
          endpoint="GET /api/v1/research/backtests"
          awaitingMessage="The research backtests namespace is not yet registered. Operation Turtle Shell ships this with the create-run slice."
          error={list.error}
          onRetry={() => list.refetch()}
        />
      ) : null}
      {list.data && list.data.runs.length === 0 ? (
        <EmptyState
          title="No backtest runs yet"
          message="Runs persist as research evidence. Trigger one via the create-run drawer (lands once Codex's BacktestExecutionService is wired); read-only V1 already round-trips a recorded run."
        />
      ) : null}
      {list.data && list.data.runs.length > 0 ? (
        <RunsTable
          runs={list.data.runs}
          directory={directory}
          onOpen={(runId) => setSelectedRunId(runId)}
        />
      ) : null}

      <RoadmapCard surface="Backtests" items={BACKTESTS_ROADMAP} />
    </div>
  );
}

interface StrategyDirectory {
  strategyName: (id: string | null | undefined) => string;
  versionLabel: (strategyId: string | null | undefined, versionId: string | null | undefined) => string;
}

interface DirectoryEntry {
  strategy: Strategy;
  versionsById: Map<string, StrategyVersionRecord>;
}

function buildStrategyDirectory(strategies: Strategy[]): StrategyDirectory {
  const byId = new Map<string, DirectoryEntry>();
  for (const s of strategies) {
    byId.set(s.strategy_id, { strategy: s, versionsById: new Map() });
  }
  return {
    strategyName: (id) => {
      if (!id) return "—";
      const entry = byId.get(id);
      return entry ? entry.strategy.name : `${id.slice(0, 8)}…`;
    },
    versionLabel: (strategyId, versionId) => {
      if (!versionId) return "—";
      const entry = strategyId ? byId.get(strategyId) : undefined;
      const record = entry?.versionsById.get(versionId);
      if (record) {
        return `v${record.version}${record.payload.name ? ` · ${record.payload.name}` : ""}`;
      }
      return versionId.slice(0, 8);
    },
  };
}

function RunsTable({
  runs,
  directory,
  onOpen,
}: {
  runs: BacktestRun[];
  directory: StrategyDirectory;
  onOpen: (runId: string) => void;
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent runs</CardTitle>
        <StatusBadge>{runs.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        <table className="ut-table">
          <thead>
            <tr>
              <th>Started</th>
              <th>Strategy</th>
              <th>Version</th>
              <th>Universe</th>
              <th>Window</th>
              <th>Status</th>
              <th>Bars</th>
              <th>Trades</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.run_id}>
                <td className="text-fg-muted" title={r.created_at}>
                  {relativeTime(r.created_at)}
                </td>
                <td>{directory.strategyName(r.strategy_id)}</td>
                <td className="text-fg-muted">
                  {directory.versionLabel(r.strategy_id, r.strategy_version_id)}
                </td>
                <td className="text-xs text-fg-muted">
                  {r.universe.length === 0 ? "—" : r.universe.slice(0, 4).join(", ")}
                  {r.universe.length > 4 ? ` +${r.universe.length - 4}` : ""}
                </td>
                <td className="text-xs text-fg-muted">
                  {formatDateOnly(r.start)} → {formatDateOnly(r.end)}
                </td>
                <td>
                  <StatusBadge tone={statusTone(r.status)}>{r.status}</StatusBadge>
                </td>
                <td className="tabular text-fg-muted">{formatQuantity(r.bar_count)}</td>
                <td className="tabular text-fg-muted">{formatQuantity(r.simulated_trade_count)}</td>
                <td className="text-right">
                  <Button size="sm" variant="secondary" onClick={() => onOpen(r.run_id)}>
                    Open
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

function statusTone(status: string): "ok" | "warn" | "danger" | "info" | "muted" {
  switch (status) {
    case "completed":
    case "succeeded":
      return "ok";
    case "running":
    case "queued":
    case "recorded":
      return "info";
    case "canceled":
      return "muted";
    case "failed":
      return "danger";
    default:
      return "warn";
  }
}

function formatDateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

function BacktestDetail({
  runId,
  run,
  directory,
  onBack,
}: {
  runId: string;
  run: BacktestRun | null;
  directory: StrategyDirectory;
  onBack: () => void;
}): JSX.Element {
  const detail = useQuery({
    queryKey: ["backtests", "detail", runId],
    queryFn: () => BacktestsApi.get(runId),
    initialData: run ?? undefined,
    refetchInterval: (q) => {
      const data = q.state.data as BacktestRun | undefined;
      const status = data?.status ?? "recorded";
      return status === "running" || status === "queued" ? 3_000 : false;
    },
  });
  const results = useQuery({
    queryKey: ["backtests", "results", runId],
    queryFn: () => BacktestsApi.results(runId),
    retry: false,
  });
  const metrics = useQuery({
    queryKey: ["backtests", "metrics", runId],
    queryFn: () => BacktestsApi.metrics(runId),
    retry: false,
  });

  const live = detail.data;
  const strategyName = directory.strategyName(live?.strategy_id);
  const versionLabel = directory.versionLabel(live?.strategy_id, live?.strategy_version_id);
  const runTitle = strategyName === "—" ? `Backtest run` : `${strategyName} · ${versionLabel}`;

  const monteCarlo = useMemo<MonteCarloResult | null>(() => {
    const raw = (live?.metrics as Record<string, unknown> | undefined)?.monte_carlo;
    if (!raw) return null;
    const parsed = MonteCarloResultSchema.safeParse(raw);
    return parsed.success ? parsed.data : null;
  }, [live]);

  const [drillCardId, setDrillCardId] = useState<string | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader
        title={runTitle}
        subtitle={`Backtest run · ${live?.universe.join(", ") || "—"} · ${formatDateOnly(live?.start)} → ${formatDateOnly(live?.end)}`}
        explainSlug="backtests"
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

      {detail.isError && !isAwaiting(detail.error) ? (
        <ErrorState
          title="Could not load run"
          detail={(detail.error as Error)?.message}
          onRetry={() => detail.refetch()}
        />
      ) : null}

      {live ? <RunOverview run={live} /> : <LoadingState title="Loading run" />}

      {metrics.isError && !isAwaiting(metrics.error) ? (
        <Banner
          severity="danger"
          title="Could not load metrics"
          message={(metrics.error as Error)?.message}
        />
      ) : null}
      {isAwaiting(metrics.error) ? (
        <AwaitingApiOrError
          title="Backtest metrics"
          endpoint={`GET /api/v1/research/backtests/${runId}/metrics`}
          awaitingMessage="Metrics endpoint is not registered yet."
          error={metrics.error}
          onRetry={() => metrics.refetch()}
        />
      ) : null}
      {metrics.data ? <MetricCards metrics={metrics.data} /> : null}

      {results.isError && !isAwaiting(results.error) ? (
        <Banner
          severity="danger"
          title="Could not load results"
          message={(results.error as Error)?.message}
        />
      ) : null}
      {isAwaiting(results.error) ? (
        <AwaitingApiOrError
          title="Backtest results"
          endpoint={`GET /api/v1/research/backtests/${runId}/results`}
          awaitingMessage="Results endpoint is not registered yet."
          error={results.error}
          onRetry={() => results.refetch()}
        />
      ) : null}
      {monteCarlo ? <MonteCarloCard result={monteCarlo} /> : null}

      {results.data ? (
        <ResultsBody results={results.data} onTradeClick={(id) => setDrillCardId(id)} />
      ) : null}

      <RiskDecisionCardDrawer
        open={drillCardId !== null}
        onOpenChange={(next) => {
          if (!next) setDrillCardId(null);
        }}
        riskDecisionId={drillCardId}
      />
    </div>
  );
}

function RunOverview({ run }: { run: BacktestRun }): JSX.Element {
  const lastEvent = run.status_history.at(-1);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Run overview</CardTitle>
        <span className="flex items-center gap-2">
          <StatusBadge tone={statusTone(run.status)}>{run.status}</StatusBadge>
          <span className="text-[11px] text-fg-subtle" title={run.run_id}>
            run {run.run_id.slice(0, 8)}
          </span>
        </span>
      </CardHeader>
      <CardBody className="grid grid-cols-2 gap-3 text-xs md:grid-cols-4">
        <Field label="Universe" value={run.universe.join(", ") || "—"} />
        <Field label="Timeframe" value={run.timeframe} />
        <Field label="Window" value={`${formatDateOnly(run.start)} → ${formatDateOnly(run.end)}`} />
        <Field label="Initial capital" value={formatCurrency(run.initial_capital, { whole: true })} />
        <Field label="Bars" value={formatQuantity(run.bar_count)} />
        <Field label="SignalPlans" value={formatQuantity(run.signal_plan_count)} />
        <Field label="Simulated trades" value={formatQuantity(run.simulated_trade_count)} />
        <Field
          label="Last status change"
          value={lastEvent?.at ? formatTimestamp(lastEvent.at) : formatTimestamp(run.created_at)}
        />
      </CardBody>
    </Card>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div>
      <div className="text-fg-muted">{label}</div>
      <div className="mt-0.5">{value}</div>
    </div>
  );
}

function MetricCards({ metrics }: { metrics: BacktestMetricsResponse }): JSX.Element {
  const m = metrics.metrics ?? {};
  const cards: Array<{
    label: string;
    value: React.ReactNode;
    tone?: "ok" | "warn" | "danger" | "info" | "neutral";
    sub?: React.ReactNode;
  }> = [
    {
      label: "CAGR",
      value: formatMetricPercent(m.cagr),
      tone: pctTone(m.cagr),
    },
    { label: "Sharpe", value: formatMetricNumber(m.sharpe), tone: ratioTone(m.sharpe) },
    { label: "Sortino", value: formatMetricNumber(m.sortino), tone: ratioTone(m.sortino) },
    { label: "Calmar", value: formatMetricNumber(m.calmar), tone: ratioTone(m.calmar) },
    {
      label: "Max drawdown",
      value: formatMetricPercent(m.max_drawdown ?? m.max_dd),
      tone: "danger",
    },
    { label: "Hit rate", value: formatMetricPercent(m.hit_rate) },
    { label: "Profit factor", value: formatMetricNumber(m.profit_factor) },
    { label: "Expectancy", value: formatMetricCurrency(m.expectancy) },
    { label: "Exposure", value: formatMetricPercent(m.exposure) },
    { label: "Turnover", value: formatMetricPercent(m.turnover) },
    { label: "Time in market", value: formatMetricPercent(m.time_in_market) },
    {
      label: "Cost model",
      value: <CostModelInline cost={metrics.cost_model} />,
      sub: <span className="text-fg-subtle">commissions · slippage · borrow</span>,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
      {cards.map((c) => (
        <KpiCard key={c.label} label={c.label} value={c.value} tone={c.tone} sublabel={c.sub} />
      ))}
    </div>
  );
}

function CostModelInline({ cost }: { cost: Record<string, unknown> }): JSX.Element {
  const commissions = cost.commissions ?? cost.commission ?? null;
  const slippageBps = cost.slippage_bps ?? cost.slippage ?? null;
  const borrow = cost.borrow_cost ?? cost.borrow_bps ?? null;
  if (commissions == null && slippageBps == null && borrow == null) {
    return <span className="text-fg-subtle">—</span>;
  }
  return (
    <span className="text-base font-semibold tabular leading-tight">
      {commissions != null ? `c=${formatScalar(commissions)}` : ""}
      {slippageBps != null ? ` s=${formatScalar(slippageBps)}` : ""}
      {borrow != null ? ` b=${formatScalar(borrow)}` : ""}
    </span>
  );
}

function ResultsBody({
  results,
  onTradeClick,
}: {
  results: BacktestResultsResponse;
  onTradeClick?: (riskDecisionId: string | null) => void;
}): JSX.Element {
  const equityValues = useMemo(
    () => extractEquityValues(results.equity_curve),
    [results.equity_curve],
  );
  const drawdownValues = useMemo(
    () => extractDrawdownValues(results.drawdown_series),
    [results.drawdown_series],
  );
  const finalEquity = equityValues.at(-1);
  const peakDrawdown = drawdownValues.length ? Math.min(...drawdownValues) : null;
  const regimeRows = useMemo(
    () => normalizeRegimeMetrics(results.per_regime_metrics),
    [results.per_regime_metrics],
  );

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Equity curve</CardTitle>
          <span className="text-xs text-fg-muted">
            {finalEquity != null ? formatCurrency(finalEquity) : "—"}
          </span>
        </CardHeader>
        <CardBody>
          <Sparkline
            ariaLabel="equity curve"
            values={equityValues}
            empty={equityValues.length === 0}
            emptyMessage="awaiting equity points"
            tone="ok"
            height={120}
          />
        </CardBody>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Drawdown</CardTitle>
          <span className="text-xs text-fg-muted">
            peak {peakDrawdown != null ? formatMetricPercent(peakDrawdown) : "—"}
          </span>
        </CardHeader>
        <CardBody>
          <Sparkline
            ariaLabel="drawdown"
            values={drawdownValues}
            empty={drawdownValues.length === 0}
            emptyMessage="awaiting drawdown points"
            tone="danger"
            baselineAtZero
            height={120}
          />
        </CardBody>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Per-regime metrics</CardTitle>
          <StatusBadge>{regimeRows.length}</StatusBadge>
        </CardHeader>
        <CardBody className="p-0">
          {regimeRows.length === 0 ? (
            <div className="p-3">
              <span className="text-xs text-fg-subtle">
                No per-regime breakdown reported. Backend stamps regime tags on every bar; the
                breakdown table populates the moment one is recorded.
              </span>
            </div>
          ) : (
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Regime</th>
                  <th>Bars</th>
                  <th>Trades</th>
                  <th>Hit rate</th>
                  <th>Sharpe</th>
                  <th>Return</th>
                </tr>
              </thead>
              <tbody>
                {regimeRows.map((row) => (
                  <tr key={row.regime}>
                    <td>
                      <StatusBadge tone="info">{row.regime}</StatusBadge>
                    </td>
                    <td className="tabular text-fg-muted">{formatMetricNumber(row.bars)}</td>
                    <td className="tabular text-fg-muted">{formatMetricNumber(row.trades)}</td>
                    <td className="tabular">{formatMetricPercent(row.hit_rate)}</td>
                    <td className="tabular">{formatMetricNumber(row.sharpe)}</td>
                    <td className="tabular">{formatMetricPercent(row.return_pct ?? row.return)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Per-symbol breakdown</CardTitle>
          <StatusBadge>{results.per_symbol_breakdown.length}</StatusBadge>
        </CardHeader>
        <CardBody className="p-0">
          {results.per_symbol_breakdown.length === 0 ? (
            <div className="p-3 text-xs text-fg-subtle">no per-symbol data reported.</div>
          ) : (
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Trades</th>
                  <th>Win rate</th>
                  <th>Return</th>
                  <th>P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {results.per_symbol_breakdown.map((row, i) => (
                  <PerSymbolRow key={`${row.symbol ?? "row"}-${i}`} row={row} />
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>

      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>Trade ledger</CardTitle>
          <StatusBadge>{results.trade_ledger.length}</StatusBadge>
        </CardHeader>
        <CardBody className="p-0">
          {results.trade_ledger.length === 0 ? (
            <div className="p-3 text-xs text-fg-subtle">no trades reported.</div>
          ) : (
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>Opened</th>
                  <th>Closed</th>
                  <th>Regime</th>
                  <th>P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {results.trade_ledger.slice(0, 200).map((t, i) => (
                  <TradeRow
                    key={`${t.symbol ?? "trade"}-${i}`}
                    trade={t}
                    onClick={onTradeClick}
                  />
                ))}
              </tbody>
            </table>
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function PerSymbolRow({ row }: { row: PerSymbolBreakdown }): JSX.Element {
  return (
    <tr>
      <td className="font-medium">{row.symbol ?? "—"}</td>
      <td className="tabular text-fg-muted">{formatMetricNumber(row.trades)}</td>
      <td className="tabular">{formatMetricPercent(row.win_rate)}</td>
      <td className="tabular">{formatMetricPercent(row.return_pct)}</td>
      <td className="tabular">{formatMetricCurrency(row.pnl)}</td>
    </tr>
  );
}

function TradeRow({
  trade,
  onClick,
}: {
  trade: TradeLedgerEntry;
  onClick?: (riskDecisionId: string | null) => void;
}): JSX.Element {
  const qty = trade.quantity ?? trade.qty;
  const cardId = (trade as Record<string, unknown>).risk_decision_id;
  const cardIdStr = typeof cardId === "string" ? cardId : null;
  const interactive = onClick && cardIdStr;
  const pnl = (trade.pnl ?? (trade as Record<string, unknown>).net_pnl) as number | undefined;
  return (
    <tr
      className={interactive ? "cursor-pointer hover:bg-bg-inset" : ""}
      onClick={interactive ? () => onClick?.(cardIdStr) : undefined}
      title={interactive ? "Open risk decision card" : undefined}
    >
      <td className="font-medium">{trade.symbol ?? "—"}</td>
      <td className="text-fg-muted">{trade.side ?? "—"}</td>
      <td className="tabular text-fg-muted">{qty != null ? formatQuantity(qty) : "—"}</td>
      <td className="tabular">{formatMetricCurrency(trade.entry_price)}</td>
      <td className="tabular">{formatMetricCurrency(trade.exit_price)}</td>
      <td className="text-fg-muted">{trade.opened_at ? formatTimestamp(trade.opened_at) : "—"}</td>
      <td className="text-fg-muted">{trade.closed_at ? formatTimestamp(trade.closed_at) : "—"}</td>
      <td>{trade.regime ? <StatusBadge tone="info">{trade.regime}</StatusBadge> : "—"}</td>
      <td className={tradePnlClass(pnl)}>{formatMetricCurrency(pnl)}</td>
    </tr>
  );
}

function tradePnlClass(pnl: number | undefined): string {
  if (pnl == null) return "tabular text-fg-muted";
  if (pnl > 0) return "tabular text-ok";
  if (pnl < 0) return "tabular text-danger";
  return "tabular text-fg-muted";
}

// ---------- helpers ----------

function extractEquityValues(points: EquityPoint[]): number[] {
  const out: number[] = [];
  for (const p of points) {
    const v = p.equity ?? p.value;
    if (typeof v === "number" && Number.isFinite(v)) out.push(v);
  }
  return out;
}

function extractDrawdownValues(points: DrawdownPoint[]): number[] {
  const out: number[] = [];
  for (const p of points) {
    const v = p.drawdown ?? p.underwater ?? p.value;
    if (typeof v === "number" && Number.isFinite(v)) out.push(v);
  }
  return out;
}

interface RegimeRow {
  regime: string;
  bars?: number;
  trades?: number;
  hit_rate?: number;
  sharpe?: number;
  return_pct?: number;
  return?: number;
}

function normalizeRegimeMetrics(raw: Record<string, unknown>): RegimeRow[] {
  const rows: RegimeRow[] = [];
  for (const [key, value] of Object.entries(raw)) {
    if (!value || typeof value !== "object") continue;
    const v = value as Record<string, unknown>;
    rows.push({
      regime: key,
      bars: numericOr(v.bars ?? v.bar_count),
      trades: numericOr(v.trades ?? v.trade_count),
      hit_rate: numericOr(v.hit_rate),
      sharpe: numericOr(v.sharpe),
      return_pct: numericOr(v.return_pct ?? v.return ?? v.cagr),
    });
  }
  return rows;
}

function numericOr(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function formatMetricNumber(v: unknown): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return v.toFixed(2);
}

function formatMetricPercent(v: unknown): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  // Heuristic: 0..1 ratio renders as %, larger numbers are already percent.
  const pct = Math.abs(v) <= 1 ? v * 100 : v;
  return formatPercent(pct);
}

function formatMetricCurrency(v: unknown): string {
  if (typeof v !== "number" || !Number.isFinite(v)) return "—";
  return formatCurrency(v);
}

function pctTone(v: unknown): "ok" | "danger" | "neutral" {
  if (typeof v !== "number" || !Number.isFinite(v)) return "neutral";
  return v >= 0 ? "ok" : "danger";
}

function ratioTone(v: unknown): "ok" | "warn" | "danger" | "neutral" {
  if (typeof v !== "number" || !Number.isFinite(v)) return "neutral";
  if (v >= 1.5) return "ok";
  if (v >= 0.5) return "warn";
  if (v < 0) return "danger";
  return "neutral";
}

function formatScalar(v: unknown): string {
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toString();
    return v.toFixed(3);
  }
  if (v == null) return "—";
  return String(v);
}

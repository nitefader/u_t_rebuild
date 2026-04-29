import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { HistoricalDatasetsApi } from "@/api/historicalDatasets";
import type { HistoricalBar, HistoricalDatasetSummary } from "@/api/schemas/historicalDatasets";
import type { ChartBar } from "@/api/schemas/chartLab";
import { PriceChart } from "@/components/charts/PriceChart";
import { StatusBadge, type StatusTone } from "@/components/badges/StatusBadge";
import { Banner } from "@/components/ui/Banner";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { ErrorState } from "@/components/empty/ErrorState";
import { LoadingState } from "@/components/empty/LoadingState";
import { PageHeader } from "@/routes/PageHeader";
import { formatTimestamp } from "@/lib/format";
import { cn } from "@/lib/cn";

const BAR_PAGE = 200;
const CHART_BAR_CAP = 500;

function qualityTone(s: string): StatusTone {
  if (s === "ok") return "ok";
  if (s === "warning") return "warn";
  if (s === "stale") return "danger";
  return "neutral";
}

function toChartBars(bars: HistoricalBar[], symbol: string): ChartBar[] {
  return bars.map((b) => ({
    symbol,
    timeframe: undefined,
    timestamp: b.timestamp,
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
    volume: b.volume ?? undefined,
    vwap: b.vwap ?? undefined,
  }));
}

function fmtNum(n: number | null | undefined, decimals: number): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(decimals);
}

function fmtBool(b: boolean | null | undefined): string {
  if (b == null) return "—";
  return b ? "Y" : "N";
}

function MarkdownBlock({ text, className }: { text: string; className?: string }): JSX.Element {
  return (
    <div
      className={cn("rounded border border-border/60 bg-bg-subtle/40 px-3 py-2 text-xs text-fg-muted", className)}
    >
      <pre className="whitespace-pre-wrap font-sans">{text}</pre>
    </div>
  );
}

export function DataCenterHistoricalDatasets(): JSX.Element {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [barOffset, setBarOffset] = useState(0);

  const listQ = useQuery({
    queryKey: ["data-center", "historical-datasets"],
    queryFn: () => HistoricalDatasetsApi.list(),
    refetchInterval: 60_000,
  });

  const detailQ = useQuery({
    queryKey: ["data-center", "historical-datasets", selectedId, "detail"],
    queryFn: () => HistoricalDatasetsApi.detail(selectedId!),
    enabled: Boolean(selectedId),
  });

  const barsQ = useQuery({
    queryKey: ["data-center", "historical-datasets", selectedId, "bars", barOffset],
    queryFn: () => HistoricalDatasetsApi.bars(selectedId!, { offset: barOffset, limit: BAR_PAGE }),
    enabled: Boolean(selectedId),
  });

  const chartBarsQ = useQuery({
    queryKey: ["data-center", "historical-datasets", selectedId, "bars", "chart-preview"],
    queryFn: () => HistoricalDatasetsApi.bars(selectedId!, { offset: 0, limit: CHART_BAR_CAP }),
    enabled: Boolean(selectedId),
  });

  const selectedSummary = useMemo(
    () => listQ.data?.items.find((i: HistoricalDatasetSummary) => i.dataset_id === selectedId) ?? null,
    [listQ.data, selectedId],
  );

  const bars = barsQ.data?.bars ?? [];
  const previewBars = chartBarsQ.data?.bars ?? [];
  const chartBars = useMemo(() => {
    if (!selectedSummary) return [];
    return toChartBars(previewBars, selectedSummary.symbol);
  }, [previewBars, selectedSummary]);

  const optionalCols = useMemo(() => {
    const has = (pred: (b: HistoricalBar) => boolean) => bars.some(pred);
    return {
      bid: has((b) => b.bid != null),
      ask: has((b) => b.ask != null),
      spread: has((b) => b.spread != null),
      source_feed: has((b) => Boolean(b.source_feed)),
      adjusted_close: has((b) => b.adjusted_close != null),
      corporate_action_flag: has((b) => b.corporate_action_flag != null),
      gap_flag: has((b) => b.gap_flag != null),
      synthetic_bar_flag: has((b) => b.synthetic_bar_flag != null),
    };
  }, [bars]);

  function selectRow(id: string): void {
    setSelectedId(id);
    setBarOffset(0);
    setDrawerOpen(true);
  }

  function clearSelection(): void {
    setSelectedId(null);
    setDrawerOpen(false);
    setBarOffset(0);
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Data Center · Historical Datasets"
        subtitle="Read-only inspection: one HistoricalDataSet, many bars, one visual surface before Chart Lab, Sim Lab, or backtests."
        explainSlug="data-center"
      />

      <Banner
        severity="info"
        title="Fixture-backed historical catalog"
        message="Persistence and live vendor reconciliation ship on the doctrine spine. This page is the operator truth surface for raw OHLCV/VWAP shape and quality flags."
      />

      {listQ.isLoading ? <LoadingState title="Loading dataset inventory" /> : null}
      {listQ.isError ? <ErrorState title="Inventory failed" message={(listQ.error as Error).message} /> : null}

      {listQ.data ? (
        <Card>
          <CardHeader>
            <CardTitle>Dataset inventory</CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-xs">
                <thead className="border-b border-border bg-bg-subtle/50 text-fg-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">Symbol</th>
                    <th className="px-3 py-2 font-medium">Timeframe</th>
                    <th className="px-3 py-2 font-medium">Provider</th>
                    <th className="px-3 py-2 font-medium">Adjustment</th>
                    <th className="px-3 py-2 font-medium text-right">Bars</th>
                    <th className="px-3 py-2 font-medium">Coverage</th>
                    <th className="px-3 py-2 font-medium">Quality</th>
                  </tr>
                </thead>
                <tbody>
                  {listQ.data.items.map((row: HistoricalDatasetSummary) => {
                    const active = row.dataset_id === selectedId;
                    return (
                      <tr
                        key={row.dataset_id}
                        className={cn(
                          "cursor-pointer border-b border-border/60 hover:bg-bg-subtle/60",
                          active && "bg-bg-subtle",
                        )}
                        onClick={() => selectRow(row.dataset_id)}
                      >
                        <td className="px-3 py-2 font-mono font-medium text-fg">{row.symbol}</td>
                        <td className="px-3 py-2 text-fg-muted">{row.timeframe}</td>
                        <td className="px-3 py-2 text-fg-muted">{row.provider}</td>
                        <td className="px-3 py-2 text-fg-muted">{row.adjustment_label}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-fg">{row.bar_count}</td>
                        <td className="px-3 py-2 text-fg-muted">
                          {formatTimestamp(row.coverage_start)} → {formatTimestamp(row.coverage_end)}
                        </td>
                        <td className="px-3 py-2">
                          <StatusBadge tone={qualityTone(row.aggregate_quality_status)}>{row.aggregate_quality_status}</StatusBadge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </CardBody>
        </Card>
      ) : null}

      {selectedId && selectedSummary ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-end gap-2">
            {!drawerOpen ? (
              <button
                type="button"
                className="rounded border border-border px-2 py-1 text-[11px] font-medium text-fg-muted hover:bg-bg-subtle hover:text-fg"
                onClick={() => setDrawerOpen(true)}
              >
                Open provider drawer
              </button>
            ) : null}
            <button
              type="button"
              className="rounded border border-border px-2 py-1 text-[11px] font-medium text-fg-muted hover:bg-bg-subtle hover:text-fg"
              onClick={clearSelection}
            >
              Clear selection
            </button>
          </div>
          {detailQ.isLoading ? <LoadingState title="Loading dataset detail" /> : null}
          {detailQ.isError ? <ErrorState title="Detail failed" message={(detailQ.error as Error).message} /> : null}
          {barsQ.isLoading ? <LoadingState title="Loading bars" /> : null}
          {barsQ.isError ? <ErrorState title="Bars failed" message={(barsQ.error as Error).message} /> : null}
          {chartBarsQ.isLoading ? <LoadingState title="Loading chart preview" /> : null}
          {chartBarsQ.isError ? (
            <ErrorState title="Chart preview failed" message={(chartBarsQ.error as Error).message} />
          ) : null}

          {detailQ.data ? (
            <Card>
              <CardHeader>
                <CardTitle>
                  Selected: {detailQ.data.symbol} | {detailQ.data.timeframe} | {detailQ.data.provider} |{" "}
                  {detailQ.data.adjustment_label}
                </CardTitle>
              </CardHeader>
              <CardBody className="space-y-3 text-xs">
                <div className="flex flex-wrap gap-3 text-fg-muted">
                  <span>
                    <span className="text-fg-subtle">Coverage</span>: {formatTimestamp(detailQ.data.coverage_start)} →{" "}
                    {formatTimestamp(detailQ.data.coverage_end)}
                  </span>
                  <span>
                    <span className="text-fg-subtle">Missing bars (flagged)</span>: {detailQ.data.missing_bar_count}
                  </span>
                  <span>
                    <span className="text-fg-subtle">Aggregate quality</span>:{" "}
                    <StatusBadge tone={qualityTone(detailQ.data.aggregate_quality_status)}>
                      {detailQ.data.aggregate_quality_status}
                    </StatusBadge>
                  </span>
                </div>
                {detailQ.data.warnings.length ? (
                  <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-amber-100">
                    <div className="font-semibold text-amber-50">Warnings</div>
                    <ul className="mt-1 list-disc pl-4">
                      {detailQ.data.warnings.map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </CardBody>
            </Card>
          ) : null}

          {chartBars.length ? (
            <Card>
              <CardHeader>
                <CardTitle>Read-only dataset chart</CardTitle>
              </CardHeader>
              <CardBody>
                <PriceChart
                  symbol={selectedSummary.symbol}
                  bars={chartBars}
                  height={360}
                  dataInspectionMode
                  className="min-h-[360px]"
                />
                <p className="mt-2 text-[11px] text-fg-muted">
                  Candlesticks + volume strip + VWAP overlay when the bar payload includes volume and VWAP. This is not
                  Chart Lab streaming. Preview loads up to {CHART_BAR_CAP} bars from the start of the series; the table
                  below pages through the full dataset.
                </p>
              </CardBody>
            </Card>
          ) : null}

          {bars.length ? (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle>Raw bar table (OHLCV / VWAP)</CardTitle>
                  {barsQ.data ? (
                    <div className="flex items-center gap-2 text-[11px] text-fg-muted">
                      <span className="tabular-nums">
                        {barsQ.data.offset + 1}–{barsQ.data.offset + bars.length} of {barsQ.data.total}
                      </span>
                      <button
                        type="button"
                        className="rounded border border-border px-2 py-0.5 hover:bg-bg-subtle disabled:opacity-40"
                        disabled={barOffset <= 0}
                        onClick={() => setBarOffset((o) => Math.max(0, o - BAR_PAGE))}
                      >
                        Prev
                      </button>
                      <button
                        type="button"
                        className="rounded border border-border px-2 py-0.5 hover:bg-bg-subtle disabled:opacity-40"
                        disabled={!barsQ.data || barOffset + BAR_PAGE >= barsQ.data.total}
                        onClick={() => setBarOffset((o) => o + BAR_PAGE)}
                      >
                        Next
                      </button>
                    </div>
                  ) : null}
                </div>
              </CardHeader>
              <CardBody className="p-0">
                <div className="max-h-[420px] overflow-auto">
                  <table className="w-full min-w-[1100px] text-left text-[11px]">
                    <thead className="sticky top-0 z-10 border-b border-border bg-bg-raised text-fg-muted">
                      <tr>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium">Timestamp</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Open</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">High</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Low</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Close</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Volume</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">VWAP</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Trade Count</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium">Provider</th>
                        <th className="whitespace-nowrap px-2 py-1.5 font-medium">Quality</th>
                        {optionalCols.bid ? <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Bid</th> : null}
                        {optionalCols.ask ? <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Ask</th> : null}
                        {optionalCols.spread ? (
                          <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Spread</th>
                        ) : null}
                        {optionalCols.source_feed ? (
                          <th className="whitespace-nowrap px-2 py-1.5 font-medium">Source Feed</th>
                        ) : null}
                        {optionalCols.adjusted_close ? (
                          <th className="whitespace-nowrap px-2 py-1.5 font-medium text-right">Adj. Close</th>
                        ) : null}
                        {optionalCols.corporate_action_flag ? (
                          <th className="whitespace-nowrap px-2 py-1.5 font-medium">Corp. Action</th>
                        ) : null}
                        {optionalCols.gap_flag ? <th className="whitespace-nowrap px-2 py-1.5 font-medium">Gap</th> : null}
                        {optionalCols.synthetic_bar_flag ? (
                          <th className="whitespace-nowrap px-2 py-1.5 font-medium">Synthetic</th>
                        ) : null}
                      </tr>
                    </thead>
                    <tbody>
                      {bars.map((b) => (
                        <tr key={b.timestamp} className="border-b border-border/40 hover:bg-bg-subtle/40">
                          <td className="whitespace-nowrap px-2 py-1 font-mono text-fg">{formatTimestamp(b.timestamp)}</td>
                          <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.open, 4)}</td>
                          <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.high, 4)}</td>
                          <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.low, 4)}</td>
                          <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.close, 4)}</td>
                          <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.volume, 0)}</td>
                          <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.vwap, 4)}</td>
                          <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{b.trade_count ?? "—"}</td>
                          <td className="whitespace-nowrap px-2 py-1 text-fg-muted">{b.provider}</td>
                          <td className="whitespace-nowrap px-2 py-1">
                            <StatusBadge tone={qualityTone(b.quality_status)}>{b.quality_status}</StatusBadge>
                          </td>
                          {optionalCols.bid ? (
                            <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.bid, 4)}</td>
                          ) : null}
                          {optionalCols.ask ? (
                            <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.ask, 4)}</td>
                          ) : null}
                          {optionalCols.spread ? (
                            <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.spread, 6)}</td>
                          ) : null}
                          {optionalCols.source_feed ? (
                            <td className="whitespace-nowrap px-2 py-1 text-fg-muted">{b.source_feed ?? "—"}</td>
                          ) : null}
                          {optionalCols.adjusted_close ? (
                            <td className="whitespace-nowrap px-2 py-1 text-right tabular-nums">{fmtNum(b.adjusted_close, 4)}</td>
                          ) : null}
                          {optionalCols.corporate_action_flag ? (
                            <td className="whitespace-nowrap px-2 py-1">{fmtBool(b.corporate_action_flag)}</td>
                          ) : null}
                          {optionalCols.gap_flag ? (
                            <td className="whitespace-nowrap px-2 py-1">{fmtBool(b.gap_flag)}</td>
                          ) : null}
                          {optionalCols.synthetic_bar_flag ? (
                            <td className="whitespace-nowrap px-2 py-1">{fmtBool(b.synthetic_bar_flag)}</td>
                          ) : null}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardBody>
            </Card>
          ) : null}
        </div>
      ) : null}

      <Drawer open={Boolean(selectedId) && drawerOpen} onOpenChange={setDrawerOpen}>
        <DrawerContent aria-describedby={undefined}>
          <DrawerHeader>
            <DrawerTitle>Provider &amp; quality</DrawerTitle>
            <DrawerDescription>
              {selectedSummary
                ? `${selectedSummary.symbol} · ${selectedSummary.timeframe} · ${selectedSummary.provider}`
                : ""}
            </DrawerDescription>
          </DrawerHeader>
          <DrawerBody className="space-y-4">
            {detailQ.data ? (
              <>
                <section>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">Provider decision</h3>
                  <MarkdownBlock text={detailQ.data.provider_decision_markdown} />
                </section>
                <section>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">Quality report</h3>
                  <MarkdownBlock text={detailQ.data.quality_report_markdown} />
                </section>
                <section>
                  <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-fg-subtle">Usage history</h3>
                  <ul className="space-y-2 text-xs text-fg-muted">
                    {detailQ.data.usage_history.map((u) => (
                      <li key={`${u.tool}-${u.last_used_at}`} className="rounded border border-border/60 px-2 py-1.5">
                        <div className="font-medium text-fg">{u.tool}</div>
                        <div className="tabular-nums">{formatTimestamp(u.last_used_at)}</div>
                        {u.note ? <div className="mt-0.5 text-fg-muted">{u.note}</div> : null}
                      </li>
                    ))}
                  </ul>
                </section>
              </>
            ) : detailQ.isLoading ? (
              <LoadingState title="Loading drawer" />
            ) : (
              <p className="text-xs text-fg-muted">Select a dataset row to load provider context.</p>
            )}
          </DrawerBody>
        </DrawerContent>
      </Drawer>
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Pause, Pin, PinOff, Play, Search, FlaskConical, Radio } from "lucide-react";
import { ChartLabApi } from "@/api/chartLab";
import {
  ChartLabFrameSchema,
  type ChartBar,
  type ChartLabPreviewResponse,
} from "@/api/schemas/chartLab";
import { useWS } from "@/api/ws";
import { useChartLabPin } from "@/lib/chartLabPin";
import { StrategiesApi } from "@/api/strategies";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { PriceChart } from "@/components/charts/PriceChart";
import {
  StrategyPreviewChart,
  type PreviewBarRow,
} from "@/components/charts/StrategyPreviewChart";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { PageHeader } from "./PageHeader";
import { formatTimestamp, relativeTime } from "@/lib/format";

const MAX_BARS = 240;

type Mode = "stream" | "preview";

export function ChartLab(): JSX.Element {
  const [mode, setMode] = useState<Mode>("stream");

  return (
    <div className="space-y-4">
      <PageHeader
        title="Chart Lab"
        subtitle="Streaming bar preview and strategy replay. Research only - Chart Lab cannot submit broker orders."
        explainSlug="chart-lab"
      />
      <Tabs value={mode} onValueChange={(v) => setMode(v as Mode)}>
        <TabsList>
          <TabsTrigger value="stream">
            <Radio className="h-3.5 w-3.5" aria-hidden="true" />
            Live stream
          </TabsTrigger>
          <TabsTrigger value="preview">
            <FlaskConical className="h-3.5 w-3.5" aria-hidden="true" />
            Strategy preview
          </TabsTrigger>
        </TabsList>
        <TabsContent value="stream">
          <StreamPane />
        </TabsContent>
        <TabsContent value="preview">
          <PreviewPane />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// -------------------------------------------------------------------------
// Live stream pane (the original Chart Lab surface).
// -------------------------------------------------------------------------

function StreamPane(): JSX.Element {
  const health = useQuery({
    queryKey: ["chart-lab", "health"],
    queryFn: () => ChartLabApi.health(),
    refetchInterval: 30_000,
  });

  const [symbol, setSymbol] = useState<string>("");
  const [active, setActive] = useState<string | null>(null);
  const [bars, setBars] = useState<ChartBar[]>([]);
  const [running, setRunning] = useState<boolean>(false);
  const { symbol: pinnedSymbol, pin, unpin } = useChartLabPin();
  const isPinned = active != null && pinnedSymbol === active;

  useEffect(() => {
    if (!symbol && health.data?.default_symbol) {
      setSymbol(health.data.default_symbol);
    }
  }, [health.data, symbol]);

  const path = useMemo(() => (active ? ChartLabApi.streamPath(active) : ""), [active]);

  const ws = useWS({
    schema: ChartLabFrameSchema,
    path,
    enabled: Boolean(active),
    onMessage: (frame) => {
      if (frame.type === "bar") {
        setBars((prev) => {
          const bar: ChartBar = { ...frame.data, timeframe: frame.data.timeframe ?? "1Min" };
          const next = [...prev, bar];
          if (next.length > MAX_BARS) next.splice(0, next.length - MAX_BARS);
          return next;
        });
      } else if (frame.type === "ready") {
        setRunning(true);
      } else if (frame.type === "error") {
        setRunning(false);
      }
    },
  });

  useEffect(() => {
    if (!active) setRunning(false);
  }, [active]);

  function startStreaming(): void {
    const target = symbol.trim().toUpperCase();
    if (!target) return;
    setBars([]);
    setActive(target);
  }

  function stopStreaming(): void {
    ws.close();
    setActive(null);
    setRunning(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        {active ? (
          <>
            {isPinned ? (
              <Button
                size="sm"
                variant="ghost"
                leftIcon={<PinOff className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={unpin}
              >
                Unpin from dashboard
              </Button>
            ) : (
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<Pin className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() => pin(active)}
              >
                Pin to dashboard
              </Button>
            )}
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Pause className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={stopStreaming}
            >
              Stop
            </Button>
          </>
        ) : (
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={startStreaming}
            disabled={!symbol.trim()}
          >
            Stream
          </Button>
        )}
      </div>

      {health.isLoading ? <LoadingState title="Loading Chart Lab health" /> : null}
      {health.isError ? (
        <ErrorState
          title="Chart Lab not configured"
          detail={(health.error as Error)?.message}
          onRetry={() => health.refetch()}
        />
      ) : null}

      {health.data && !health.data.streaming_enabled ? (
        <Banner
          severity="warning"
          title="Streaming disabled"
          message="Configure Alpaca credentials and enable streaming in Settings before using Chart Lab."
        />
      ) : null}

      {health.data ? (
        <Card>
          <CardHeader>
            <CardTitle>Stream</CardTitle>
            <span className="flex items-center gap-2">
              <StatusBadge tone={health.data.test_stream ? "info" : "ok"}>
                {health.data.test_stream ? "FAKEPACA" : health.data.data_feed.toUpperCase()}
              </StatusBadge>
              {active ? (
                <StatusBadge tone={running ? "ok" : "warn"}>{ws.status}</StatusBadge>
              ) : (
                <StatusBadge tone="muted">idle</StatusBadge>
              )}
            </span>
          </CardHeader>
          <CardBody className="space-y-2">
            <div className="flex flex-wrap items-end gap-2">
              <div className="min-w-48 flex-1">
                <TextField
                  label="Symbol"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                  placeholder={health.data.default_symbol}
                  hint="ENTER on the action button to stream."
                />
              </div>
              <Button
                size="sm"
                variant="primary"
                leftIcon={<Search className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={startStreaming}
                disabled={!symbol.trim()}
              >
                Stream
              </Button>
            </div>
            {ws.lastError ? (
              <Banner severity="warning" title="WebSocket warning" message={ws.lastError} />
            ) : null}
          </CardBody>
        </Card>
      ) : null}

      {bars.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>{active}</CardTitle>
            <StatusBadge>{bars.length} bars</StatusBadge>
          </CardHeader>
          <CardBody className="p-0">
            <PriceChart bars={bars} symbol={active ?? ""} height={360} />
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Open</th>
                  <th>High</th>
                  <th>Low</th>
                  <th>Close</th>
                  <th>Volume</th>
                </tr>
              </thead>
              <tbody>
                {bars
                  .slice(-25)
                  .reverse()
                  .map((bar, i) => (
                    <tr key={`${bar.timestamp}-${i}`}>
                      <td className="text-fg-muted">{formatTimestamp(bar.timestamp)}</td>
                      <td className="tabular">{bar.open}</td>
                      <td className="tabular">{bar.high}</td>
                      <td className="tabular">{bar.low}</td>
                      <td className="tabular font-medium">{bar.close}</td>
                      <td className="tabular text-fg-muted">{bar.volume ?? "-"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
            <div className="px-4 py-2 text-xs text-fg-subtle">
              Last bar {bars[bars.length - 1] ? relativeTime(bars[bars.length - 1].timestamp) : "-"}
            </div>
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

// -------------------------------------------------------------------------
// Strategy preview pane.
// Strategy-only research surface: pick a saved Strategy + version, replay
// over a date window, see candles + auto-derived feature overlays + signal
// markers + condition truth trees on a chart-first surface.
// -------------------------------------------------------------------------

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;
type Timeframe = (typeof TIMEFRAMES)[number];

function defaultIsoDate(daysAgo: number): string {
  const d = new Date(Date.now() - daysAgo * 24 * 3600 * 1000);
  return d.toISOString().slice(0, 10);
}

function previewBarsFrom(response: ChartLabPreviewResponse): PreviewBarRow[] {
  // Backend's preview response carries per-bar feature_values keyed by the
  // canonical feature_key. When the strategy references price.{open,high,
  // low,close} we can reconstruct OHLC; otherwise we fall back to a
  // close-only line so signals + oscillators line up.
  const rows: PreviewBarRow[] = [];
  for (const row of response.bars) {
    const get = (kind: string) =>
      row.feature_values.find(
        (fv) =>
          fv.value !== null &&
          fv.feature_key.includes(`|${row.timeframe}|price.${kind}|`),
      )?.value ?? null;
    const open = get("open");
    const high = get("high");
    const low = get("low");
    const close = get("close");
    if (open !== null && high !== null && low !== null && close !== null) {
      rows.push({ timestamp: row.timestamp, open, high, low, close });
    } else if (close !== null) {
      rows.push({ timestamp: row.timestamp, open: close, high: close, low: close, close });
    }
  }
  return rows;
}

function PreviewPane(): JSX.Element {
  const strategies = useQuery({
    queryKey: ["strategies", "list"],
    queryFn: () => StrategiesApi.list(),
  });

  const [strategyId, setStrategyId] = useState<string>("");
  const [versionId, setVersionId] = useState<string>("");
  const [symbol, setSymbol] = useState<string>("SPY");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [startDate, setStartDate] = useState<string>(defaultIsoDate(30));
  const [endDate, setEndDate] = useState<string>(defaultIsoDate(0));
  const source = "alpaca" as const;
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const versions = useQuery({
    queryKey: ["strategies", strategyId, "versions"],
    queryFn: () => StrategiesApi.listVersions(strategyId),
    enabled: Boolean(strategyId),
  });

  // When the operator picks a different Strategy, default to the latest version.
  useEffect(() => {
    if (!versions.data || versions.data.length === 0) {
      setVersionId("");
      return;
    }
    setVersionId((current) => {
      if (current && versions.data.some((v) => v.strategy_version_id === current)) {
        return current;
      }
      const latest = [...versions.data].sort((a, b) => b.version - a.version)[0];
      return latest.strategy_version_id;
    });
  }, [versions.data]);

  const previewMutation = useMutation({
    mutationFn: () =>
      ChartLabApi.preview({
        strategy_version_id: versionId,
        symbol,
        timeframe,
        start: new Date(startDate).toISOString(),
        end: new Date(endDate + "T23:59:59").toISOString(),
        source,
        adjustment_policy: "split_dividend_adjusted",
      }),
  });

  const response = previewMutation.data;

  // When a new response arrives, default-select all feature_keys.
  useEffect(() => {
    if (!response) return;
    setSelected(new Set(response.feature_plan.feature_keys));
  }, [response]);

  function toggleFeature(key: string): void {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const previewBars = useMemo(
    () => (response ? previewBarsFrom(response) : []),
    [response],
  );
  const totalSignals = useMemo(
    () => (response ? response.bars.reduce((acc, row) => acc + row.signal_markers.length, 0) : 0),
    [response],
  );
  const featureKeys = response?.feature_plan.feature_keys ?? [];

  const canRun = Boolean(versionId && symbol.trim() && startDate && endDate);

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Replay a saved Strategy</CardTitle>
          <StatusBadge tone="muted">strategy-only - no deployment</StatusBadge>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-4">
            <Select
              label="Strategy"
              value={strategyId}
              onChange={(e) => setStrategyId(e.target.value)}
              disabled={strategies.isLoading || strategies.isError}
            >
              <option value="">- pick a strategy -</option>
              {strategies.data?.strategies.map((s) => (
                <option key={s.strategy_id} value={s.strategy_id}>
                  {s.name}
                </option>
              ))}
            </Select>
            <Select
              label="Version"
              value={versionId}
              onChange={(e) => setVersionId(e.target.value)}
              disabled={!strategyId || versions.isLoading}
            >
              <option value="">- pick a version -</option>
              {versions.data?.map((v) => (
                <option key={v.strategy_version_id} value={v.strategy_version_id}>
                  v{v.version} - {v.status}
                </option>
              ))}
            </Select>
            <TextField
              label="Symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="SPY"
            />
            <Select
              label="Timeframe"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value as Timeframe)}
            >
              {TIMEFRAMES.map((tf) => (
                <option key={tf} value={tf}>
                  {tf}
                </option>
              ))}
            </Select>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <TextField
              label="Start"
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
            <TextField
              label="End"
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="primary"
              leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => previewMutation.mutate()}
              disabled={!canRun || previewMutation.isPending}
            >
              {previewMutation.isPending ? "Replaying..." : "Run preview"}
            </Button>
            {response ? (
              <span className="flex items-center gap-2 text-xs text-fg-subtle">
                <StatusBadge tone="ok">{response.bars.length} bars</StatusBadge>
                <StatusBadge tone={totalSignals ? "info" : "muted"}>
                  {totalSignals} signals
                </StatusBadge>
                <StatusBadge tone="muted">{featureKeys.length} features</StatusBadge>
              </span>
            ) : null}
          </div>
          {previewMutation.isError ? (
            <Banner
              severity="warning"
              title="Preview failed"
              message={(previewMutation.error as Error)?.message ?? "preview_error"}
            />
          ) : null}
        </CardBody>
      </Card>

      {response && previewBars.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>{response.session.symbol}</CardTitle>
            <StatusBadge>
              {response.session.timeframe} -{" "}
              {response.bars[0]?.timestamp.slice(0, 10)} to{" "}
              {response.bars[response.bars.length - 1]?.timestamp.slice(0, 10)}
            </StatusBadge>
          </CardHeader>
          <CardBody className="p-0">
            <StrategyPreviewChart
              symbol={response.session.symbol}
              bars={previewBars}
              preview={response.bars}
              plan={response.feature_plan}
              selectedFeatureKeys={[...selected]}
              height={480}
            />
          </CardBody>
        </Card>
      ) : null}

      {response && featureKeys.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Plotted features</CardTitle>
            <StatusBadge tone="muted">
              {selected.size}/{featureKeys.length} on chart
            </StatusBadge>
          </CardHeader>
          <CardBody className="space-y-1">
            <p className="text-xs text-fg-subtle">
              Toggle which auto-derived features the chart overlays. Price-overlay features
              draw on the candle pane; oscillators (RSI, MACD, ATR...) drop into the lower pane.
            </p>
            <ul className="grid grid-cols-1 gap-1 md:grid-cols-2">
              {featureKeys.map((key) => (
                <li key={key} className="flex items-start gap-2 text-xs">
                  <input
                    type="checkbox"
                    aria-label={`Toggle ${key}`}
                    className="mt-0.5"
                    checked={selected.has(key)}
                    onChange={() => toggleFeature(key)}
                  />
                  <code className="break-all rounded bg-bg-inset px-1.5 py-0.5 font-mono text-[11px] text-fg-muted">
                    {key}
                  </code>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {response && response.bars.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Signal markers</CardTitle>
            <StatusBadge tone={totalSignals ? "info" : "muted"}>
              {totalSignals === 0 ? "no fires" : `${totalSignals} fires`}
            </StatusBadge>
          </CardHeader>
          <CardBody className="p-0">
            {totalSignals === 0 ? (
              <p className="px-4 py-3 text-xs text-fg-subtle">
                The strategy did not fire on any bar in this window. The first non-fire reasons:
                {" "}
                <code className="rounded bg-bg-inset px-1 py-0.5 font-mono text-[11px]">
                  {[...new Set(response.bars.flatMap((row) => row.non_fire_reasons))]
                    .slice(0, 3)
                    .join(", ") || "-"}
                </code>
              </p>
            ) : (
              <table className="ut-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Signal</th>
                    <th>Side</th>
                    <th>Type</th>
                    <th>Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {response.bars
                    .flatMap((row) => row.signal_markers)
                    .slice(0, 50)
                    .map((m, i) => (
                      <tr key={`${m.timestamp}-${i}`}>
                        <td className="text-fg-muted">{formatTimestamp(m.timestamp)}</td>
                        <td>{m.signal_name}</td>
                        <td className="capitalize">{m.side}</td>
                        <td className="text-fg-muted">{m.marker_type}</td>
                        <td className="text-fg-muted">{m.reason}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )}
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

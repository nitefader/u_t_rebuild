import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pause, Pin, PinOff, Play, Search } from "lucide-react";
import { ChartLabApi } from "@/api/chartLab";
import { ChartLabFrameSchema, type ChartBar } from "@/api/schemas/chartLab";
import { useWS } from "@/api/ws";
import { useChartLabPin } from "@/lib/chartLabPin";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { PriceChart } from "@/components/charts/PriceChart";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { PageHeader } from "./PageHeader";
import { formatTimestamp, relativeTime } from "@/lib/format";

const MAX_BARS = 240;

export function ChartLab(): JSX.Element {
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

  // Once health resolves, default to its default symbol if no operator pick.
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
      <PageHeader
        title="Chart Lab"
        subtitle="Streaming bar preview surface. Research only — Chart Lab cannot submit broker orders."
        explainSlug="chart-lab"
        actions={
          <span className="flex items-center gap-2">
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
          </span>
        }
      />

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
                      <td className="tabular text-fg-muted">{bar.volume ?? "—"}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
            <div className="px-4 py-2 text-xs text-fg-subtle">
              Last bar {bars[bars.length - 1] ? relativeTime(bars[bars.length - 1].timestamp) : "—"}
            </div>
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}

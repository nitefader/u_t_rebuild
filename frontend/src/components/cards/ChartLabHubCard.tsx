import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Pin, PinOff } from "lucide-react";
import { ChartLabApi } from "@/api/chartLab";
import { ChartLabFrameSchema, type ChartBar } from "@/api/schemas/chartLab";
import { useWS } from "@/api/ws";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { PulseDot, type PulseTone } from "@/components/ui/PulseDot";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { useChartLabPin } from "@/lib/chartLabPin";
import { formatCurrency, relativeTime } from "@/lib/format";

/**
 * ChartLabHubCard — home dashboard hub card for the operator's pinned
 * Chart Lab session (gate D7).
 *
 * Subscribes to `/api/v1/chart-lab/stream?symbol=…` for the pinned
 * symbol and renders a PulseDot whose tone + pulse reflects the
 * underlying stream health:
 *
 *   - open + recent bar           → ok    + pulse
 *   - open but no bar yet         → info  + pulse
 *   - reconnecting / closed       → warn  + no pulse
 *   - error                       → danger + no pulse
 *   - no pin                      → muted + no pulse
 *
 * Doctrine: tab-local pin only (`localStorage`); no server state.
 * Streaming respects the platform live stock hub identity — Chart
 * Lab's per-symbol stream is a read-only window on the platform feed.
 */
export function ChartLabHubCard(): JSX.Element {
  const { symbol, unpin } = useChartLabPin();
  const path = symbol ? ChartLabApi.streamPath(symbol) : "";
  const enabled = Boolean(symbol);

  const [lastBar, setLastBar] = useState<ChartBar | null>(null);
  const [ready, setReady] = useState<boolean>(false);

  useEffect(() => {
    setLastBar(null);
    setReady(false);
  }, [symbol]);

  const ws = useWS({
    schema: ChartLabFrameSchema,
    path,
    enabled,
    onMessage: (frame) => {
      if (frame.type === "ready") setReady(true);
      else if (frame.type === "bar") setLastBar(frame.data);
      else if (frame.type === "error") setReady(false);
    },
  });

  const tone = computeTone({ symbol, ready, status: ws.status, lastEventAt: ws.lastEventAt, lastError: ws.lastError });
  const pulse = symbol != null && (ws.status === "open" || ws.status === "connecting");

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <PulseDot tone={tone} pulse={pulse} size="md" label={`chart-lab ${symbol ?? "unpinned"}`} />
            Chart Lab pin
          </span>
        </CardTitle>
        <span className="flex items-center gap-2">
          {symbol ? (
            <>
              <StatusBadge tone="info">{symbol}</StatusBadge>
              <Button
                size="sm"
                variant="ghost"
                leftIcon={<PinOff className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={unpin}
              >
                Unpin
              </Button>
            </>
          ) : (
            <StatusBadge tone="muted">no pin</StatusBadge>
          )}
        </span>
      </CardHeader>
      <CardBody className="space-y-1.5 text-xs">
        {!symbol ? (
          <UnpinnedBody />
        ) : (
          <>
            <div className="flex items-baseline justify-between">
              <span className="text-fg-muted">Stream</span>
              <span>{describeStatus(ws.status, ready)}</span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-fg-muted">Last bar</span>
              <span className="tabular">
                {lastBar ? formatCurrency(lastBar.close) : "—"}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-fg-muted">Last update</span>
              <span className="text-fg-muted">
                {ws.lastEventAt ? relativeTime(ws.lastEventAt.toISOString()) : "—"}
              </span>
            </div>
            {ws.lastError ? (
              <div className="rounded border border-danger/40 bg-danger-subtle px-2 py-1 text-[11px] text-danger">
                {ws.lastError}
              </div>
            ) : null}
          </>
        )}
      </CardBody>
    </Card>
  );
}

function UnpinnedBody(): JSX.Element {
  return (
    <div className="flex items-center justify-between gap-3 text-fg-muted">
      <span>
        Pin a Chart Lab session to surface its live stream as a hub card here. Status pulse will
        reflect the WebSocket health.
      </span>
      <Link to="/chart-lab">
        <Button size="sm" variant="secondary" leftIcon={<Pin className="h-3.5 w-3.5" aria-hidden="true" />}>
          Open Chart Lab
        </Button>
      </Link>
    </div>
  );
}

function computeTone(args: {
  symbol: string | null;
  ready: boolean;
  status: string;
  lastEventAt: Date | null;
  lastError: string | null;
}): PulseTone {
  const { symbol, status, lastEventAt, lastError } = args;
  if (!symbol) return "muted";
  if (lastError && status !== "open") return "danger";
  if (status === "open") {
    return lastEventAt ? "ok" : "info";
  }
  if (status === "connecting") return "info";
  if (status === "error") return "danger";
  return "warn";
}

function describeStatus(status: string, ready: boolean): string {
  switch (status) {
    case "open":
      return ready ? "open · ready" : "open · awaiting first bar";
    case "connecting":
      return "connecting";
    case "closed":
      return "reconnecting";
    case "error":
      return "error";
    default:
      return status;
  }
}

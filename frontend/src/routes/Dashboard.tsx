import { useQuery } from "@tanstack/react-query";
import { Activity, Wifi } from "lucide-react";
import { OperationsApi } from "@/api/operations";
import { SystemApi } from "@/api/system";
import { Banner } from "@/components/ui/Banner";
import { KpiCard } from "@/components/ui/Card";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { SyncSignal, type SyncState } from "@/components/badges/SyncSignal";
import { ChartLabHubCard } from "@/components/cards/ChartLabHubCard";
import { ResearchJobsHubCard } from "@/components/jobs/ResearchJobsHubCard";
import type { RuntimeOverview } from "@/api/schemas/operations";
import type { TradeStreamStatus, HubStatus } from "@/api/schemas/system";
import { PageHeader } from "./PageHeader";

export function Dashboard(): JSX.Element {
  const streams = useQuery({
    queryKey: ["system", "streams"],
    queryFn: () => SystemApi.streams(),
    refetchInterval: 5_000,
  });
  const overview = useQuery({
    queryKey: ["operations", "overview"],
    queryFn: () => OperationsApi.overview(),
    refetchInterval: 5_000,
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Dashboard"
        subtitle="Live operator health for Ultimate Trader."
        explainSlug="dashboard"
      />

      {streams.isLoading ? (
        <LoadingState title="Reading platform state" message="Querying /api/v1/system/streams" />
      ) : streams.isError ? (
        <ErrorState
          title="Could not load platform state"
          detail={(streams.error as Error)?.message}
          onRetry={() => streams.refetch()}
        />
      ) : (
        <>
          <Banners hubs={streams.data?.market_data_hubs ?? []} tradeStreams={streams.data?.trade_streams ?? []} />
          <KpiGrid
            hubs={streams.data?.market_data_hubs ?? []}
            tradeStreams={streams.data?.trade_streams ?? []}
            overview={overview.data}
            overviewLoading={overview.isLoading}
            overviewError={overview.isError}
          />
          <ChartLabHubCard />
          <ResearchJobsHubCard limit={10} />
        </>
      )}
    </div>
  );
}

function Banners({ hubs, tradeStreams }: { hubs: HubStatus[]; tradeStreams: TradeStreamStatus[] }): JSX.Element | null {
  const liveHubDown = hubs.length > 0 && hubs.every((h) => !h.is_running);
  const allTradeStreamsDown = tradeStreams.length > 0 && tradeStreams.every((s) => !s.is_running);

  if (!liveHubDown && !allTradeStreamsDown) return null;
  return (
    <div className="space-y-2">
      {liveHubDown && (
        <Banner
          severity="danger"
          title="Live Stock Market Data Stream is down"
          message="Operator must investigate. New entries are blocked while the stream is down."
        />
      )}
      {allTradeStreamsDown && (
        <Banner
          severity="danger"
          title="All Account Trade Syncs are down"
          message="Per-account broker truth cannot be trusted. Pause Deployments before resolving."
        />
      )}
    </div>
  );
}

function KpiGrid({
  hubs,
  tradeStreams,
  overview,
  overviewLoading,
  overviewError,
}: {
  hubs: HubStatus[];
  tradeStreams: TradeStreamStatus[];
  overview?: RuntimeOverview;
  overviewLoading: boolean;
  overviewError: boolean;
}): JSX.Element {
  const hubRunning = hubs.filter((h) => h.is_running).length;
  const tradeConnected = tradeStreams.filter((s) => s.is_running && !s.is_stale).length;
  const tradeStale = tradeStreams.filter((s) => s.is_running && s.is_stale).length;
  const tradeDown = tradeStreams.filter((s) => !s.is_running).length;
  const runningDeployments = overview?.deployments.filter((d) => d.is_running).length ?? 0;
  const blockedDeployments = overview?.blocked_deployments.length ?? 0;
  const deploymentCount = overview?.deployments.length ?? 0;
  const deploymentValue = overviewError ? "unavailable" : overviewLoading ? "..." : String(deploymentCount);
  const positionsValue = overviewError ? "unavailable" : overviewLoading ? "..." : String(overview?.open_positions_count ?? 0);
  const deploymentTone = overviewError ? "warn" : blockedDeployments > 0 ? "warn" : "neutral";
  const positionsTone = overviewError ? "warn" : (overview?.open_positions_count ?? 0) > 0 ? "info" : "neutral";

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <KpiCard
        label="Live Stock Data"
        value={hubRunning > 0 ? "Running" : "Down"}
        sublabel={
          hubs[0]
            ? `${hubs[0].provider} - ${hubs[0].asset_class} - ${hubs[0].data_feed.toUpperCase()} - ${hubs[0].subscribed_symbols.length} symbols`
            : "no hub configured"
        }
        tone={hubRunning > 0 ? "ok" : "danger"}
        trailing={<Activity className="h-4 w-4 text-fg-subtle" aria-hidden="true" />}
      />
      <KpiCard
        label="Account Trade Sync"
        value={`${tradeConnected}/${tradeStreams.length}`}
        sublabel={`stale ${tradeStale} - down ${tradeDown}`}
        tone={tradeDown === 0 ? (tradeStale === 0 ? "ok" : "warn") : "danger"}
        trailing={<Wifi className="h-4 w-4 text-fg-subtle" aria-hidden="true" />}
      />
      <KpiCard
        label="Deployments"
        value={deploymentValue}
        sublabel={
          overviewError
            ? "operations overview unavailable"
            : overviewLoading
              ? "loading operations overview"
              : `${runningDeployments} running - ${blockedDeployments} blocked`
        }
        tone={deploymentTone}
      />
      <KpiCard
        label="Open Positions"
        value={positionsValue}
        sublabel={
          overviewError
            ? "operations overview unavailable"
            : overviewLoading
              ? "loading operations overview"
              : `open orders ${overview?.open_orders_count ?? 0}`
        }
        tone={positionsTone}
      />
    </div>
  );
}

/** Compact summary row reused on Dashboard sub-panels. */
export function tradeSyncToState(s: TradeStreamStatus): SyncState {
  if (s.last_error?.toLowerCase().includes("credential")) return "credentials_invalid";
  if (!s.is_running) return "down";
  if (s.is_stale && s.stale_reason && !s.stale_reason.toLowerCase().includes("no_event")) return "stale";
  if (s.last_event_at) return "connected";
  return "idle";
}

/** Render compact sync chip for a trade stream. */
export function TradeSyncChip({ s }: { s: TradeStreamStatus }): JSX.Element {
  return <SyncSignal state={tradeSyncToState(s)} label={s.account_label ?? s.account_id} />;
}

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Clock, Pause, Play, Search, ShieldAlert, TrendingDown, Zap } from "lucide-react";
import { OperationsApi } from "@/api/operations";
import { SystemApi } from "@/api/system";
import { TimelinesApi } from "@/api/timelines";
import type {
  AccountSummary,
  DeploymentSummary,
  GovernorDecision,
  RuntimeOverview,
} from "@/api/schemas/operations";
import type { GovernorDecisionTrace } from "@/api/schemas/timelines";
import type { DailyRiskStateResponse } from "@/api/schemas/dailyRiskState";
import type { HubStatus, TradeStreamStatus } from "@/api/schemas/system";
import { TRADING_HORIZON_LABELS } from "@/api/schemas/risk";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { DangerConfirm } from "@/components/ui/DangerConfirm";
import { TextField } from "@/components/ui/TextField";
import { useToast } from "@/components/ui/Toast";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { AwaitingApiOrError, isAwaiting } from "@/components/empty/AwaitingApi";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { SyncSignal } from "@/components/badges/SyncSignal";
import { PulseDot } from "@/components/ui/PulseDot";
import { tradeSyncToState } from "./Dashboard";
import { OperationsLedger } from "./OperationsLedger";
import { OperationsTimelines } from "./OperationsTimelines";
import { PageHeader } from "./PageHeader";
import { formatCurrency, formatTimestamp, relativeTime } from "@/lib/format";
import { latestBrokerSyncTimestamp } from "@/lib/brokerSync";

/**
 * Operations Center — full surface against /api/v1/operations/* and
 * /api/v1/system/streams.
 */
export function Operations(): JSX.Element {
  const overview = useQuery({
    queryKey: ["operations", "overview"],
    queryFn: () => OperationsApi.overview(),
    refetchInterval: 5_000,
  });
  const streams = useQuery({
    queryKey: ["system", "streams"],
    queryFn: () => SystemApi.streams(),
    refetchInterval: 5_000,
  });

  const isLoading = overview.isLoading || streams.isLoading;
  const isError = overview.isError || streams.isError;

  return (
    <div className="space-y-4">
      <PageHeader
        title="Operations"
        subtitle="Live runtime visibility. Nothing mission-critical fails silently here."
        actions={<GlobalControls overview={overview.data ?? null} />}
        explainSlug="operations"
      />

      {isLoading ? (
        <LoadingState title="Loading runtime state" />
      ) : isError ? (
        <ErrorState
          title="Could not load runtime state"
          detail={(overview.error ?? streams.error)?.toString() ?? ""}
          onRetry={() => {
            void overview.refetch();
            void streams.refetch();
          }}
        />
      ) : (
        <>
          {overview.data ? (
            <OverviewBanners overview={overview.data} streams={streams.data ?? undefined} />
          ) : null}
          {overview.data ? (
            <OverviewKpis overview={overview.data} streams={streams.data ?? undefined} />
          ) : null}

          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <LiveStockHubsCard hubs={streams.data?.market_data_hubs ?? []} />
            <AccountTradeSyncsCard streams={streams.data?.trade_streams ?? []} />
          </div>

          <BrokerOrderTraceCard />

          {overview.data ? <AccountsSection overview={overview.data} streams={streams.data ?? undefined} /> : null}
          <OperationsLedger />
          {overview.data ? <DeploymentsSection overview={overview.data} /> : null}
          <OperationsTimelines />
          {overview.data ? <RecentDecisionsCard overview={overview.data} /> : null}
        </>
      )}
    </div>
  );
}

// ---------- Global control strip ----------

function GlobalControls({ overview }: { overview: RuntimeOverview | null }): JSX.Element {
  const qc = useQueryClient();
  const toast = useToast();
  const killActive = overview?.global_kill_active ?? false;
  const [killOpen, setKillOpen] = useState(false);
  const [resumeOpen, setResumeOpen] = useState(false);

  const kill = useMutation({
    mutationFn: (reason: string) => OperationsApi.globalKill(reason),
    onSuccess: (_data, reason) => {
      toast.show({
        severity: "danger",
        title: "Global kill activated",
        description: `Reason: ${reason}. New opens blocked across every Account.`,
        durationMs: 12_000,
      });
    },
    onError: (e, reason) =>
      toast.show({
        severity: "danger",
        title: "Global kill failed",
        description: `${reason} — ${(e as Error)?.message ?? String(e)}`,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["operations", "overview"] }),
  });
  const resume = useMutation({
    mutationFn: (reason: string) => OperationsApi.globalResume(reason),
    onSuccess: (_data, reason) => {
      toast.show({
        severity: "ok",
        title: "Global trading resumed",
        description: `Reason: ${reason}. Account-level pause states still in effect.`,
      });
    },
    onError: (e, reason) =>
      toast.show({
        severity: "danger",
        title: "Global resume failed",
        description: `${reason} — ${(e as Error)?.message ?? String(e)}`,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["operations", "overview"] }),
  });

  return (
    <div className="flex items-center gap-2">
      {killActive ? (
        <>
          <StatusBadge tone="danger">Global Kill Active</StatusBadge>
          <Button
            variant="ok"
            size="sm"
            leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setResumeOpen(true)}
          >
            Resume Globally
          </Button>
        </>
      ) : (
        <Button
          variant="danger"
          size="sm"
          leftIcon={<ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={() => setKillOpen(true)}
        >
          Global Kill
        </Button>
      )}

      <DangerConfirm
        open={killOpen}
        onOpenChange={setKillOpen}
        title="Activate global kill?"
        message="This blocks every Account from opening new positions across every Deployment. Existing protective orders remain active. Type GLOBAL KILL to confirm."
        expected="GLOBAL KILL"
        actionLabel="Activate Global Kill"
        tone="danger"
        busy={kill.isPending}
        onConfirm={async (reason) => {
          await kill.mutateAsync(reason);
          setKillOpen(false);
        }}
      />
      <DangerConfirm
        open={resumeOpen}
        onOpenChange={setResumeOpen}
        title="Resume global trading?"
        message="Type RESUME to lift the global kill. Account-level pause states remain in effect."
        expected="RESUME"
        actionLabel="Resume Globally"
        tone="ok"
        busy={resume.isPending}
        onConfirm={async (reason) => {
          await resume.mutateAsync(reason);
          setResumeOpen(false);
        }}
      />
    </div>
  );
}

// ---------- Banners ----------

function OverviewBanners({
  overview,
  streams,
}: {
  overview: RuntimeOverview;
  streams: { trade_streams: TradeStreamStatus[]; market_data_hubs: HubStatus[] } | undefined;
}): JSX.Element | null {
  const hubs = streams?.market_data_hubs ?? [];
  const ts = streams?.trade_streams ?? [];
  const hubDown = hubs.length > 0 && hubs.every((h) => !h.is_running);
  const allTradeDown = ts.length > 0 && ts.every((s) => !s.is_running);

  const items: JSX.Element[] = [];
  if (overview.system_recovery_active)
    items.push(
      <Banner
        key="recovery"
        severity="warning"
        title="System recovery in progress"
        message="New orders are blocked until recovery clears."
      />,
    );
  if (overview.global_kill_active)
    items.push(
      <Banner
        key="kill"
        severity="danger"
        title="Global kill is active"
        message="No Account can open new positions until the operator resumes globally."
      />,
    );
  if (hubDown)
    items.push(
      <Banner
        key="hubdown"
        severity="danger"
        title="Live Stock Market Data Stream is down"
        message="New entries are blocked while the platform stream is down."
      />,
    );
  if (allTradeDown)
    items.push(
      <Banner
        key="tradedown"
        severity="danger"
        title="All Account Trade Syncs are down"
        message="Per-Account broker truth cannot be trusted. Pause Deployments before resolving."
      />,
    );
  if (overview.stale_sync_accounts.length > 0)
    items.push(
      <Banner
        key="stale"
        severity="warning"
        title={`${overview.stale_sync_accounts.length} Account(s) have stale broker sync`}
        message="Governor will block new opens for stale Accounts."
      />,
    );

  if (items.length === 0) return null;
  return <div className="space-y-2">{items}</div>;
}

// ---------- KPIs ----------

function OverviewKpis({
  overview,
  streams,
}: {
  overview: RuntimeOverview;
  streams: { trade_streams: TradeStreamStatus[]; market_data_hubs: HubStatus[] } | undefined;
}): JSX.Element {
  const accountCount = overview.broker_accounts.length;
  const runningDeployments = overview.deployments.filter((d) => d.is_running).length;
  const totalDeployments = overview.deployments.length;
  const hubsRunning = (streams?.market_data_hubs ?? []).filter((h) => h.is_running).length;
  const tradeRunning = (streams?.trade_streams ?? []).filter((s) => s.is_running && !s.is_stale).length;
  const tradeTotal = streams?.trade_streams.length ?? 0;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <Tile
        label="Accounts"
        value={accountCount}
        icon={<Activity className="h-4 w-4 text-fg-subtle" aria-hidden="true" />}
      />
      <Tile
        label="Deployments running"
        value={`${runningDeployments}/${totalDeployments}`}
        icon={<Zap className="h-4 w-4 text-fg-subtle" aria-hidden="true" />}
        tone={runningDeployments === totalDeployments ? "ok" : "neutral"}
      />
      <Tile
        label="Open positions / orders"
        value={`${overview.open_positions_count} · ${overview.open_orders_count}`}
      />
      <Tile
        label="Hub · Trade Sync"
        value={`${hubsRunning} · ${tradeRunning}/${tradeTotal}`}
        tone={hubsRunning > 0 && tradeRunning === tradeTotal ? "ok" : "warn"}
      />
    </div>
  );
}

function Tile({
  label,
  value,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  icon?: React.ReactNode;
  tone?: "ok" | "warn" | "danger" | "neutral";
}): JSX.Element {
  const TONE: Record<typeof tone, string> = {
    ok: "text-ok",
    warn: "text-warn",
    danger: "text-danger",
    neutral: "text-fg",
  };
  return (
    <Card className="px-4 py-3">
      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-fg-muted">
        <span>{label}</span>
        {icon}
      </div>
      <div className={`mt-1 text-xl font-semibold tabular ${TONE[tone]}`}>{value}</div>
    </Card>
  );
}

// ---------- Streams panels ----------

function LiveStockHubsCard({ hubs }: { hubs: HubStatus[] }): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
            Live Stock Market Data Stream
          </span>
        </CardTitle>
        <StatusBadge tone={hubs.some((h) => h.is_running) ? "ok" : "danger"}>
          {hubs.some((h) => h.is_running) ? "Running" : "Down"}
        </StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        {hubs.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No hubs registered" message="Configure a Market Data Provider in Providers." />
          </div>
        ) : (
          <table className="ut-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Pipeline</th>
                <th>Feed</th>
                <th>State</th>
                <th>Symbols</th>
                <th>Last message</th>
                <th>Last error</th>
              </tr>
            </thead>
            <tbody>
              {hubs.map((h) => (
                <tr key={`${h.provider}:${h.asset_class}:${h.data_feed}`}>
                  <td className="font-medium">{h.provider}</td>
                  <td>{h.asset_class}</td>
                  <td>{h.data_feed.toUpperCase()}</td>
                  <td>
                    <span className="flex items-center gap-2">
                      <PulseDot tone={h.is_running ? "ok" : "danger"} pulse={h.is_running} size="sm" />
                      {h.is_running ? "running" : "stopped"}
                    </span>
                  </td>
                  <td className="tabular">{h.subscribed_symbols.length}</td>
                  <td className="text-fg-muted">{h.last_message_at ? relativeTime(h.last_message_at) : "—"}</td>
                  <td className="text-danger">{h.last_error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

function AccountTradeSyncsCard({ streams }: { streams: TradeStreamStatus[] }): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Account Trade Sync (per Account)</CardTitle>
        <StatusBadge
          tone={
            streams.length === 0
              ? "muted"
              : streams.some((s) => !s.is_running)
                ? "danger"
                : streams.some((s) => s.is_stale)
                  ? "warn"
                  : "ok"
          }
        >
          {streams.length} accounts
        </StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        {streams.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No Accounts configured" message="Add a broker Account to start a Trade Sync." />
          </div>
        ) : (
          <table className="ut-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Sync</th>
                <th>Last event</th>
                <th>Subscribers</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {streams.map((s) => (
                <tr key={s.account_id}>
                  <td className="font-medium">{s.account_label ?? s.account_id}</td>
                  <td>
                    <SyncSignal state={tradeSyncToState(s)} />
                  </td>
                  <td className="text-fg-muted">{s.last_event_at ? formatTimestamp(s.last_event_at) : "—"}</td>
                  <td className="tabular">{s.subscriber_count}</td>
                  <td className="text-fg-muted">{s.idle_note ?? s.stale_reason ?? s.last_error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

// ---------- Accounts section ----------

function AccountsSection({
  overview,
  streams,
}: {
  overview: RuntimeOverview;
  streams: { trade_streams: TradeStreamStatus[] } | undefined;
}): JSX.Element {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Accounts</CardTitle>
          <StatusBadge>{overview.broker_accounts.length}</StatusBadge>
        </CardHeader>
        <CardBody className={overview.broker_accounts.length === 0 ? "" : "grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"}>
          {overview.broker_accounts.length === 0 ? (
            <EmptyState title="No Accounts" message="Add a broker Account to begin." />
          ) : (
            overview.broker_accounts.map((a) => (
              <AccountSummaryCard
                key={a.account_id}
                account={a}
                tradeStream={streams?.trade_streams.find((s) => s.account_id === a.account_id)}
              />
            ))
          )}
        </CardBody>
      </Card>
      {overview.broker_accounts.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Daily Risk State</CardTitle>
            <TrendingDown className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
          </CardHeader>
          <CardBody className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {overview.broker_accounts.map((a) => (
              <DailyRiskStateCard key={a.account_id} accountId={a.account_id} />
            ))}
          </CardBody>
        </Card>
      )}
    </>
  );
}

function AccountSummaryCard({
  account,
  tradeStream,
}: {
  account: AccountSummary;
  tradeStream: TradeStreamStatus | undefined;
}): JSX.Element {
  const qc = useQueryClient();
  const toast = useToast();
  const [pauseOpen, setPauseOpen] = useState(false);
  const [resumeOpen, setResumeOpen] = useState(false);
  const [flattenOpen, setFlattenOpen] = useState(false);
  const idShortLabel = account.account_id.slice(0, 8);

  const pause = useMutation({
    mutationFn: (reason: string) => OperationsApi.pauseAccount(account.account_id, reason),
    onSuccess: (_data, reason) =>
      toast.show({
        severity: "warn",
        title: `Account ${idShortLabel} paused`,
        description: `Reason: ${reason}. New opens blocked on this Account.`,
      }),
    onError: (e, reason) =>
      toast.show({
        severity: "danger",
        title: `Pause failed for ${idShortLabel}`,
        description: `${reason} — ${(e as Error)?.message ?? String(e)}`,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["operations", "overview"] }),
  });
  const resume = useMutation({
    mutationFn: (reason: string) => OperationsApi.resumeAccount(account.account_id, reason),
    onSuccess: (_data, reason) =>
      toast.show({
        severity: "ok",
        title: `Account ${idShortLabel} resumed`,
        description: `Reason: ${reason}.`,
      }),
    onError: (e, reason) =>
      toast.show({
        severity: "danger",
        title: `Resume failed for ${idShortLabel}`,
        description: `${reason} — ${(e as Error)?.message ?? String(e)}`,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["operations", "overview"] }),
  });
  const flatten = useMutation({
    mutationFn: (reason: string) => OperationsApi.flattenAccount(account.account_id, reason),
    onSuccess: (_data, reason) =>
      toast.show({
        severity: "danger",
        title: `Account ${idShortLabel} flatten requested`,
        description: `Reason: ${reason}. Close orders submitted for every open position on this Account.`,
        durationMs: 12_000,
      }),
    onError: (e, reason) =>
      toast.show({
        severity: "danger",
        title: `Flatten failed for ${idShortLabel}`,
        description: `${reason} — ${(e as Error)?.message ?? String(e)}`,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["operations", "overview"] }),
  });

  const equity = account.snapshot?.equity ?? null;
  const cash = account.snapshot?.cash ?? null;
  const buyingPower = account.snapshot?.buying_power ?? null;
  const stale = account.sync_state?.is_stale === true;
  const idShort = account.account_id.slice(0, 8);
  const lastSyncAt = latestBrokerSyncTimestamp(account.sync_state);

  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <div>
          <div className="font-semibold tracking-tight">{idShort}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {account.is_killed ? (
              <StatusBadge tone="danger">Killed</StatusBadge>
            ) : account.is_paused ? (
              <StatusBadge tone="warn">Paused</StatusBadge>
            ) : (
              <StatusBadge tone="ok">Active</StatusBadge>
            )}
            {stale ? (
              <StatusBadge tone="warn">Sync Stale</StatusBadge>
            ) : (
              <StatusBadge tone="ok">Sync Fresh</StatusBadge>
            )}
            {tradeStream ? (
              <SyncSignal state={tradeSyncToState(tradeStream)} />
            ) : (
              <StatusBadge tone="muted">No Sync</StatusBadge>
            )}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 px-4 py-3 text-xs">
        <KeyValue label="Equity" value={formatCurrency(equity)} />
        <KeyValue label="Cash" value={formatCurrency(cash)} />
        <KeyValue label="Buying Power" value={formatCurrency(buyingPower)} />
        <KeyValue label="Open Orders" value={String(account.open_orders_count)} />
        <KeyValue label="Positions" value={String(account.positions_count)} />
        <KeyValue label="Last sync" value={lastSyncAt ? relativeTime(lastSyncAt) : "—"} />
      </div>
      <div className="flex flex-wrap gap-1 border-t border-border/70 px-4 py-2">
        {account.is_paused ? (
          <Button
            size="sm"
            variant="ok"
            leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setResumeOpen(true)}
          >
            Resume
          </Button>
        ) : (
          <Button
            size="sm"
            variant="secondary"
            leftIcon={<Pause className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setPauseOpen(true)}
          >
            Pause
          </Button>
        )}
        <Button size="sm" variant="danger" onClick={() => setFlattenOpen(true)}>
          Flatten
        </Button>
      </div>

      <DangerConfirm
        open={pauseOpen}
        onOpenChange={setPauseOpen}
        title="Pause this Account?"
        message={`Type ${idShort} to confirm. New opens are blocked while paused.`}
        expected={idShort}
        actionLabel="Pause Account"
        tone="danger"
        busy={pause.isPending}
        onConfirm={async (reason) => {
          await pause.mutateAsync(reason);
          setPauseOpen(false);
        }}
      />
      <DangerConfirm
        open={resumeOpen}
        onOpenChange={setResumeOpen}
        title="Resume this Account?"
        message={`Type ${idShort} to confirm.`}
        expected={idShort}
        actionLabel="Resume Account"
        tone="ok"
        busy={resume.isPending}
        onConfirm={async (reason) => {
          await resume.mutateAsync(reason);
          setResumeOpen(false);
        }}
      />
      <DangerConfirm
        open={flattenOpen}
        onOpenChange={setFlattenOpen}
        title="Flatten this Account?"
        message={`This requests close orders for every open position on Account ${idShort}. Type FLATTEN ${idShort} to confirm.`}
        expected={`FLATTEN ${idShort}`}
        actionLabel="Flatten Positions"
        tone="danger"
        busy={flatten.isPending}
        onConfirm={async (reason) => {
          await flatten.mutateAsync(reason);
          setFlattenOpen(false);
        }}
      />
    </Card>
  );
}

function KeyValue({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-fg-subtle">{label}</span>
      <span className="tabular text-fg">{value}</span>
    </div>
  );
}

// ---------- Daily Risk State card ----------

function DailyRiskStateCard({ accountId }: { accountId: string }): JSX.Element {
  const { data, isLoading, isError } = useQuery<DailyRiskStateResponse>({
    queryKey: ["operations", "daily-risk-state", accountId],
    queryFn: () => OperationsApi.dailyRiskState(accountId),
    refetchInterval: 5_000,
  });

  const idShort = accountId.slice(0, 8);
  const state = data?.state ?? null;
  const cooldown = data?.cooldown_remaining_minutes ?? null;

  const pnl = state?.realized_pnl ?? null;
  const drawdown = state?.drawdown_pct ?? null;
  const marketDay = state?.market_day ?? null;
  const updatedAt = state?.updated_at ?? null;

  const pnlTone = pnl === null ? "muted" : pnl >= 0 ? "ok" : "danger";
  const cooldownTone = cooldown !== null && cooldown > 0 ? "warn" : "ok";

  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <div>
          <div className="font-semibold tracking-tight">{idShort}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {isLoading ? (
              <StatusBadge tone="muted">Loading…</StatusBadge>
            ) : isError ? (
              <StatusBadge tone="danger">Unavailable</StatusBadge>
            ) : state === null ? (
              <StatusBadge tone="muted">No fills today</StatusBadge>
            ) : (
              <StatusBadge tone={pnlTone}>
                {pnl !== null ? (pnl >= 0 ? "+" : "") + formatCurrency(pnl) : "—"}
              </StatusBadge>
            )}
            {cooldown !== null && cooldown > 0 && (
              <StatusBadge tone="warn">
                <Clock className="mr-1 inline h-3 w-3" aria-hidden="true" />
                Cooldown {Math.ceil(cooldown)}m
              </StatusBadge>
            )}
            {cooldown !== null && cooldown <= 0 && state !== null && (
              <StatusBadge tone={cooldownTone}>Cooldown clear</StatusBadge>
            )}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 px-4 py-3 text-xs">
        <KeyValue label="Realized P&L" value={pnl !== null ? formatCurrency(pnl) : "—"} />
        <KeyValue label="Drawdown" value={drawdown !== null ? `${drawdown.toFixed(2)}%` : "—"} />
        <KeyValue label="Day" value={marketDay ?? "—"} />
        <KeyValue label="Updated" value={updatedAt ? relativeTime(updatedAt) : "—"} />
        {cooldown !== null && cooldown > 0 && (
          <KeyValue label="Cooldown remaining" value={`${Math.ceil(cooldown)}m`} />
        )}
      </div>
    </Card>
  );
}

// ---------- Deployments section ----------

function DeploymentsSection({ overview }: { overview: RuntimeOverview }): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Deployments</CardTitle>
        <StatusBadge tone={overview.blocked_deployments.length > 0 ? "danger" : "neutral"}>
          {overview.deployments.length}
        </StatusBadge>
      </CardHeader>
      <CardBody className={overview.deployments.length === 0 ? "" : "grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"}>
        {overview.deployments.length === 0 ? (
          <EmptyState title="No Deployments" message="Create a Deployment from a Strategy and Watchlist." />
        ) : (
          overview.deployments.map((d) => <DeploymentSummaryCard key={d.deployment_id} d={d} />)
        )}
      </CardBody>
    </Card>
  );
}

function DeploymentSummaryCard({ d }: { d: DeploymentSummary }): JSX.Element {
  const qc = useQueryClient();
  const toast = useToast();
  const [pauseOpen, setPauseOpen] = useState(false);
  const [resumeOpen, setResumeOpen] = useState(false);
  const [flattenOpen, setFlattenOpen] = useState(false);
  const idShortLabel = d.deployment_id.slice(0, 8);

  const pause = useMutation({
    mutationFn: (reason: string) => OperationsApi.pauseDeployment(d.deployment_id, reason),
    onSuccess: (_data, reason) =>
      toast.show({
        severity: "warn",
        title: `Deployment ${idShortLabel} paused`,
        description: `Reason: ${reason}.`,
      }),
    onError: (e, reason) =>
      toast.show({
        severity: "danger",
        title: `Pause failed for Deployment ${idShortLabel}`,
        description: `${reason} — ${(e as Error)?.message ?? String(e)}`,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["operations", "overview"] }),
  });
  const resume = useMutation({
    mutationFn: (reason: string) => OperationsApi.resumeDeployment(d.deployment_id, reason),
    onSuccess: (_data, reason) =>
      toast.show({
        severity: "ok",
        title: `Deployment ${idShortLabel} resumed`,
        description: `Reason: ${reason}.`,
      }),
    onError: (e, reason) =>
      toast.show({
        severity: "danger",
        title: `Resume failed for Deployment ${idShortLabel}`,
        description: `${reason} — ${(e as Error)?.message ?? String(e)}`,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["operations", "overview"] }),
  });
  const flatten = useMutation({
    mutationFn: (reason: string) => OperationsApi.flattenDeployment(d.deployment_id, reason),
    onSuccess: (_data, reason) =>
      toast.show({
        severity: "danger",
        title: `Deployment ${idShortLabel} flatten requested`,
        description: `Reason: ${reason}. Close orders submitted for every position owned by this Deployment.`,
        durationMs: 12_000,
      }),
    onError: (e, reason) =>
      toast.show({
        severity: "danger",
        title: `Flatten failed for Deployment ${idShortLabel}`,
        description: `${reason} — ${(e as Error)?.message ?? String(e)}`,
      }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["operations", "overview"] }),
  });

  const idShort = d.deployment_id.slice(0, 8);
  const tone: "ok" | "warn" | "danger" = d.is_running
    ? "ok"
    : d.status === "blocked" || d.status === "blocked_recovery" || d.status === "error"
      ? "danger"
      : "warn";

  return (
    <Card>
      <div className="flex items-center justify-between gap-3 px-4 pt-3">
        <div>
          <div className="font-semibold tracking-tight">{idShort}</div>
          <div className="text-xs text-fg-muted">
            strategy {d.strategy_version_id?.slice(0, 8) ?? "—"} · v{d.strategy_version ?? "—"}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <StatusBadge tone={tone}>{d.status}</StatusBadge>
          <span className="flex items-center gap-1 text-xs text-fg-muted">
            <PulseDot tone={tone} pulse={d.is_running} size="sm" />
            {d.is_running ? "running" : "idle"}
          </span>
        </div>
      </div>
      <div className="px-4 py-2 text-xs text-fg-muted">
        Account: {d.account_id ? d.account_id.slice(0, 8) : "—"}
      </div>
      <div className="flex flex-wrap gap-1 border-t border-border/70 px-4 py-2">
        {d.is_running ? (
          <Button size="sm" variant="secondary" leftIcon={<Pause className="h-3.5 w-3.5" aria-hidden="true" />} onClick={() => setPauseOpen(true)}>
            Pause
          </Button>
        ) : (
          <Button size="sm" variant="ok" leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />} onClick={() => setResumeOpen(true)}>
            Resume
          </Button>
        )}
        <Button size="sm" variant="danger" onClick={() => setFlattenOpen(true)}>
          Flatten
        </Button>
      </div>

      <DangerConfirm
        open={pauseOpen}
        onOpenChange={setPauseOpen}
        title="Pause this Deployment?"
        message={`Type ${idShort} to confirm. No new SignalPlans publish for any subscribed Account.`}
        expected={idShort}
        actionLabel="Pause Deployment"
        tone="danger"
        busy={pause.isPending}
        onConfirm={async (reason) => {
          await pause.mutateAsync(reason);
          setPauseOpen(false);
        }}
      />
      <DangerConfirm
        open={resumeOpen}
        onOpenChange={setResumeOpen}
        title="Resume this Deployment?"
        message={`Type ${idShort} to confirm.`}
        expected={idShort}
        actionLabel="Resume Deployment"
        tone="ok"
        busy={resume.isPending}
        onConfirm={async (reason) => {
          await resume.mutateAsync(reason);
          setResumeOpen(false);
        }}
      />
      <DangerConfirm
        open={flattenOpen}
        onOpenChange={setFlattenOpen}
        title="Flatten this Deployment?"
        message={`This requests close orders for every Position originated by Deployment ${idShort}. Type FLATTEN ${idShort} to confirm.`}
        expected={`FLATTEN ${idShort}`}
        actionLabel="Flatten Deployment"
        tone="danger"
        busy={flatten.isPending}
        onConfirm={async (reason) => {
          await flatten.mutateAsync(reason);
          setFlattenOpen(false);
        }}
      />
    </Card>
  );
}

// ---------- Broker-order trace ----------

function BrokerOrderTraceCard(): JSX.Element {
  const [draft, setDraft] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);

  const lookup = useQuery({
    queryKey: ["operations", "broker-order-trace", submitted],
    queryFn: () => OperationsApi.lookupBrokerOrder(submitted!),
    enabled: Boolean(submitted),
    retry: false,
  });

  function handleSubmit(): void {
    const id = draft.trim();
    if (id) setSubmitted(id);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Search className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
            Trace broker order
          </span>
        </CardTitle>
        <span className="text-[11px] text-fg-subtle">
          paste an Alpaca broker order id
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-64 flex-1">
            <TextField
              label="Broker order id"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="alp-1234abcd-..."
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSubmit();
              }}
            />
          </div>
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Search className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={handleSubmit}
            disabled={!draft.trim()}
            loading={lookup.isFetching && Boolean(submitted)}
          >
            Trace
          </Button>
          {submitted ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setSubmitted(null);
                setDraft("");
              }}
            >
              Clear
            </Button>
          ) : null}
        </div>

        {submitted == null ? (
          <span className="block text-xs text-fg-subtle">
            Result will resolve to the internal order, broker mapping, fills, and trade summary.
          </span>
        ) : lookup.isLoading ? (
          <LoadingState title={`Looking up ${submitted}`} />
        ) : lookup.isError ? (
          isAwaiting(lookup.error) ? (
            <Banner
              severity="warning"
              title="No match"
              message={
                <span>
                  No internal order is mapped to broker order
                  <span className="ml-1 font-mono">{submitted}</span>. Check the id against the
                  Alpaca dashboard, or confirm BrokerSync has reconciled this Account.
                </span>
              }
            />
          ) : (
            <AwaitingApiOrError
              title="broker-order trace"
              endpoint={`GET /api/v1/operations/broker-orders/${submitted}`}
              awaitingMessage="The broker-order trace endpoint is not registered yet."
              error={lookup.error}
              onRetry={() => lookup.refetch()}
            />
          )
        ) : lookup.data ? (
          <BrokerOrderTraceResult detail={lookup.data} />
        ) : null}
      </CardBody>
    </Card>
  );
}

function BrokerOrderTraceResult({
  detail,
}: {
  detail: import("@/api/schemas/operations").OrderDetail;
}): JSX.Element {
  const order = detail.internal_order;
  return (
    <div className="rounded border border-border/70 bg-bg-inset p-3 text-xs">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone="info">{order.symbol}</StatusBadge>
        <StatusBadge tone="neutral">{order.side}</StatusBadge>
        <StatusBadge tone={statusTone(order.status)}>{order.status}</StatusBadge>
        <StatusBadge tone="muted">broker · {detail.broker_status}</StatusBadge>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-2 md:grid-cols-3">
        <KeyValue label="Internal order id" value={<span className="font-mono">{order.order_id.slice(0, 12)}…</span>} />
        <KeyValue label="Account" value={<span className="font-mono">{detail.broker_account_id.slice(0, 12)}…</span>} />
        <KeyValue
          label="Deployment"
          value={
            detail.deployment_id ? (
              <span className="font-mono">{detail.deployment_id.slice(0, 12)}…</span>
            ) : (
              <span className="text-fg-subtle">manual</span>
            )
          }
        />
        <KeyValue
          label="Strategy version"
          value={
            detail.strategy_version_id ? (
              <span className="font-mono">{detail.strategy_version_id.slice(0, 12)}…</span>
            ) : (
              <span className="text-fg-subtle">—</span>
            )
          }
        />
        <KeyValue label="Quantity" value={`${order.filled_quantity} / ${order.quantity}`} />
        <KeyValue
          label="Last broker sync"
          value={
            detail.broker_sync_timestamp ? relativeTime(detail.broker_sync_timestamp) : "—"
          }
        />
      </div>
      <div className="mt-2 text-[11px] text-fg-subtle">
        Fills: {detail.fills.length}
        {detail.broker_order_id ? (
          <span className="ml-2">
            broker order id: <span className="font-mono">{detail.broker_order_id}</span>
          </span>
        ) : null}
      </div>
    </div>
  );
}

function statusTone(status: string): "ok" | "warn" | "danger" | "info" | "muted" {
  const s = status.toLowerCase();
  if (s === "filled") return "ok";
  if (s === "rejected" || s === "canceled") return "danger";
  if (s === "partially_filled" || s === "submitted" || s === "accepted") return "info";
  return "muted";
}

// ---------- Recent decisions ----------

function friendlyRuleText(decision: GovernorDecision): string {
  const ruleId = decision.rule_id ?? "";
  if (ruleId === "account_missing_risk_plan_for_horizon") {
    const horizon = decision.projected_state?.deployment_risk_horizon as string | undefined;
    const label =
      horizon != null && horizon in TRADING_HORIZON_LABELS
        ? TRADING_HORIZON_LABELS[horizon as keyof typeof TRADING_HORIZON_LABELS]
        : horizon ?? "unknown";
    return `No RiskPlan mapped for the deployment's ${label} horizon`;
  }
  return ruleId;
}

function resolvedRiskPlanLabel(decision: GovernorDecision): string | null {
  const id = decision.projected_state?.resolved_risk_plan_id as string | undefined;
  const name = decision.projected_state?.resolved_risk_plan_name as string | undefined;
  if (name) return name;
  if (id) return id.slice(0, 8) + "...";
  return null;
}

function traceReasonText(decision: GovernorDecisionTrace): string {
  return decision.reasons[0] ?? decision.violations[0] ?? decision.status;
}

function traceRuleText(decision: GovernorDecisionTrace): string {
  return decision.violations[0] ?? decision.reasons[0] ?? decision.status;
}

function traceRiskPlanLabel(decision: GovernorDecisionTrace): string | null {
  const projected = (decision.projected_state ?? {}) as Record<string, unknown>;
  const name = projected.resolved_risk_plan_name as string | undefined;
  const id = projected.resolved_risk_plan_id as string | undefined;
  if (name) return name;
  if (id) return id.slice(0, 8) + "...";
  return null;
}

function RecentDecisionsCard({ overview }: { overview: RuntimeOverview }): JSX.Element {
  const timeline = useQuery({
    queryKey: ["operations", "governor-decisions", "recent"],
    queryFn: () => TimelinesApi.governorDecisions({ limit: 10 }),
    refetchInterval: 5_000,
    retry: false,
  });
  const traceList = timeline.data?.governor_decisions ?? [];
  const legacyList = overview.latest_governor_decisions;
  const listLength = traceList.length > 0 ? traceList.length : legacyList.length;
  const hasRejected = traceList.length > 0
    ? traceList.some((d) => !d.approved)
    : legacyList.some((d) => !d.approved);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent Governor decisions</CardTitle>
        <StatusBadge tone={hasRejected ? "warn" : "ok"}>{listLength}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        {listLength === 0 ? (
          <div className="p-4">
            <EmptyState title="No recent decisions" message="Governor decisions will appear here as Deployments emit SignalPlans." />
          </div>
        ) : traceList.length > 0 ? (
          <table className="ut-table">
            <thead>
              <tr>
                <th>Approved</th>
                <th>Reason</th>
                <th>Rule</th>
                <th>RiskPlan</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {traceList.map((d) => {
                const riskPlanLabel = traceRiskPlanLabel(d);
                return (
                  <tr key={d.governor_decision_id}>
                    <td>
                      <StatusBadge tone={d.approved ? "ok" : "danger"}>
                        {d.approved ? "approved" : "rejected"}
                      </StatusBadge>
                    </td>
                    <td className="font-medium">{traceReasonText(d)}</td>
                    <td className="text-fg-muted">{traceRuleText(d)}</td>
                    <td>
                      {riskPlanLabel ? (
                        <StatusBadge tone="neutral" size="sm">
                          {riskPlanLabel}
                        </StatusBadge>
                      ) : (
                        <span className="text-fg-subtle">-</span>
                      )}
                    </td>
                    <td className="text-fg-muted">{relativeTime(d.evaluated_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <table className="ut-table">
            <thead>
              <tr>
                <th>Approved</th>
                <th>Reason</th>
                <th>Rule</th>
                <th>RiskPlan</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {legacyList.map((d, i) => {
                const riskPlanLabel = resolvedRiskPlanLabel(d);
                return (
                  <tr key={i}>
                    <td>
                      <StatusBadge tone={d.approved ? "ok" : "danger"}>
                        {d.approved ? "approved" : "rejected"}
                      </StatusBadge>
                    </td>
                    <td className="font-medium">{d.reason ?? ""}</td>
                    <td className="text-fg-muted">{friendlyRuleText(d)}</td>
                    <td>
                      {riskPlanLabel ? (
                        <StatusBadge tone="neutral" size="sm">
                          {riskPlanLabel}
                        </StatusBadge>
                      ) : (
                        <span className="text-fg-subtle">—</span>
                      )}
                    </td>
                    <td className="text-fg-muted">{d.decided_at ? relativeTime(d.decided_at) : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

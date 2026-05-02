import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, Activity, Play } from "lucide-react";
import { ApiError } from "@/api/client";
import { SimLabApi } from "@/api/researchRuns";
import { StrategiesApi } from "@/api/strategies";
import { StrategyControlsApi } from "@/api/strategyControls";
import { ExecutionPlansApi } from "@/api/executionPlans";
import {
  SimLabStreamMessageSchema,
  type SimLabBatchRunRequest,
  type SimLabStreamMessage,
  type SimulationRun,
} from "@/api/schemas/researchRuns";
import type { Strategy, StrategyVersionRecord } from "@/api/schemas/strategies";
import { useWS } from "@/api/ws";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
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
import { PulseDot } from "@/components/ui/PulseDot";
import {
  SimLabReplayChart,
  type SimLabReplayBar,
  type SimLabReplayEquityPoint,
  type SimLabReplayFill,
} from "@/components/charts/SimLabReplayChart";
import { LoadingState } from "@/components/empty/LoadingState";
import { EmptyState } from "@/components/empty/EmptyState";
import { StaleState } from "@/components/empty/StaleState";
import { AwaitingApiOrError } from "@/components/empty/AwaitingApi";
import { Select } from "@/components/ui/Select";
import { RiskPlanPicker } from "@/components/risk_plans/RiskPlanPicker";
import { PageHeader } from "./PageHeader";
import { formatCurrency, formatTimestamp, formatQuantity, relativeTime } from "@/lib/format";

/**
 * Sim Lab — first-class operator route (gate C6).
 *
 * Lists durable simulation sessions and lets the operator select two
 * for side-by-side comparison. Pause / step / resume controls and the
 * streaming WebSocket consumer are scaffolded in `awaiting` panels
 * pinned to the matching backend endpoints (C2 + C5) so they go live
 * the moment Operation Turtle Shell ships them.
 *
 * Doctrine: Sim Lab consumes the same Strategy → Deployment →
 * SignalPlan → RiskResolver → Governor → OrderManager spine as live.
 * No alternate runtime; no broker submission; per `RESEARCH_CREATE_RUN_API_HANDOFF.md`.
 */
export function SimLab(): JSX.Element {
  const list = useQuery({
    queryKey: ["sim-lab", "sessions"],
    queryFn: () => SimLabApi.listSessions(),
    refetchInterval: 15_000,
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

  const sessions = list.data?.sessions ?? [];

  const [leftId, setLeftId] = useState<string | null>(null);
  const [rightId, setRightId] = useState<string | null>(null);
  const left = sessions.find((s) => s.run_id === leftId) ?? null;
  const right = sessions.find((s) => s.run_id === rightId) ?? null;
  const [batchOpen, setBatchOpen] = useState(false);
  const [streamRequest, setStreamRequest] = useState<SimLabBatchRunRequest | null>(null);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Sim Lab"
        subtitle="Historical replay sessions through the production runtime spine. Same Strategy → Deployment → SignalPlan → RiskResolver → Governor → OrderManager as live — no real broker submission."
        explainSlug="sim-lab"
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setBatchOpen(true)}
            disabled={(strategies.data?.strategies.length ?? 0) === 0}
          >
            Run batch sim
          </Button>
        }
      />

      <Banner
        severity="info"
        title="What you're seeing"
        message={
          <span>
            Sim Lab replays <strong>real historical bars</strong> from your configured data source
            (Yahoo by default) through the same SignalPlan → RiskResolver → simulated-broker spine
            the live runtime uses — no real broker submission. Each chart shows OHLC candles for
            one symbol; entry / exit markers appear as fills land; the equity overlay tracks
            simulated PnL. <em>Not sample data.</em> Bar-count is bounded by the form so a long
            window doesn't tie up the stream — bump it if you want more replayed history.
          </span>
        }
      />

      {streamRequest ? (
        <SimLabStreamView
          request={streamRequest}
          onClose={() => setStreamRequest(null)}
        />
      ) : null}

      {list.isLoading ? <LoadingState title="Loading simulation sessions" /> : null}
      {list.isError ? (
        <AwaitingApiOrError
          title="Simulation sessions"
          endpoint="GET /api/v1/sim-lab/sessions"
          awaitingMessage="The Sim Lab sessions endpoint is not registered. Read-only catalog flips on automatically when Codex's evidence path lands."
          error={list.error}
          onRetry={() => list.refetch()}
        />
      ) : null}

      {list.data && sessions.length === 0 ? (
        <EmptyState
          title="No simulation sessions yet"
          message="Sessions persist as research evidence. Open a strategy version, run a Sim Lab session, then return here for replay + comparison."
        />
      ) : null}

      {sessions.length > 0 ? (
        <SessionsTable sessions={sessions} directory={directory} />
      ) : null}

      <CompareSelector
        sessions={sessions}
        directory={directory}
        leftId={leftId}
        rightId={rightId}
        onLeftChange={setLeftId}
        onRightChange={setRightId}
      />

      {left || right ? (
        <CompareGrid left={left} right={right} directory={directory} />
      ) : null}

      <BatchRunDrawer
        open={batchOpen}
        onOpenChange={setBatchOpen}
        strategies={strategies.data?.strategies ?? []}
        onStreamRequest={(req) => {
          setStreamRequest(req);
          setBatchOpen(false);
        }}
      />
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

function SessionsTable({
  sessions,
  directory,
}: {
  sessions: SimulationRun[];
  directory: StrategyDirectory;
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Sessions</CardTitle>
        <StatusBadge>{sessions.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        <table className="ut-table">
          <thead>
            <tr>
              <th>Created</th>
              <th>Scenario</th>
              <th>Strategy</th>
              <th>Window</th>
              <th>SignalPlans</th>
              <th>Sim orders</th>
              <th>Sim fills</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.run_id}>
                <td className="text-fg-muted" title={s.created_at}>
                  {relativeTime(s.created_at)}
                </td>
                <td className="font-medium">{s.scenario_name}</td>
                <td>{directory.name(s.strategy_id)}</td>
                <td className="text-xs text-fg-muted">
                  {dateOnly(s.start)} → {dateOnly(s.end)}
                </td>
                <td className="tabular text-fg-muted">{formatQuantity(s.signal_plan_count)}</td>
                <td className="tabular text-fg-muted">{formatQuantity(s.simulated_order_count)}</td>
                <td className="tabular text-fg-muted">{formatQuantity(s.simulated_fill_count)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

function CompareSelector({
  sessions,
  directory,
  leftId,
  rightId,
  onLeftChange,
  onRightChange,
}: {
  sessions: SimulationRun[];
  directory: StrategyDirectory;
  leftId: string | null;
  rightId: string | null;
  onLeftChange: (id: string | null) => void;
  onRightChange: (id: string | null) => void;
}): JSX.Element {
  const options = useMemo(() => {
    return sessions.map((s) => ({
      value: s.run_id,
      label: `${s.scenario_name} · ${directory.name(s.strategy_id)} · ${dateOnly(s.start)}`,
    }));
  }, [sessions, directory]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Side-by-side compare</CardTitle>
        <span className="flex items-center gap-1.5 text-[11px] text-fg-muted">
          <ArrowLeftRight className="h-3.5 w-3.5" aria-hidden="true" />
          Pick two sessions
        </span>
      </CardHeader>
      <CardBody className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <Select
          label="Left session"
          value={leftId ?? ""}
          onChange={(e) => onLeftChange(e.target.value || null)}
          disabled={sessions.length === 0}
        >
          <option value="">— none —</option>
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.value === rightId}>
              {o.label}
            </option>
          ))}
        </Select>
        <Select
          label="Right session"
          value={rightId ?? ""}
          onChange={(e) => onRightChange(e.target.value || null)}
          disabled={sessions.length === 0}
        >
          <option value="">— none —</option>
          {options.map((o) => (
            <option key={o.value} value={o.value} disabled={o.value === leftId}>
              {o.label}
            </option>
          ))}
        </Select>
      </CardBody>
    </Card>
  );
}

function CompareGrid({
  left,
  right,
  directory,
}: {
  left: SimulationRun | null;
  right: SimulationRun | null;
  directory: StrategyDirectory;
}): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <CompareCard side="Left" run={left} directory={directory} other={right} />
      <CompareCard side="Right" run={right} directory={directory} other={left} />
    </div>
  );
}

function CompareCard({
  side,
  run,
  other,
  directory,
}: {
  side: "Left" | "Right";
  run: SimulationRun | null;
  other: SimulationRun | null;
  directory: StrategyDirectory;
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{side}</CardTitle>
        {run ? (
          <span className="text-xs text-fg-muted" title={run.run_id}>
            session {run.run_id.slice(0, 8)}
          </span>
        ) : (
          <StatusBadge tone="muted">none</StatusBadge>
        )}
      </CardHeader>
      <CardBody className="space-y-2 text-xs">
        {!run ? (
          <span className="text-fg-subtle">Pick a session to populate this side.</span>
        ) : (
          <>
            <CompareRow
              label="Scenario"
              value={run.scenario_name}
              compare={other?.scenario_name}
            />
            <CompareRow
              label="Strategy"
              value={directory.name(run.strategy_id)}
              compare={other ? directory.name(other.strategy_id) : undefined}
            />
            <CompareRow
              label="Window"
              value={`${dateOnly(run.start)} → ${dateOnly(run.end)}`}
              compare={other ? `${dateOnly(other.start)} → ${dateOnly(other.end)}` : undefined}
            />
            <CompareNumberRow
              label="SignalPlans"
              value={run.signal_plan_count}
              compare={other?.signal_plan_count}
            />
            <CompareNumberRow
              label="Sim orders"
              value={run.simulated_order_count}
              compare={other?.simulated_order_count}
            />
            <CompareNumberRow
              label="Sim fills"
              value={run.simulated_fill_count}
              compare={other?.simulated_fill_count}
            />
            <CompareRow
              label="Created"
              value={formatTimestamp(run.created_at)}
              compare={other ? formatTimestamp(other.created_at) : undefined}
            />
            <MetricsCompare run={run} other={other} />
          </>
        )}
      </CardBody>
    </Card>
  );
}

function CompareRow({
  label,
  value,
  compare,
}: {
  label: string;
  value: React.ReactNode;
  compare?: React.ReactNode;
}): JSX.Element {
  const differs = compare !== undefined && compare !== value;
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-fg-muted">{label}</span>
      <span className={differs ? "text-warn" : ""}>{value}</span>
    </div>
  );
}

function CompareNumberRow({
  label,
  value,
  compare,
}: {
  label: string;
  value: number;
  compare?: number;
}): JSX.Element {
  const delta = compare == null ? null : value - compare;
  const tone = delta == null || delta === 0 ? "" : delta > 0 ? "text-ok" : "text-danger";
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-fg-muted">{label}</span>
      <span className={`tabular ${tone}`}>
        {formatQuantity(value)}
        {delta != null && delta !== 0 ? (
          <span className="ml-1 text-[11px] text-fg-subtle">
            ({delta > 0 ? "+" : ""}
            {formatQuantity(delta)})
          </span>
        ) : null}
      </span>
    </div>
  );
}

function MetricsCompare({
  run,
  other,
}: {
  run: SimulationRun;
  other: SimulationRun | null;
}): JSX.Element {
  const keys = collectMetricKeys(run.metrics, other?.metrics ?? {});
  if (keys.length === 0) {
    return (
      <div className="border-t border-border/70 pt-2 text-fg-subtle">No metrics reported.</div>
    );
  }
  return (
    <div className="border-t border-border/70 pt-2 space-y-1">
      <div className="text-fg-muted">Metrics</div>
      {keys.map((k) => (
        <div key={k} className="flex items-baseline justify-between gap-3">
          <span className="text-fg-subtle">{k}</span>
          <span className="tabular">
            {formatMetric(run.metrics[k])}
            {other ? (
              <span className="ml-2 text-[11px] text-fg-subtle">
                vs {formatMetric(other.metrics[k])}
              </span>
            ) : null}
          </span>
        </div>
      ))}
    </div>
  );
}

function collectMetricKeys(a: Record<string, unknown>, b: Record<string, unknown>): string[] {
  const keys = new Set<string>();
  for (const k of Object.keys(a)) keys.add(k);
  for (const k of Object.keys(b)) keys.add(k);
  return [...keys].sort();
}

function formatMetric(v: unknown): string {
  if (typeof v === "number" && Number.isFinite(v)) {
    if (Number.isInteger(v)) return v.toString();
    return v.toFixed(3);
  }
  if (v == null) return "—";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string") return v;
  return JSON.stringify(v).slice(0, 32);
}

function dateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toISOString().slice(0, 10);
}

// ---------- Batch run drawer ----------

interface BatchForm {
  strategyId: string;
  versionId: string;
  strategyControlsVersionId: string;
  executionPlanVersionId: string;
  riskPlanVersionId: string;
  scenarioName: string;
  universe: string;
  timeframe: string;
  start: string;
  end: string;
  initialCash: string;
  barCount: string;
}

function defaultBatchForm(): BatchForm {
  const today = new Date();
  const startDate = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);
  return {
    strategyId: "",
    versionId: "",
    strategyControlsVersionId: "",
    executionPlanVersionId: "",
    riskPlanVersionId: "",
    scenarioName: "",
    universe: "SPY",
    timeframe: "5m",
    start: startDate.toISOString(),
    end: today.toISOString(),
    initialCash: "100000",
    // Replay length. The backend caps the stream at this many bars before
    // emitting `session_completed`. 12 was a debug default; 500 gives ~40h
    // of 5m data — enough that the chart renders something useful.
    barCount: "500",
  };
}

function BatchRunDrawer({
  open,
  onOpenChange,
  strategies,
  onStreamRequest,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  strategies: Strategy[];
  onStreamRequest: (req: SimLabBatchRunRequest) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const [form, setForm] = useState<BatchForm>(() => defaultBatchForm());
  const [error, setError] = useState<string | null>(null);

  // Pull versions for the selected strategy lazily. Sim Lab is a verification
  // surface — drafts and frozen versions are both valid. Freeze is the
  // commit-to-deploy step, not a research gate.
  const versions = useQuery({
    queryKey: ["strategies", "versions", form.strategyId],
    queryFn: () => StrategiesApi.listVersions(form.strategyId),
    enabled: Boolean(form.strategyId),
  });
  const strategyControls = useQuery({
    queryKey: ["strategy-controls", "list"],
    queryFn: () => StrategyControlsApi.list(),
    enabled: open,
  });
  const executionPlans = useQuery({
    queryKey: ["execution-plans", "list"],
    queryFn: () => ExecutionPlansApi.list(),
    enabled: open,
  });

  const allVersions: StrategyVersionRecord[] = useMemo(() => {
    return [...(versions.data ?? [])].sort((a, b) => a.version - b.version);
  }, [versions.data]);

  useEffect(() => {
    if (!form.strategyControlsVersionId && strategyControls.data?.libraries?.length) {
      const preferred =
        strategyControls.data.libraries.find((library) => library.is_default) ??
        strategyControls.data.libraries[0];
      setForm((prev) => ({ ...prev, strategyControlsVersionId: preferred.head_version_id ?? "" }));
    }
  }, [form.strategyControlsVersionId, strategyControls.data]);

  useEffect(() => {
    if (!form.executionPlanVersionId && executionPlans.data?.libraries?.length) {
      const preferred =
        executionPlans.data.libraries.find((library) => library.is_default) ??
        executionPlans.data.libraries[0];
      setForm((prev) => ({ ...prev, executionPlanVersionId: preferred.head_version_id ?? "" }));
    }
  }, [form.executionPlanVersionId, executionPlans.data]);

  function reset(): void {
    setForm(defaultBatchForm());
    setError(null);
  }

  function buildRequest(): SimLabBatchRunRequest {
    const universe = form.universe
      .split(/[,\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    if (universe.length === 0) throw new Error("Universe must contain at least one symbol.");
    const initialCash = Number.parseFloat(form.initialCash);
    if (!Number.isFinite(initialCash) || initialCash <= 0) {
      throw new Error("Initial cash must be a positive number.");
    }
    const barCount = Number.parseInt(form.barCount, 10);
    if (!Number.isFinite(barCount) || barCount < 2) {
      throw new Error("Bar count must be at least 2.");
    }
    if (!form.strategyId) throw new Error("Pick a strategy.");
    if (!form.versionId) throw new Error("Pick a version.");
    if (!form.strategyControlsVersionId) throw new Error("Pick a Strategy Control.");
    if (!form.executionPlanVersionId) throw new Error("Pick an Execution Plan.");
    if (!form.riskPlanVersionId) throw new Error("Pick a Risk Plan.");
    if (!form.scenarioName.trim()) throw new Error("Scenario name is required.");
    return {
      strategy_id: form.strategyId,
      strategy_version_id: form.versionId,
      strategy_controls_version_id: form.strategyControlsVersionId,
      execution_plan_version_id: form.executionPlanVersionId,
      risk_plan_version_id: form.riskPlanVersionId,
      scenario_name: form.scenarioName.trim(),
      universe,
      timeframe: form.timeframe.trim() || "5m",
      start: form.start,
      end: form.end,
      initial_cash: initialCash,
      bar_count: barCount,
    };
  }

  const create = useMutation({
    mutationFn: () => SimLabApi.batchRun(buildRequest()),
    onSuccess: () => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["sim-lab", "sessions"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : (e as Error).message),
  });

  function handleRun(): void {
    setError(null);
    try {
      create.mutate();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function handleStream(): void {
    setError(null);
    try {
      const req = buildRequest();
      reset();
      onStreamRequest(req);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DrawerContent className="max-w-xl">
        <DrawerHeader>
          <DrawerTitle>Run batch sim</DrawerTitle>
          <DrawerDescription>
            Deterministic fixed-window historical replay through the production runtime spine.
            Persists a `SimulationRunEvidence` and surfaces in the sessions list above on success.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Cannot run sim" message={error} /> : null}
          <Select
            label="Strategy"
            value={form.strategyId}
            onChange={(e) => setForm({ ...form, strategyId: e.target.value, versionId: "" })}
          >
            <option value="">— pick —</option>
            {strategies.map((s) => (
              <option key={s.strategy_id} value={s.strategy_id}>
                {s.name}
              </option>
            ))}
          </Select>
          <Select
            label="Strategy version"
            value={form.versionId}
            onChange={(e) => setForm({ ...form, versionId: e.target.value })}
            disabled={!form.strategyId || allVersions.length === 0}
            hint={
              form.strategyId && allVersions.length === 0
                ? "Strategy has no versions yet; add one first."
                : "Drafts are fine for verification — freeze is the commit-to-deploy step."
            }
          >
            <option value="">— pick —</option>
            {allVersions.map((v) => (
              <option key={v.strategy_version_id} value={v.strategy_version_id}>
                v{v.version}
                {v.payload.name ? ` · ${v.payload.name}` : ""}
                {` · ${v.status}`}
              </option>
            ))}
          </Select>
          <Select
            label="Strategy Control"
            value={form.strategyControlsVersionId}
            onChange={(e) => setForm({ ...form, strategyControlsVersionId: e.target.value })}
            hint="Pins timeframe, sessions, and Strategy Control rules for this replay snapshot."
          >
            <option value="">-- pick --</option>
            {(strategyControls.data?.libraries ?? []).map((library) => (
              <option
                key={library.strategy_controls_id}
                value={library.head_version_id ?? ""}
                disabled={!library.head_version_id}
              >
                {library.name} v{library.head_version_number}
                {library.is_default ? " · default" : ""}
              </option>
            ))}
          </Select>
          <Select
            label="Execution Plan"
            value={form.executionPlanVersionId}
            onChange={(e) => setForm({ ...form, executionPlanVersionId: e.target.value })}
            hint="Pins the exact simulated order and bracket behavior for this replay."
          >
            <option value="">-- pick --</option>
            {(executionPlans.data?.libraries ?? []).map((library) => (
              <option
                key={library.execution_plan_id}
                value={library.head_version_id ?? ""}
                disabled={!library.head_version_id}
              >
                {library.name} v{library.head_version_number}
                {library.is_default ? " · default" : ""}
              </option>
            ))}
          </Select>
          <RiskPlanPicker
            label="Risk Plan"
            required
            value={form.riskPlanVersionId || null}
            onChange={(next) => setForm({ ...form, riskPlanVersionId: next ?? "" })}
            hint="Required. Sim Lab uses it through RiskResolver exactly like a deployment-like run."
          />
          <div className="rounded border border-border bg-bg-subtle px-3 py-2 text-xs text-fg-muted">
            <div className="mb-1 flex flex-wrap gap-1.5">
              <StatusBadge tone="muted">Data source: simulated</StatusBadge>
              <StatusBadge tone="muted">Adjustment: raw</StatusBadge>
            </div>
            <span>
              Sim Lab uses deterministic generated bars for execution-path verification. Use Chart
              Lab, Backtest, Optimization, or Walk-Forward when provider data policy must vary.
            </span>
          </div>
          <TextField
            label="Scenario name"
            value={form.scenarioName}
            onChange={(e) => setForm({ ...form, scenarioName: e.target.value })}
            placeholder="Bull regime soak"
          />
          <TextField
            label="Universe (comma or space separated)"
            value={form.universe}
            onChange={(e) => setForm({ ...form, universe: e.target.value })}
            placeholder="SPY, QQQ"
          />
          <div className="grid grid-cols-2 gap-2">
            <TextField
              label="Timeframe"
              value={form.timeframe}
              onChange={(e) => setForm({ ...form, timeframe: e.target.value })}
              placeholder="5m"
            />
            <TextField
              label="Bar count (min 2)"
              value={form.barCount}
              onChange={(e) => setForm({ ...form, barCount: e.target.value })}
              inputMode="numeric"
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <TextField
              label="Start (ISO)"
              value={form.start}
              onChange={(e) => setForm({ ...form, start: e.target.value })}
              hint="e.g. 2026-03-01T13:30:00Z"
            />
            <TextField
              label="End (ISO)"
              value={form.end}
              onChange={(e) => setForm({ ...form, end: e.target.value })}
            />
          </div>
          <TextField
            label="Initial cash (USD)"
            value={form.initialCash}
            onChange={(e) => setForm({ ...form, initialCash: e.target.value })}
            inputMode="numeric"
          />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleStream}
            leftIcon={<Activity className="h-3.5 w-3.5" aria-hidden="true" />}
          >
            Stream
          </Button>
          <Button
            variant="primary"
            size="sm"
            loading={create.isPending}
            onClick={handleRun}
            leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
          >
            Run
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

// ---------- Stream view ----------

interface StreamState {
  barsBySymbol: Map<string, SimLabReplayBar[]>;
  fillsBySymbol: Map<string, SimLabReplayFill[]>;
  equityCurve: SimLabReplayEquityPoint[];
  signalPlans: number;
  positionsBySymbol: Map<string, SimLabStreamMessage>;
  lastEquity: number | null;
  sessionStarted: SimLabStreamMessage | null;
  sessionCompleted: SimLabStreamMessage | null;
}

function emptyStreamState(): StreamState {
  return {
    barsBySymbol: new Map(),
    fillsBySymbol: new Map(),
    equityCurve: [],
    signalPlans: 0,
    positionsBySymbol: new Map(),
    lastEquity: null,
    sessionStarted: null,
    sessionCompleted: null,
  };
}

function appendToSymbolMap<T>(
  prev: Map<string, T[]>,
  symbol: string,
  item: T,
): Map<string, T[]> {
  const next = new Map(prev);
  const existing = next.get(symbol) ?? [];
  next.set(symbol, [...existing, item]);
  return next;
}

function totalCount<T>(map: Map<string, T[]>): number {
  let n = 0;
  for (const arr of map.values()) n += arr.length;
  return n;
}

function SimLabStreamView({
  request,
  onClose,
}: {
  request: SimLabBatchRunRequest;
  onClose: () => void;
}): JSX.Element {
  const [state, setState] = useState<StreamState>(() => emptyStreamState());

  // Reset accumulated state whenever the operator opens a new stream session.
  useEffect(() => {
    setState(emptyStreamState());
  }, [
    request.strategy_id,
    request.strategy_version_id,
    request.scenario_name,
    request.universe.join(","),
    request.start,
    request.end,
  ]);

  const path = SimLabApi.streamPath(request);
  const ws = useWS({
    schema: SimLabStreamMessageSchema,
    path,
    enabled: true,
    onMessage: (msg) => {
      setState((prev) => applyStreamMessage(prev, msg));
    },
  });

  const completed = state.sessionCompleted != null;
  // Suppress the close-handshake warning once the deterministic stream has
  // ack'd `session_completed`; otherwise the `useWS` reconnect/close handler
  // emits a transient `websocket_error` that misleadingly survives a
  // successful run.
  const visibleError = completed ? null : ws.lastError;
  const tone = streamTone({ status: ws.status, lastError: visibleError, completed, lastEventAt: ws.lastEventAt });
  const pulse = !completed && (ws.status === "open" || ws.status === "connecting");

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <PulseDot tone={tone} pulse={pulse} size="md" label="sim lab stream" />
            Streaming · {request.scenario_name}
          </span>
        </CardTitle>
        <span className="flex items-center gap-2">
          <StatusBadge tone={tone === "ok" ? "ok" : tone === "danger" ? "danger" : "info"}>
            {completed ? "completed" : ws.status}
          </StatusBadge>
          <Button size="sm" variant="ghost" onClick={() => ws.close()}>
            Close stream
          </Button>
          <Button size="sm" variant="secondary" onClick={onClose}>
            Hide
          </Button>
        </span>
      </CardHeader>
      <CardBody className="space-y-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px]">
          <KpiInline label="Universe" value={request.universe.join(", ")} />
          <KpiInline
            label="Window"
            value={`${dateOnly(request.start)} → ${dateOnly(request.end)}`}
          />
          <KpiInline label="Bars" value={formatQuantity(totalCount(state.barsBySymbol))} />
          <KpiInline label="SignalPlans" value={formatQuantity(state.signalPlans)} />
          <KpiInline label="Fills" value={formatQuantity(totalCount(state.fillsBySymbol))} />
          <KpiInline
            label="Last equity"
            value={state.lastEquity != null ? formatCurrency(state.lastEquity) : "—"}
          />
          <KpiInline
            label="Last update"
            value={ws.lastEventAt ? relativeTime(ws.lastEventAt.toISOString()) : "—"}
          />
        </div>

        {visibleError ? (
          <Banner severity="danger" title="Stream warning" message={visibleError} />
        ) : null}

        {!completed && ws.status !== "open" && totalCount(state.barsBySymbol) > 0 ? (
          <StaleState
            title="Replay stream is not connected"
            message="Showing the bars and fills received so far. Replay will resume when the stream reconnects."
            detail={
              ws.lastEventAt
                ? `last update ${relativeTime(ws.lastEventAt.toISOString())}`
                : undefined
            }
          />
        ) : null}

        <ReplayCharts
          universe={request.universe}
          timeframe={request.timeframe ?? "5m"}
          start={request.start}
          end={request.end}
          barsBySymbol={state.barsBySymbol}
          fillsBySymbol={state.fillsBySymbol}
          equityCurve={state.equityCurve}
        />

        {completed && state.sessionCompleted ? (
          <SessionSummary message={state.sessionCompleted} />
        ) : null}
      </CardBody>
    </Card>
  );
}

function KpiInline({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <span>
      <span className="text-fg-subtle">{label}:</span>{" "}
      <span className="tabular text-fg">{value}</span>
    </span>
  );
}

function ReplayCharts({
  universe,
  timeframe,
  start,
  end,
  barsBySymbol,
  fillsBySymbol,
  equityCurve,
}: {
  universe: string[];
  timeframe: string;
  start: string;
  end: string;
  barsBySymbol: Map<string, SimLabReplayBar[]>;
  fillsBySymbol: Map<string, SimLabReplayFill[]>;
  equityCurve: SimLabReplayEquityPoint[];
}): JSX.Element {
  if (universe.length === 0) {
    return (
      <div className="rounded border border-dashed border-border/70 bg-bg-inset p-3 text-[11px] text-fg-subtle">
        no symbols in universe.
      </div>
    );
  }
  return (
    <div
      className={
        universe.length === 1
          ? "grid grid-cols-1"
          : "grid grid-cols-1 gap-3 xl:grid-cols-2"
      }
    >
      {universe.map((rawSymbol, idx) => {
        const symbol = rawSymbol.toUpperCase();
        const bars = barsBySymbol.get(symbol) ?? [];
        const fills = fillsBySymbol.get(symbol) ?? [];
        // Equity overlay only on the first symbol panel; otherwise it would
        // duplicate the same curve under every chart.
        const equity = idx === 0 ? equityCurve : [];
        const header = (
          <div className="flex items-center justify-between border-b border-border/50 bg-bg-inset/60 px-3 py-1.5 text-[11px]">
            <span className="font-medium text-fg">
              {symbol} · {timeframe} · historical replay
            </span>
            <span className="text-fg-subtle">
              {dateOnly(start)} → {dateOnly(end)} · {bars.length} bar
              {bars.length === 1 ? "" : "s"}
              {fills.length > 0 ? ` · ${fills.length} fill${fills.length === 1 ? "" : "s"}` : ""}
            </span>
          </div>
        );
        return bars.length === 0 && fills.length === 0 ? (
          <div
            key={symbol}
            className="overflow-hidden rounded border border-dashed border-border/70 bg-bg-inset"
          >
            {header}
            <div className="flex h-[320px] items-center justify-center text-[11px] text-fg-subtle">
              awaiting bars for {symbol}… (real OHLC from your data source — Yahoo by default)
            </div>
          </div>
        ) : (
          <div
            key={symbol}
            className="overflow-hidden rounded border border-border/70 bg-bg-raised"
          >
            {header}
            <SimLabReplayChart
              symbol={symbol}
              bars={bars}
              fills={fills}
              equity={equity}
              height={320}
            />
          </div>
        );
      })}
    </div>
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

function streamTone(args: {
  status: string;
  lastError: string | null;
  completed: boolean;
  lastEventAt: Date | null;
}): "ok" | "warn" | "danger" | "info" | "muted" {
  if (args.completed) return "ok";
  if (args.lastError && args.status !== "open") return "danger";
  if (args.status === "open") return args.lastEventAt ? "ok" : "info";
  if (args.status === "connecting") return "info";
  if (args.status === "error") return "danger";
  return "warn";
}

function applyStreamMessage(prev: StreamState, msg: SimLabStreamMessage): StreamState {
  const next: StreamState = { ...prev };
  switch (msg.type) {
    case "session_started":
      next.sessionStarted = msg;
      return next;
    case "bar": {
      const bar = parseReplayBar(msg);
      if (!bar) return prev;
      next.barsBySymbol = appendToSymbolMap(prev.barsBySymbol, bar.symbol, bar.data);
      return next;
    }
    case "signal_plan":
      next.signalPlans = prev.signalPlans + 1;
      return next;
    case "virtual_fill": {
      const fill = parseReplayFill(msg);
      if (!fill) return prev;
      next.fillsBySymbol = appendToSymbolMap(prev.fillsBySymbol, fill.symbol, fill.data);
      return next;
    }
    case "position": {
      // Codex emits the full SimulatedPosition under payload.position; fall
      // back to the top-level symbol when the nested object is missing.
      const symbol =
        readNestedString(msg.payload, ["position", "symbol"]) ??
        readString(msg.payload, "symbol") ??
        "—";
      const positionsBySymbol = new Map(prev.positionsBySymbol);
      positionsBySymbol.set(symbol, msg);
      next.positionsBySymbol = positionsBySymbol;
      return next;
    }
    case "equity": {
      // PNL_UPDATED nests {equity, realized_pnl, gross_exposure} under details.
      const value =
        readNestedNumber(msg.payload, ["details", "equity"]) ??
        readNumber(msg.payload, "equity", "value", "cash_plus_market_value");
      if (value != null) {
        next.equityCurve = [...prev.equityCurve, { timestamp: msg.timestamp, value }];
        next.lastEquity = value;
      }
      return next;
    }
    case "session_completed": {
      next.sessionCompleted = msg;
      const realized = readNumber(msg.payload, "realized_pnl");
      if (prev.lastEquity == null && realized != null) next.lastEquity = realized;
      return next;
    }
    default:
      return next;
  }
}

function parseReplayBar(msg: SimLabStreamMessage): { symbol: string; data: SimLabReplayBar } | null {
  const symbol = readString(msg.payload, "symbol");
  const open = readNumber(msg.payload, "open");
  const high = readNumber(msg.payload, "high");
  const low = readNumber(msg.payload, "low");
  const close = readNumber(msg.payload, "close");
  const timestamp = readString(msg.payload, "timestamp") ?? msg.timestamp;
  if (!symbol || open == null || high == null || low == null || close == null) return null;
  return { symbol, data: { timestamp, open, high, low, close } };
}

function parseReplayFill(msg: SimLabStreamMessage): { symbol: string; data: SimLabReplayFill } | null {
  const symbol =
    readNestedString(msg.payload, ["fill", "symbol"]) ?? readString(msg.payload, "symbol");
  const price =
    readNestedNumber(msg.payload, ["fill", "price"]) ?? readNumber(msg.payload, "price");
  const sideRaw =
    readNestedString(msg.payload, ["fill", "side"]) ?? readString(msg.payload, "side");
  const qty = readNestedNumber(msg.payload, ["fill", "qty"]) ?? readNumber(msg.payload, "qty");
  const intentRaw = readNestedString(msg.payload, ["details", "intent_type"]);
  if (!symbol || price == null) return null;
  const side: SimLabReplayFill["side"] =
    sideRaw === "buy" || sideRaw === "long"
      ? "buy"
      : sideRaw === "sell" || sideRaw === "short"
        ? "sell"
        : "buy";
  const intent: SimLabReplayFill["intent"] | undefined =
    intentRaw === "entry"
      ? "entry"
      : intentRaw === "exit"
        ? "exit"
        : intentRaw === "open" || intentRaw === "close"
          ? intentRaw
          : undefined;
  return {
    symbol,
    data: {
      timestamp: msg.timestamp,
      side,
      price,
      qty: qty ?? undefined,
      intent,
    },
  };
}

function readString(payload: Record<string, unknown>, key: string): string | null {
  const v = payload[key];
  return typeof v === "string" ? v : null;
}

function readNumber(payload: Record<string, unknown>, ...keys: string[]): number | null {
  for (const key of keys) {
    const v = payload[key];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return null;
}

function readNestedString(payload: Record<string, unknown>, path: string[]): string | null {
  const v = readNested(payload, path);
  return typeof v === "string" ? v : null;
}

function readNestedNumber(payload: Record<string, unknown>, path: string[]): number | null {
  const v = readNested(payload, path);
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function readNested(payload: Record<string, unknown>, path: string[]): unknown {
  let cursor: unknown = payload;
  for (const key of path) {
    if (cursor && typeof cursor === "object" && !Array.isArray(cursor)) {
      cursor = (cursor as Record<string, unknown>)[key];
    } else {
      return undefined;
    }
  }
  return cursor;
}

function SessionSummary({ message }: { message: SimLabStreamMessage }): JSX.Element {
  const realized = readNumber(message.payload, "realized_pnl");
  const dd = readNumber(message.payload, "max_drawdown");
  const exposure = readNumber(message.payload, "gross_exposure");
  const fills = readNumber(message.payload, "simulated_fill_count");
  const orders = readNumber(message.payload, "simulated_order_count");
  const sigs = readNumber(message.payload, "signal_plan_count");
  return (
    <div className="grid grid-cols-2 gap-3 rounded border border-ok/40 bg-ok-subtle p-3 text-xs md:grid-cols-6">
      <Field label="Realized P&L" value={formatCurrency(realized)} />
      <Field label="Max drawdown" value={dd != null ? dd.toFixed(4) : "—"} />
      <Field label="Gross exposure" value={exposure != null ? exposure.toFixed(2) : "—"} />
      <Field label="SignalPlans" value={sigs != null ? formatQuantity(sigs) : "—"} />
      <Field label="Sim orders" value={orders != null ? formatQuantity(orders) : "—"} />
      <Field label="Sim fills" value={fills != null ? formatQuantity(fills) : "—"} />
    </div>
  );
}

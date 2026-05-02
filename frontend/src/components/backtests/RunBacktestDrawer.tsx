import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ResearchJobsApi } from "@/api/researchJobs";
import { StrategiesApi } from "@/api/strategies";
import { StrategyControlsApi } from "@/api/strategyControls";
import { ExecutionPlansApi } from "@/api/executionPlans";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { Banner } from "@/components/ui/Banner";
import { RiskPlanPicker } from "@/components/risk_plans/RiskPlanPicker";

type AdjustmentPolicy = "split_dividend_adjusted" | "split_only" | "raw";

/**
 * RunBacktestDrawer.
 *
 * Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §6.1 + §9.5:
 * - risk_plan_version_id is required
 * - strategy + version selectable across drafts and frozen versions
 * - Monte Carlo collapsible (trade_bootstrap | block_bootstrap, replications, seed)
 *
 * Submits to POST /api/v1/research/backtests; on success invalidates the
 * runs list and calls onCreated with the new run_id so the parent can
 * navigate into the detail view.
 */
export function RunBacktestDrawer({
  open,
  onOpenChange,
  onCreated,
  defaultRiskPlanVersionId,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onCreated?: (jobId: string) => void;
  defaultRiskPlanVersionId?: string | null;
}): JSX.Element {
  const queryClient = useQueryClient();
  const strategies = useQuery({
    queryKey: ["strategies", "list"],
    queryFn: () => StrategiesApi.list(),
    enabled: open,
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

  const [strategyId, setStrategyId] = useState<string>("");
  const [versionId, setVersionId] = useState<string>("");
  const [strategyControlsVersionId, setStrategyControlsVersionId] = useState<string>("");
  const [executionPlanVersionId, setExecutionPlanVersionId] = useState<string>("");
  const [riskPlanVersionId, setRiskPlanVersionId] = useState<string>(
    defaultRiskPlanVersionId ?? "",
  );

  useEffect(() => {
    if (defaultRiskPlanVersionId) setRiskPlanVersionId(defaultRiskPlanVersionId);
  }, [defaultRiskPlanVersionId]);
  const [symbols, setSymbols] = useState<string>("SPY");
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const oneYearAgo = useMemo(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    return d.toISOString().slice(0, 10);
  }, []);
  const [start, setStart] = useState<string>(oneYearAgo);
  const [end, setEnd] = useState<string>(today);
  const [timeframe, setTimeframe] = useState<string>("1d");
  const [initialCapital, setInitialCapital] = useState<string>("100000");
  const [commission, setCommission] = useState<string>("0");
  const [slippageBps, setSlippageBps] = useState<string>("0");
  const [source, setSource] = useState<"yahoo" | "alpaca">("yahoo");
  const [adjustmentPolicy, setAdjustmentPolicy] =
    useState<AdjustmentPolicy>("split_dividend_adjusted");
  const [mcEnabled, setMcEnabled] = useState<boolean>(true);
  const [mcMethod, setMcMethod] = useState<"trade_bootstrap" | "block_bootstrap">(
    "trade_bootstrap",
  );
  const [mcReplications, setMcReplications] = useState<string>("1000");
  const [mcBlockSize, setMcBlockSize] = useState<string>("5");
  const [mcSeed, setMcSeed] = useState<string>("42");

  // Auto-select first strategy + version when list loads
  const versionsQuery = useQuery({
    queryKey: ["strategies", "versions", strategyId],
    queryFn: () => StrategiesApi.listVersions(strategyId),
    enabled: open && Boolean(strategyId),
  });

  useEffect(() => {
    if (!strategyId && strategies.data?.strategies?.length) {
      setStrategyId(strategies.data.strategies[0].strategy_id);
    }
  }, [strategies.data, strategyId]);

  useEffect(() => {
    if (!versionId && versionsQuery.data?.length) {
      setVersionId(versionsQuery.data[0].strategy_version_id);
    }
  }, [versionsQuery.data, versionId]);

  useEffect(() => {
    if (!strategyControlsVersionId && strategyControls.data?.libraries?.length) {
      const preferred =
        strategyControls.data.libraries.find((library) => library.is_default) ??
        strategyControls.data.libraries[0];
      setStrategyControlsVersionId(preferred.head_version_id ?? "");
    }
  }, [strategyControls.data, strategyControlsVersionId]);

  useEffect(() => {
    if (!executionPlanVersionId && executionPlans.data?.libraries?.length) {
      const preferred =
        executionPlans.data.libraries.find((library) => library.is_default) ??
        executionPlans.data.libraries[0];
      setExecutionPlanVersionId(preferred.head_version_id ?? "");
    }
  }, [executionPlans.data, executionPlanVersionId]);

  const create = useMutation({
    mutationFn: () =>
      ResearchJobsApi.submitBacktest({
        request: {
          strategy_id: strategyId,
          strategy_version_id: versionId,
          strategy_controls_version_id: strategyControlsVersionId,
          execution_plan_version_id: executionPlanVersionId,
          risk_plan_version_id: riskPlanVersionId,
          symbols: symbols
            .split(",")
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
          timeframe,
          start: new Date(`${start}T00:00:00.000Z`).toISOString(),
          end: new Date(`${end}T00:00:00.000Z`).toISOString(),
          initial_capital: Number(initialCapital) || 100_000,
          cost_model: {
            commission_per_trade: Number(commission) || 0,
            slippage_bps: Number(slippageBps) || 0,
          },
          source,
          adjustment_policy: adjustmentPolicy,
          monte_carlo: mcEnabled
            ? {
                enabled: true,
                method: mcMethod,
                replications: Number(mcReplications) || 1000,
                block_size: Number(mcBlockSize) || 5,
                seed: Number(mcSeed) || 42,
              }
            : null,
        },
        metadata: {},
      }),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["backtests", "list"] });
      queryClient.invalidateQueries({ queryKey: ["research-jobs"] });
      onOpenChange(false);
      onCreated?.(job.job_id);
    },
  });

  const canSubmit =
    Boolean(strategyId) &&
    Boolean(versionId) &&
    Boolean(strategyControlsVersionId) &&
    Boolean(executionPlanVersionId) &&
    Boolean(riskPlanVersionId) &&
    symbols.trim().length > 0 &&
    start < end &&
    Number(initialCapital) > 0 &&
    !create.isPending;

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Run new backtest</DrawerTitle>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          <Select
            label="Strategy"
            value={strategyId}
            onChange={(e) => {
              setStrategyId(e.target.value);
              setVersionId("");
            }}
          >
            <option value="">— pick a strategy —</option>
            {(strategies.data?.strategies ?? []).map((s) => (
              <option key={s.strategy_id} value={s.strategy_id}>
                {s.name}
              </option>
            ))}
          </Select>

          <Select
            label="Strategy version (drafts + frozen)"
            value={versionId}
            onChange={(e) => setVersionId(e.target.value)}
            disabled={!strategyId}
          >
            <option value="">— pick a version —</option>
            {(versionsQuery.data ?? []).map((v) => (
              <option key={v.strategy_version_id} value={v.strategy_version_id}>
                v{v.version} · {v.status}
                {v.payload?.name ? ` · ${v.payload.name}` : ""}
              </option>
            ))}
          </Select>

          <Select
            label="Strategy Control"
            value={strategyControlsVersionId}
            onChange={(e) => setStrategyControlsVersionId(e.target.value)}
            hint="Pins the exact entry permissions, timeframe, sessions, and trade limits for this research snapshot."
          >
            <option value="">-- pick a Strategy Control --</option>
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
            value={executionPlanVersionId}
            onChange={(e) => setExecutionPlanVersionId(e.target.value)}
            hint="Pins the exact order types, brackets, retry, and cancel behavior for the research snapshot."
          >
            <option value="">-- pick an Execution Plan --</option>
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
            value={riskPlanVersionId || null}
            onChange={(next) => setRiskPlanVersionId(next ?? "")}
            hint="Required per contract §6.1. The Backtest run pins the exact RiskPlanVersion used."
          />

          <TextField
            label="Symbols (comma-separated)"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            placeholder="SPY, QQQ"
          />

          <div className="grid grid-cols-2 gap-3">
            <TextField
              type="date"
              label="Start"
              value={start}
              onChange={(e) => setStart(e.target.value)}
            />
            <TextField
              type="date"
              label="End"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Select
              label="Timeframe"
              value={timeframe}
              onChange={(e) => setTimeframe(e.target.value)}
            >
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="1d">1d</option>
            </Select>
            <Select
              label="Data source"
              value={source}
              onChange={(e) => setSource(e.target.value as "yahoo" | "alpaca")}
            >
              <option value="yahoo">Yahoo</option>
              <option value="alpaca">Alpaca</option>
            </Select>
            <Select
              label="Adjustment policy"
              value={adjustmentPolicy}
              onChange={(e) => setAdjustmentPolicy(e.target.value as AdjustmentPolicy)}
            >
              <option value="split_dividend_adjusted">Split + dividend adjusted</option>
              <option value="split_only">Split adjusted</option>
              <option value="raw">Raw</option>
            </Select>
          </div>

          <TextField
            type="number"
            label="Initial capital"
            value={initialCapital}
            min={0}
            onChange={(e) => setInitialCapital(e.target.value)}
          />

          <div className="grid grid-cols-2 gap-3">
            <TextField
              type="number"
              label="Commission per trade"
              value={commission}
              min={0}
              step={0.01}
              onChange={(e) => setCommission(e.target.value)}
              hint="post-fill, metrics-only"
            />
            <TextField
              type="number"
              label="Slippage (bps)"
              value={slippageBps}
              min={0}
              step={0.1}
              onChange={(e) => setSlippageBps(e.target.value)}
              hint="post-fill, metrics-only"
            />
          </div>

          <details className="rounded border border-border p-2 text-xs">
            <summary className="cursor-pointer text-fg-muted">Monte Carlo</summary>
            <div className="mt-3 space-y-3">
              <label className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={mcEnabled}
                  onChange={(e) => setMcEnabled(e.target.checked)}
                />
                <span>Run Monte Carlo on completion</span>
              </label>
              {mcEnabled ? (
                <>
                  <Select
                    label="Method"
                    value={mcMethod}
                    onChange={(e) =>
                      setMcMethod(e.target.value as "trade_bootstrap" | "block_bootstrap")
                    }
                  >
                    <option value="trade_bootstrap">Trade-PnL bootstrap</option>
                    <option value="block_bootstrap">Block bootstrap on bar returns</option>
                  </Select>
                  <div className="grid grid-cols-3 gap-3">
                    <TextField
                      type="number"
                      label="Replications"
                      min={10}
                      max={100000}
                      value={mcReplications}
                      onChange={(e) => setMcReplications(e.target.value)}
                    />
                    {mcMethod === "block_bootstrap" ? (
                      <TextField
                        type="number"
                        label="Block size"
                        min={2}
                        max={200}
                        value={mcBlockSize}
                        onChange={(e) => setMcBlockSize(e.target.value)}
                      />
                    ) : (
                      <div />
                    )}
                    <TextField
                      type="number"
                      label="Seed"
                      min={0}
                      value={mcSeed}
                      onChange={(e) => setMcSeed(e.target.value)}
                    />
                  </div>
                </>
              ) : null}
            </div>
          </details>

          {create.error ? (
            <Banner
              severity="danger"
              title="Backtest failed"
              message={(create.error as Error).message}
            />
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => create.mutate()} disabled={!canSubmit}>
            {create.isPending ? "Running…" : "Run backtest"}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

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
 * RunOptimizationDrawer.
 *
 * Operator-driven parameter sweep. Spine-driven: hits the Optimization service
 * which runs HistoricalReplayEngine per candidate. Output is hypothesis only —
 * the detail page surfaces a Walk-Forward handoff button to validate forward.
 */
export function RunOptimizationDrawer({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onCreated?: (jobId: string) => void;
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
  const [method, setMethod] = useState<"grid" | "random">("grid");
  const [maxCandidates, setMaxCandidates] = useState<string>("200");
  const [seed, setSeed] = useState<string>("42");
  const [selectionCriterion, setSelectionCriterion] = useState<
    "sharpe" | "sortino" | "calmar" | "expectancy" | "max_dd_bounded_sharpe" | "hit_rate"
  >("max_dd_bounded_sharpe");
  const [sweepRows, setSweepRows] = useState<{ field: string; values: string }[]>([
    { field: "fixed_shares", values: "5, 10, 20" },
  ]);
  const [baseRiskPlanVersionId, setBaseRiskPlanVersionId] = useState<string | null>(null);
  const [mcEnabled, setMcEnabled] = useState<boolean>(false);
  const [wfTopK, setWfTopK] = useState<string>("3");
  const [runnersPct, setRunnersPct] = useState<string>("5");

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
      ResearchJobsApi.submitOptimization({
        request: {
          strategy_id: strategyId,
          strategy_version_id: versionId,
          strategy_controls_version_id: strategyControlsVersionId,
          execution_plan_version_id: executionPlanVersionId,
          symbols: symbols
            .split(",")
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
          start: new Date(`${start}T00:00:00.000Z`).toISOString(),
          end: new Date(`${end}T00:00:00.000Z`).toISOString(),
          timeframe,
          initial_capital: Number(initialCapital) || 100_000,
          cost_model: {
            commission_per_trade: Number(commission) || 0,
            slippage_bps: Number(slippageBps) || 0,
          },
          source,
          adjustment_policy: adjustmentPolicy,
          method,
          max_candidates: Number(maxCandidates) || 200,
          seed: Number(seed) || 42,
          selection_criterion: selectionCriterion,
          sweep: {
            base_risk_plan_version_id: baseRiskPlanVersionId ?? undefined,
            parameters: sweepRows
              .map((row) => ({
                field: row.field,
                values: row.values
                  .split(",")
                  .map((v) => Number(v.trim()))
                  .filter((v) => Number.isFinite(v) && v > 0),
              }))
              .filter((row) => row.values.length > 0),
          },
          monte_carlo: mcEnabled
            ? {
                enabled: true,
                method: "trade_bootstrap",
                replications: 1000,
                block_size: 5,
                seed: 42,
              }
            : null,
          runners_up_threshold_pct: Math.max(0, Number(runnersPct) / 100 || 0.05),
          walk_forward_handoff_top_k: Math.max(1, Number(wfTopK) || 3),
        },
        metadata: {},
      }),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["optimization", "runs"] });
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
    Boolean(baseRiskPlanVersionId) &&
    symbols.trim().length > 0 &&
    start < end &&
    Number(initialCapital) > 0 &&
    sweepRows.some((row) => row.values.trim().length > 0) &&
    !create.isPending;

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Run new optimization</DrawerTitle>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          <Banner
            severity="info"
            title="Hypothesis search"
            message="Optimization searches a parameter space on one window. The output is the best parameter set, surfaced with the full landscape and a one-click 'Validate with Walk-Forward' handoff. Curve-fit until WF validates it — never deploy directly from an Optimization winner."
          />
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
            label="Strategy version"
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
            hint="Pins the exact timeframe, sessions, and entry controls used by every candidate."
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
            hint="Pins the exact order behavior used by every candidate."
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

          <TextField
            label="Symbols (comma-separated)"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
          />

          <div className="grid grid-cols-2 gap-3">
            <TextField type="date" label="Start" value={start} onChange={(e) => setStart(e.target.value)} />
            <TextField type="date" label="End" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>

          <div className="grid grid-cols-3 gap-3">
            <Select label="Timeframe" value={timeframe} onChange={(e) => setTimeframe(e.target.value)}>
              <option value="1m">1m</option>
              <option value="5m">5m</option>
              <option value="15m">15m</option>
              <option value="1h">1h</option>
              <option value="1d">1d</option>
            </Select>
            <Select label="Data source" value={source} onChange={(e) => setSource(e.target.value as "yahoo" | "alpaca")}>
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
            <TextField type="number" label="Commission per trade" value={commission} min={0} step={0.01} onChange={(e) => setCommission(e.target.value)} />
            <TextField type="number" label="Slippage (bps)" value={slippageBps} min={0} step={0.1} onChange={(e) => setSlippageBps(e.target.value)} />
          </div>

          <div className="rounded border border-border p-3 space-y-3 text-xs">
            <div className="text-fg-muted text-[11px] uppercase tracking-wider">Search</div>
            <div className="grid grid-cols-3 gap-3">
              <Select label="Method" value={method} onChange={(e) => setMethod(e.target.value as "grid" | "random")}>
                <option value="grid">Grid (full Cartesian; capped at 1000 / max_candidates)</option>
                <option value="random">Random (uniform sample without replacement)</option>
              </Select>
              <TextField type="number" label="Max candidates" value={maxCandidates} min={1} max={2000} onChange={(e) => setMaxCandidates(e.target.value)} />
              <TextField type="number" label="Random seed" value={seed} min={0} onChange={(e) => setSeed(e.target.value)} />
            </div>
            <Select
              label="Selection criterion"
              value={selectionCriterion}
              onChange={(e) =>
                setSelectionCriterion(e.target.value as typeof selectionCriterion)
              }
              hint="Default penalises Sharpe by drawdown depth"
            >
              <option value="max_dd_bounded_sharpe">max-DD-bounded Sharpe (recommended)</option>
              <option value="sharpe">Sharpe</option>
              <option value="sortino">Sortino</option>
              <option value="calmar">Calmar</option>
              <option value="expectancy">Expectancy</option>
              <option value="hit_rate">Hit rate</option>
            </Select>
          </div>

          <div className="rounded border border-border p-3 space-y-3 text-xs">
            <div className="text-fg-muted text-[11px] uppercase tracking-wider">Risk-plan parameter grid</div>
            <RiskPlanPicker
              label="Risk Plan"
              required
              value={baseRiskPlanVersionId}
              onChange={setBaseRiskPlanVersionId}
              hint="Required. Optimization sweeps the field grid below on top of this exact Risk Plan version."
            />
            {sweepRows.map((row, i) => (
              <div key={i} className="grid grid-cols-2 gap-3">
                <Select
                  label={i === 0 ? "Field" : ""}
                  value={row.field}
                  onChange={(e) => {
                    const next = [...sweepRows];
                    next[i] = { ...next[i], field: e.target.value };
                    setSweepRows(next);
                  }}
                >
                  <option value="fixed_shares">fixed_shares</option>
                  <option value="risk_per_trade_pct">risk_per_trade_pct</option>
                  <option value="fixed_notional">fixed_notional</option>
                  <option value="max_positions">max_positions</option>
                  <option value="max_symbol_exposure_pct">max_symbol_exposure_pct</option>
                  <option value="max_daily_loss_pct">max_daily_loss_pct</option>
                  <option value="max_drawdown_pct">max_drawdown_pct</option>
                </Select>
                <TextField
                  label={i === 0 ? "Values (comma-separated)" : ""}
                  value={row.values}
                  onChange={(e) => {
                    const next = [...sweepRows];
                    next[i] = { ...next[i], values: e.target.value };
                    setSweepRows(next);
                  }}
                />
              </div>
            ))}
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  setSweepRows([...sweepRows, { field: "risk_per_trade_pct", values: "0.5, 1.0, 1.5" }])
                }
              >
                + Add parameter
              </Button>
              {sweepRows.length > 1 ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setSweepRows(sweepRows.slice(0, -1))}
                >
                  − Remove last
                </Button>
              ) : null}
            </div>
          </div>

          <details className="rounded border border-border p-3 text-xs">
            <summary className="cursor-pointer text-fg-muted">Advanced</summary>
            <div className="mt-3 space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <TextField
                  type="number"
                  label="Runners-up window (% of winner)"
                  value={runnersPct}
                  min={0}
                  max={50}
                  step={1}
                  onChange={(e) => setRunnersPct(e.target.value)}
                  hint="Surface every candidate within this % of the winner's score"
                />
                <TextField
                  type="number"
                  label="Walk-Forward handoff top-K"
                  value={wfTopK}
                  min={1}
                  max={20}
                  onChange={(e) => setWfTopK(e.target.value)}
                  hint="Top-K candidates pre-fill the WF sweep grid"
                />
              </div>
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={mcEnabled} onChange={(e) => setMcEnabled(e.target.checked)} />
                <span>Run trade-bootstrap Monte Carlo on the winner</span>
              </label>
            </div>
          </details>

          {create.error ? (
            <Banner severity="danger" title="Optimization failed" message={(create.error as Error).message} />
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => create.mutate()} disabled={!canSubmit}>
            {create.isPending ? "Searching…" : "Run optimization"}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

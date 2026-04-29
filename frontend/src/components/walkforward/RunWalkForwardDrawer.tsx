import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ResearchJobsApi } from "@/api/researchJobs";
import { StrategiesApi } from "@/api/strategies";
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

/**
 * RunWalkForwardDrawer.
 *
 * Operator-driven walk-forward run. Doctrine: per-fold IS+OOS replays via the
 * same HistoricalReplayEngine the Backtest uses; recommendation aggregates
 * across folds; recommended risk plan emerges from the sweep grid.
 */
export function RunWalkForwardDrawer({
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

  const [strategyId, setStrategyId] = useState<string>("");
  const [versionId, setVersionId] = useState<string>("");
  const [symbols, setSymbols] = useState<string>("SPY");
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const oneYearAgo = useMemo(() => {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 2);
    return d.toISOString().slice(0, 10);
  }, []);
  const [start, setStart] = useState<string>(oneYearAgo);
  const [end, setEnd] = useState<string>(today);
  const [timeframe, setTimeframe] = useState<string>("1d");
  const [initialCapital, setInitialCapital] = useState<string>("100000");
  const [commission, setCommission] = useState<string>("0");
  const [slippageBps, setSlippageBps] = useState<string>("0");
  const [source, setSource] = useState<"yahoo" | "alpaca">("yahoo");
  const [windowMode, setWindowMode] = useState<"rolling" | "anchored">("rolling");
  const [isLengthDays, setIsLengthDays] = useState<string>("180");
  const [oosLengthDays, setOosLengthDays] = useState<string>("60");
  const [stepDays, setStepDays] = useState<string>("60");
  const [maxFolds, setMaxFolds] = useState<string>("12");
  const [selectionCriterion, setSelectionCriterion] = useState<
    "sharpe" | "sortino" | "calmar" | "expectancy" | "max_dd_bounded_sharpe" | "hit_rate"
  >("max_dd_bounded_sharpe");
  const [sweepEnabled, setSweepEnabled] = useState<boolean>(true);
  const [sweepField, setSweepField] = useState<string>("fixed_shares");
  const [sweepValues, setSweepValues] = useState<string>("5, 10, 20");
  const [baseRiskPlanVersionId, setBaseRiskPlanVersionId] = useState<string | null>(null);
  const [mcEnabled, setMcEnabled] = useState<boolean>(false);

  // Operator-tunable scoring + thresholds. Defaults match the backend
  // (recommendation.py DEFAULT_SCORE_WEIGHTS + DEFAULT_SHIP_THRESHOLDS).
  const SCORE_DEFAULTS = { sharpe: 0.5, stability: 0.5 };
  const THRESHOLD_DEFAULTS = {
    ship_oos_sharpe_p25_min: 0.5,
    ship_is_oos_decay_max: 0.5,
    ship_folds_passed_ratio_min: 0.6,
    ship_oos_max_dd_min: -0.25,
    do_not_ship_oos_sharpe_p50_max: 0.0,
    do_not_ship_is_oos_decay_min: 1.5,
    do_not_ship_oos_max_dd_max: -0.4,
  };
  const [sharpeWeight, setSharpeWeight] = useState<string>(String(SCORE_DEFAULTS.sharpe));
  const [stabilityWeight, setStabilityWeight] = useState<string>(String(SCORE_DEFAULTS.stability));
  const [shipMaxDd, setShipMaxDd] = useState<string>(String(THRESHOLD_DEFAULTS.ship_oos_max_dd_min));
  const [doNotShipMaxDd, setDoNotShipMaxDd] = useState<string>(
    String(THRESHOLD_DEFAULTS.do_not_ship_oos_max_dd_max),
  );
  const resetTunables = (): void => {
    setSharpeWeight(String(SCORE_DEFAULTS.sharpe));
    setStabilityWeight(String(SCORE_DEFAULTS.stability));
    setShipMaxDd(String(THRESHOLD_DEFAULTS.ship_oos_max_dd_min));
    setDoNotShipMaxDd(String(THRESHOLD_DEFAULTS.do_not_ship_oos_max_dd_max));
  };

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

  const create = useMutation({
    mutationFn: () =>
      ResearchJobsApi.submitWalkForward({
        request: {
        strategy_id: strategyId,
        strategy_version_id: versionId,
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
        window_mode: windowMode,
        is_length: { unit: "days", value: Number(isLengthDays) || 180 },
        oos_length: { unit: "days", value: Number(oosLengthDays) || 60 },
        step: { unit: "days", value: Number(stepDays) || 60 },
        max_folds: Number(maxFolds) || null,
        selection_criterion: selectionCriterion,
        sweep: sweepEnabled
          ? {
              enabled: true,
              base_risk_plan_version_id: baseRiskPlanVersionId ?? undefined,
              parameters: [
                {
                  field: sweepField,
                  values: sweepValues
                    .split(",")
                    .map((v) => Number(v.trim()))
                    .filter((v) => Number.isFinite(v) && v > 0),
                },
              ],
            }
          : null,
        monte_carlo: mcEnabled
          ? { enabled: true, method: "trade_bootstrap", replications: 1000, block_size: 5, seed: 42 }
          : null,
        score_weights: {
          oos_sharpe_p25: Number(sharpeWeight) || SCORE_DEFAULTS.sharpe,
          stability: Number(stabilityWeight) || SCORE_DEFAULTS.stability,
        },
        ship_thresholds: {
          ship_oos_max_dd_min: Number(shipMaxDd) || THRESHOLD_DEFAULTS.ship_oos_max_dd_min,
          do_not_ship_oos_max_dd_max: Number(doNotShipMaxDd) || THRESHOLD_DEFAULTS.do_not_ship_oos_max_dd_max,
        },
        },
        metadata: {},
      }),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["walk-forward", "runs"] });
      queryClient.invalidateQueries({ queryKey: ["research-jobs"] });
      onOpenChange(false);
      onCreated?.(job.job_id);
    },
  });

  const canSubmit =
    Boolean(strategyId) &&
    Boolean(versionId) &&
    symbols.trim().length > 0 &&
    start < end &&
    Number(initialCapital) > 0 &&
    Number(isLengthDays) > 0 &&
    Number(oosLengthDays) > 0 &&
    !create.isPending;

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Run new walk-forward</DrawerTitle>
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

          <TextField
            label="Symbols (comma-separated)"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
          />

          <div className="grid grid-cols-2 gap-3">
            <TextField type="date" label="Start" value={start} onChange={(e) => setStart(e.target.value)} />
            <TextField type="date" label="End" value={end} onChange={(e) => setEnd(e.target.value)} />
          </div>

          <div className="grid grid-cols-2 gap-3">
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
            <div className="text-fg-muted text-[11px] uppercase tracking-wider">Walk-forward windows</div>
            <Select label="Window mode" value={windowMode} onChange={(e) => setWindowMode(e.target.value as "rolling" | "anchored")}>
              <option value="rolling">Rolling (IS slides forward)</option>
              <option value="anchored">Anchored (IS grows from start)</option>
            </Select>
            <div className="grid grid-cols-3 gap-3">
              <TextField type="number" label="IS length (days)" value={isLengthDays} min={1} onChange={(e) => setIsLengthDays(e.target.value)} />
              <TextField type="number" label="OOS length (days)" value={oosLengthDays} min={1} onChange={(e) => setOosLengthDays(e.target.value)} />
              <TextField type="number" label="Step (days)" value={stepDays} min={1} onChange={(e) => setStepDays(e.target.value)} />
            </div>
            <TextField type="number" label="Max folds" value={maxFolds} min={1} onChange={(e) => setMaxFolds(e.target.value)} />
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

          <details className="rounded border border-border p-3 text-xs" open>
            <summary className="cursor-pointer text-fg-muted">Risk-plan parameter sweep</summary>
            <div className="mt-3 space-y-3">
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={sweepEnabled} onChange={(e) => setSweepEnabled(e.target.checked)} />
                <span>Enable sweep (drives the recommended risk plan output)</span>
              </label>
              {sweepEnabled ? (
                <>
                  <RiskPlanPicker
                    label="Base Risk Plan (sweep starts from this version)"
                    value={baseRiskPlanVersionId}
                    onChange={setBaseRiskPlanVersionId}
                    hint="Sweep overrides the selected field on top of this base config; recommendation is saved as a draft Risk Plan with source=walk_forward_recommended."
                  />
                  <div className="grid grid-cols-2 gap-3">
                    <Select label="Field" value={sweepField} onChange={(e) => setSweepField(e.target.value)}>
                      <option value="fixed_shares">fixed_shares</option>
                      <option value="risk_per_trade_pct">risk_per_trade_pct</option>
                      <option value="fixed_notional">fixed_notional</option>
                      <option value="max_positions">max_positions</option>
                      <option value="max_symbol_exposure_pct">max_symbol_exposure_pct</option>
                      <option value="max_daily_loss_pct">max_daily_loss_pct</option>
                      <option value="max_drawdown_pct">max_drawdown_pct</option>
                    </Select>
                    <TextField label="Values (comma-separated)" value={sweepValues} onChange={(e) => setSweepValues(e.target.value)} />
                  </div>
                </>
              ) : null}
            </div>
          </details>

          <details className="rounded border border-border p-3 text-xs" open>
            <summary className="cursor-pointer text-fg-muted">Recommendation tuning</summary>
            <div className="mt-3 space-y-3">
              <div className="text-[11px] text-fg-subtle">
                Score = sharpe weight × OOS-Sharpe-p25 + stability weight × stability.
                Defaults are 0.50 / 0.50. Reset returns both weights and the max-DD
                thresholds to backend defaults.
              </div>
              <div className="grid grid-cols-2 gap-3">
                <TextField
                  type="number"
                  label="Sharpe weight"
                  step={0.05}
                  min={0}
                  max={1}
                  value={sharpeWeight}
                  onChange={(e) => setSharpeWeight(e.target.value)}
                />
                <TextField
                  type="number"
                  label="Stability weight"
                  step={0.05}
                  min={0}
                  max={1}
                  value={stabilityWeight}
                  onChange={(e) => setStabilityWeight(e.target.value)}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <TextField
                  type="number"
                  label="Ship max-DD floor (e.g. -0.25)"
                  step={0.01}
                  value={shipMaxDd}
                  onChange={(e) => setShipMaxDd(e.target.value)}
                  hint="Drawdown deeper than this disqualifies a ship_recommended verdict"
                />
                <TextField
                  type="number"
                  label="Do-not-ship max-DD ceiling (e.g. -0.40)"
                  step={0.01}
                  value={doNotShipMaxDd}
                  onChange={(e) => setDoNotShipMaxDd(e.target.value)}
                  hint="Drawdown ≤ this triggers do_not_ship outright"
                />
              </div>
              <Button size="sm" variant="ghost" onClick={resetTunables}>
                Reset to defaults
              </Button>
            </div>
          </details>

          <details className="rounded border border-border p-3 text-xs">
            <summary className="cursor-pointer text-fg-muted">Monte Carlo (on aggregate OOS)</summary>
            <div className="mt-3">
              <label className="flex items-center gap-2 text-xs">
                <input type="checkbox" checked={mcEnabled} onChange={(e) => setMcEnabled(e.target.checked)} />
                <span>Run trade-bootstrap Monte Carlo on aggregated OOS trades</span>
              </label>
            </div>
          </details>

          {create.error ? (
            <Banner severity="danger" title="Walk-forward failed" message={(create.error as Error).message} />
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => create.mutate()} disabled={!canSubmit}>
            {create.isPending ? "Running…" : "Run walk-forward"}
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

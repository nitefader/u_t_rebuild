import { z } from "zod";

/**
 * Research run schemas.
 *
 * Doctrine: research evidence is additive. Backend schemas grow
 * fields over time (regime tags, status history, per-regime metrics,
 * cost-model echoes). Schemas .passthrough() and use z.string() for
 * status enums so the typed client never rejects a benign addition.
 */

const MetricsSchema = z.record(z.unknown()).default({});

const ResearchRunBaseSchema = z.object({
  run_id: z.string(),
  strategy_id: z.string(),
  strategy_version_id: z.string(),
  created_at: z.string(),
});

export const StatusHistoryEntrySchema = z
  .object({
    status: z.string(),
    at: z.string().optional(),
    reason: z.string().nullable().optional(),
  })
  .passthrough();

export const BacktestRunSchema = ResearchRunBaseSchema.extend({
  watchlist_snapshot_id: z.string().nullable().optional(),
  universe: z.array(z.string()).default([]),
  timeframe: z.string().default("1d"),
  start: z.string(),
  end: z.string(),
  initial_capital: z.number().default(0),
  cost_model: z.record(z.unknown()).default({}),
  status: z.string().default("recorded"),
  status_history: z.array(StatusHistoryEntrySchema).default([]),
  bar_count: z.number().default(0),
  signal_plan_count: z.number().default(0),
  simulated_trade_count: z.number().default(0),
  metrics: MetricsSchema,
  results: z.record(z.unknown()).default({}),
}).passthrough();
export type BacktestRun = z.infer<typeof BacktestRunSchema>;

export const BacktestRunListSchema = z
  .object({
    runs: z.array(BacktestRunSchema).default([]),
  })
  .passthrough();
export type BacktestRunList = z.infer<typeof BacktestRunListSchema>;

export const MonteCarloConfigSchema = z
  .object({
    enabled: z.boolean().default(true),
    method: z.enum(["trade_bootstrap", "block_bootstrap"]).default("trade_bootstrap"),
    replications: z.number().int().min(10).max(100_000).default(1000),
    block_size: z.number().int().min(2).max(200).default(5),
    seed: z.number().int().nonnegative().default(42),
  })
  .passthrough();
export type MonteCarloConfig = z.infer<typeof MonteCarloConfigSchema>;

export const CostModelSchema = z
  .object({
    commission_per_trade: z.number().nonnegative().default(0),
    slippage_bps: z.number().nonnegative().default(0),
  })
  .passthrough();
export type CostModelInput = z.infer<typeof CostModelSchema>;

export const BacktestRunRequestSchema = z
  .object({
    strategy_id: z.string(),
    strategy_version_id: z.string(),
    risk_plan_version_id: z.string().nullable().optional(),
    watchlist_snapshot_id: z.string().nullable().optional(),
    universe: z.array(z.string()).default([]),
    symbols: z.array(z.string()).default([]),
    timeframe: z.string().default("1d"),
    start: z.string(),
    end: z.string(),
    initial_capital: z.number().nonnegative().default(0),
    cost_model: CostModelSchema.default({ commission_per_trade: 0, slippage_bps: 0 }),
    source: z.enum(["yahoo", "alpaca"]).default("yahoo"),
    adjustment_policy: z
      .enum(["split_dividend_adjusted", "split_only", "raw"])
      .default("split_dividend_adjusted"),
    monte_carlo: MonteCarloConfigSchema.nullable().optional(),
    bar_count: z.number().nonnegative().default(0),
    signal_plan_count: z.number().nonnegative().default(0),
    simulated_trade_count: z.number().nonnegative().default(0),
    metrics: MetricsSchema,
  })
  .passthrough();
export type BacktestRunRequest = z.infer<typeof BacktestRunRequestSchema>;

export const MonteCarloPercentileBandSchema = z
  .object({
    p05: z.number().optional(),
    p25: z.number().optional(),
    p50: z.number().optional(),
    p75: z.number().optional(),
    p95: z.number().optional(),
  })
  .passthrough();

export const MonteCarloHistogramBinSchema = z
  .object({
    bin_start: z.number(),
    bin_end: z.number(),
    count: z.number(),
  })
  .passthrough();

export const MonteCarloResultSchema = z
  .object({
    method: z.string(),
    replications: z.number().int().nonnegative(),
    seed: z.number().int().nonnegative(),
    terminal_equity: MonteCarloPercentileBandSchema,
    sharpe: MonteCarloPercentileBandSchema,
    max_drawdown: MonteCarloPercentileBandSchema,
    final_equity_histogram: z.array(MonteCarloHistogramBinSchema).default([]),
  })
  .passthrough();
export type MonteCarloResult = z.infer<typeof MonteCarloResultSchema>;

export const EquityPointSchema = z
  .object({
    timestamp: z.string().optional(),
    equity: z.number().optional(),
    value: z.number().optional(),
    cash: z.number().optional(),
    pnl: z.number().optional(),
  })
  .passthrough();
export type EquityPoint = z.infer<typeof EquityPointSchema>;

export const DrawdownPointSchema = z
  .object({
    timestamp: z.string().optional(),
    drawdown: z.number().optional(),
    underwater: z.number().optional(),
    peak: z.number().optional(),
    value: z.number().optional(),
  })
  .passthrough();
export type DrawdownPoint = z.infer<typeof DrawdownPointSchema>;

export const TradeLedgerEntrySchema = z
  .object({
    symbol: z.string().optional(),
    side: z.string().optional(),
    quantity: z.number().optional(),
    qty: z.number().optional(),
    entry_price: z.number().optional(),
    exit_price: z.number().optional(),
    pnl: z.number().optional(),
    return_pct: z.number().optional(),
    opened_at: z.string().optional(),
    closed_at: z.string().optional(),
    regime: z.string().optional(),
  })
  .passthrough();
export type TradeLedgerEntry = z.infer<typeof TradeLedgerEntrySchema>;

export const PerSymbolBreakdownSchema = z
  .object({
    symbol: z.string().optional(),
    trades: z.number().optional(),
    win_rate: z.number().optional(),
    pnl: z.number().optional(),
    return_pct: z.number().optional(),
  })
  .passthrough();
export type PerSymbolBreakdown = z.infer<typeof PerSymbolBreakdownSchema>;

export const RegimeTagSchema = z
  .object({
    timestamp: z.string().optional(),
    regime: z.string().optional(),
    confidence: z.number().optional(),
    symbol: z.string().optional(),
  })
  .passthrough();
export type RegimeTag = z.infer<typeof RegimeTagSchema>;

export const BacktestResultsResponseSchema = z
  .object({
    run_id: z.string(),
    status: z.string(),
    equity_curve: z.array(EquityPointSchema).default([]),
    trade_ledger: z.array(TradeLedgerEntrySchema).default([]),
    per_symbol_breakdown: z.array(PerSymbolBreakdownSchema).default([]),
    drawdown_series: z.array(DrawdownPointSchema).default([]),
    regime_tags: z.array(RegimeTagSchema).default([]),
    per_regime_metrics: z.record(z.unknown()).default({}),
  })
  .passthrough();
export type BacktestResultsResponse = z.infer<typeof BacktestResultsResponseSchema>;

export const BacktestMetricsResponseSchema = z
  .object({
    run_id: z.string(),
    status: z.string(),
    metrics: z.record(z.unknown()).default({}),
    cost_model: z.record(z.unknown()).default({}),
  })
  .passthrough();
export type BacktestMetricsResponse = z.infer<typeof BacktestMetricsResponseSchema>;

export const SimulationRunSchema = ResearchRunBaseSchema.extend({
  scenario_name: z.string(),
  start: z.string(),
  end: z.string(),
  signal_plan_count: z.number(),
  simulated_order_count: z.number(),
  simulated_fill_count: z.number(),
  metrics: MetricsSchema,
}).passthrough();
export type SimulationRun = z.infer<typeof SimulationRunSchema>;

export const SimulationSessionListSchema = z
  .object({
    sessions: z.array(SimulationRunSchema).default([]),
  })
  .passthrough();
export type SimulationSessionList = z.infer<typeof SimulationSessionListSchema>;

export const SimulationSessionRequestSchema = z.object({
  strategy_id: z.string(),
  strategy_version_id: z.string(),
  scenario_name: z.string(),
  start: z.string(),
  end: z.string(),
  signal_plan_count: z.number().nonnegative().default(0),
  simulated_order_count: z.number().nonnegative().default(0),
  simulated_fill_count: z.number().nonnegative().default(0),
  metrics: MetricsSchema,
});
export type SimulationSessionRequest = z.infer<typeof SimulationSessionRequestSchema>;

export const SimulationRunRequestSchema = z.object({
  signal_plan_count: z.number().nonnegative().default(0),
  simulated_order_count: z.number().nonnegative().default(0),
  simulated_fill_count: z.number().nonnegative().default(0),
  metrics: MetricsSchema,
});
export type SimulationRunRequest = z.infer<typeof SimulationRunRequestSchema>;

export const SimLabBatchRunRequestSchema = z.object({
  strategy_id: z.string(),
  strategy_version_id: z.string(),
  scenario_name: z.string().min(1),
  universe: z.array(z.string()).min(1),
  timeframe: z.string().default("5m"),
  start: z.string(),
  end: z.string(),
  initial_cash: z.number().positive().default(100_000),
  bar_count: z.number().int().min(2).default(12),
});
export type SimLabBatchRunRequest = z.infer<typeof SimLabBatchRunRequestSchema>;

export const SimLabBatchRunResponseSchema = z
  .object({
    run: SimulationRunSchema,
    events: z.array(z.record(z.unknown())).default([]),
    orders: z.array(z.record(z.unknown())).default([]),
    fills: z.array(z.record(z.unknown())).default([]),
    positions: z.array(z.record(z.unknown())).default([]),
    trades: z.array(z.record(z.unknown())).default([]),
    equity_curve: z.array(EquityPointSchema).default([]),
  })
  .passthrough();
export type SimLabBatchRunResponse = z.infer<typeof SimLabBatchRunResponseSchema>;

// Sim Lab streaming WS message envelope. The discriminated union tracks the
// closed type set Codex emits today; .passthrough() on the schema means
// additive payload keys (e.g. cumulative gross exposure, realized pnl, etc.)
// flow through naturally. `type` is z.string() so a future Codex-emitted
// variant doesn't reject the typed client.
export const SimLabStreamMessageSchema = z
  .object({
    type: z.string(),
    sequence: z.number().int().nonnegative(),
    run_id: z.string(),
    timestamp: z.string(),
    payload: z.record(z.unknown()),
  })
  .passthrough();
export type SimLabStreamMessage = z.infer<typeof SimLabStreamMessageSchema>;

export const OptimizationRunSchema = ResearchRunBaseSchema.extend({
  objective: z.string(),
  candidate_count: z.number(),
  best_parameters: MetricsSchema,
  best_metrics: MetricsSchema,
}).passthrough();
export type OptimizationRun = z.infer<typeof OptimizationRunSchema>;

export const OptimizationRunListSchema = z
  .object({
    runs: z.array(OptimizationRunSchema).default([]),
  })
  .passthrough();
export type OptimizationRunList = z.infer<typeof OptimizationRunListSchema>;

export const OptimizationSweepParameterSchema = z
  .object({
    field: z.string(),
    values: z.array(z.number()).min(1),
  })
  .passthrough();

export const OptimizationSweepConfigSchema = z
  .object({
    base_risk_plan_version_id: z.string().nullable().optional(),
    parameters: z.array(OptimizationSweepParameterSchema).default([]),
  })
  .passthrough();

export const OptimizationCandidateSchema = z
  .object({
    candidate_index: z.number().int().nonnegative(),
    parameters: z.record(z.unknown()).default({}),
    metrics: z.record(z.unknown()).default({}),
    score: z.number().optional(),
    trade_count: z.number().int().nonnegative().optional(),
    risk_decision_card_ids: z.array(z.string()).default([]),
    recommended: z.boolean().default(false),
  })
  .passthrough();
export type OptimizationCandidate = z.infer<typeof OptimizationCandidateSchema>;

export const OptimizationLandscapeSummarySchema = z
  .object({
    score_min: z.number().optional(),
    score_p25: z.number().optional(),
    score_p50: z.number().optional(),
    score_p75: z.number().optional(),
    score_p95: z.number().optional(),
    score_max: z.number().optional(),
    sharpe_min: z.number().optional(),
    sharpe_max: z.number().optional(),
    max_dd_best: z.number().optional(),
    max_dd_worst: z.number().optional(),
  })
  .passthrough();

export const OptimizationHeatmapSchema = z
  .object({
    x_field: z.string(),
    y_field: z.string(),
    x_values: z.array(z.union([z.number(), z.string()])),
    y_values: z.array(z.union([z.number(), z.string()])),
    cells: z.array(z.array(z.number().nullable())),
  })
  .passthrough();
export type OptimizationHeatmap = z.infer<typeof OptimizationHeatmapSchema>;

export const OptimizationRunRequestSchema = z
  .object({
    strategy_id: z.string(),
    strategy_version_id: z.string(),
    symbols: z.array(z.string()).default([]),
    start: z.string().nullable().optional(),
    end: z.string().nullable().optional(),
    timeframe: z.string().default("1d"),
    initial_capital: z.number().nonnegative().default(0),
    cost_model: CostModelSchema.default({ commission_per_trade: 0, slippage_bps: 0 }),
    source: z.enum(["yahoo", "alpaca"]).default("yahoo"),
    adjustment_policy: z
      .enum(["split_dividend_adjusted", "split_only", "raw"])
      .default("split_dividend_adjusted"),
    method: z.enum(["grid", "random"]).default("grid"),
    max_candidates: z.number().int().positive().nullable().optional(),
    seed: z.number().int().nonnegative().default(42),
    selection_criterion: z
      .enum(["sharpe", "sortino", "calmar", "expectancy", "max_dd_bounded_sharpe", "hit_rate"])
      .default("max_dd_bounded_sharpe"),
    sweep: OptimizationSweepConfigSchema.nullable().optional(),
    monte_carlo: MonteCarloConfigSchema.nullable().optional(),
    runners_up_threshold_pct: z.number().default(0.05),
    walk_forward_handoff_top_k: z.number().int().positive().default(3),
    heatmap_dimensions: z.tuple([z.string(), z.string()]).nullable().optional(),
    // Legacy placeholders kept for back-compat with the read-only path
    objective: z.string().default("max_dd_bounded_sharpe"),
    candidate_count: z.number().nonnegative().default(0),
    best_parameters: MetricsSchema,
    best_metrics: MetricsSchema,
  })
  .passthrough();
export type OptimizationRunRequest = z.infer<typeof OptimizationRunRequestSchema>;

export const WalkForwardRunSchema = ResearchRunBaseSchema.extend({
  window_count: z.number(),
  passed_window_count: z.number(),
  metrics: MetricsSchema,
}).passthrough();
export type WalkForwardRun = z.infer<typeof WalkForwardRunSchema>;

export const WalkForwardRunListSchema = z
  .object({
    runs: z.array(WalkForwardRunSchema).default([]),
  })
  .passthrough();
export type WalkForwardRunList = z.infer<typeof WalkForwardRunListSchema>;

export const WalkForwardLengthSpecSchema = z
  .object({
    unit: z.enum(["bars", "days"]).default("days"),
    value: z.number().int().positive(),
  })
  .passthrough();

export const WalkForwardSweepParameterSchema = z
  .object({
    field: z.enum([
      "risk_per_trade_pct",
      "fixed_shares",
      "fixed_notional",
      "max_positions",
      "max_symbol_exposure_pct",
      "max_daily_loss_pct",
      "max_drawdown_pct",
    ]),
    values: z.array(z.number()).min(1),
  })
  .passthrough();

export const WalkForwardSweepConfigSchema = z
  .object({
    enabled: z.boolean().default(false),
    base_risk_plan_version_id: z.string().nullable().optional(),
    parameters: z.array(WalkForwardSweepParameterSchema).default([]),
  })
  .passthrough();

export const WalkForwardRunRequestSchema = z
  .object({
    strategy_id: z.string(),
    strategy_version_id: z.string(),
    symbols: z.array(z.string()).default([]),
    start: z.string().nullable().optional(),
    end: z.string().nullable().optional(),
    timeframe: z.string().default("1d"),
    initial_capital: z.number().nonnegative().default(0),
    cost_model: CostModelSchema.default({ commission_per_trade: 0, slippage_bps: 0 }),
    source: z.enum(["yahoo", "alpaca"]).default("yahoo"),
    adjustment_policy: z
      .enum(["split_dividend_adjusted", "split_only", "raw"])
      .default("split_dividend_adjusted"),
    window_mode: z.enum(["rolling", "anchored"]).default("rolling"),
    is_length: WalkForwardLengthSpecSchema.default({ unit: "days", value: 180 }),
    oos_length: WalkForwardLengthSpecSchema.default({ unit: "days", value: 60 }),
    step: WalkForwardLengthSpecSchema.nullable().optional(),
    max_folds: z.number().int().positive().nullable().optional(),
    selection_criterion: z
      .enum(["sharpe", "sortino", "calmar", "expectancy", "max_dd_bounded_sharpe", "hit_rate"])
      .default("max_dd_bounded_sharpe"),
    sweep: WalkForwardSweepConfigSchema.nullable().optional(),
    monte_carlo: MonteCarloConfigSchema.nullable().optional(),
    fold_pass_threshold_sharpe: z.number().default(0),
    score_weights: z.record(z.number()).nullable().optional(),
    ship_thresholds: z.record(z.number()).nullable().optional(),
    // Legacy placeholder fields
    window_count: z.number().nonnegative().default(0),
    passed_window_count: z.number().nonnegative().default(0),
    metrics: MetricsSchema,
  })
  .passthrough();
export type WalkForwardRunRequest = z.infer<typeof WalkForwardRunRequestSchema>;

export const WalkForwardRiskPlanRecommendationSchema = z
  .object({
    source: z.string().default("walk_forward"),
    candidate_risk_plan_version_id: z.string().nullable().optional(),
    parameters: z.record(z.unknown()).default({}),
    score: z.number().optional(),
    stability_metrics: z.record(z.unknown()).default({}),
    drawdown_metrics: z.record(z.unknown()).default({}),
    out_of_sample_metrics: z.record(z.unknown()).default({}),
    explanation: z.string().optional(),
  })
  .passthrough();
export type WalkForwardRiskPlanRecommendation = z.infer<
  typeof WalkForwardRiskPlanRecommendationSchema
>;

export const WalkForwardCandidateRowSchema = z
  .object({
    parameters: z.record(z.unknown()).default({}),
    oos_sharpe: z.number().optional(),
    oos_max_dd: z.number().optional(),
    oos_return: z.number().optional(),
    oos_hit_rate: z.number().optional(),
    stability: z.number().optional(),
    picked_in_folds: z.number().int().nonnegative().optional(),
    score: z.number().optional(),
    recommended: z.boolean().default(false),
  })
  .passthrough();
export type WalkForwardCandidateRow = z.infer<typeof WalkForwardCandidateRowSchema>;

export const CancelRunRequestSchema = z.object({
  reason: z.string().min(1),
});
export type CancelRunRequest = z.infer<typeof CancelRunRequestSchema>;

import { api } from "./client";
import {
  BacktestMetricsResponseSchema,
  BacktestResultsResponseSchema,
  BacktestRunListSchema,
  BacktestRunSchema,
  OptimizationRunListSchema,
  OptimizationRunSchema,
  SimLabBatchRunResponseSchema,
  SimulationRunSchema,
  SimulationSessionListSchema,
  WalkForwardRunListSchema,
  WalkForwardRunSchema,
  type BacktestMetricsResponse,
  type BacktestResultsResponse,
  type BacktestRun,
  type BacktestRunList,
  type BacktestRunRequest,
  type CancelRunRequest,
  type OptimizationRun,
  type OptimizationRunList,
  type OptimizationRunRequest,
  type SimLabBatchRunRequest,
  type SimLabBatchRunResponse,
  type SimulationRun,
  type SimulationRunRequest,
  type SimulationSessionList,
  type SimulationSessionRequest,
  type WalkForwardRun,
  type WalkForwardRunList,
  type WalkForwardRunRequest,
} from "./schemas/researchRuns";

/**
 * Backtests now live under the canonical /api/v1/research/backtests
 * namespace. The legacy /api/v1/backtests path is still registered
 * for backward compat but the typed client targets the research path
 * exclusively so additive evidence fields (results, status_history,
 * regime_tags, per_regime_metrics) flow through naturally.
 */
export const BacktestsApi = {
  list: (): Promise<BacktestRunList> =>
    api.get(BacktestRunListSchema, "/api/v1/research/backtests"),
  create: (req: BacktestRunRequest): Promise<BacktestRun> =>
    api.post(BacktestRunSchema, "/api/v1/research/backtests", req),
  get: (runId: string): Promise<BacktestRun> =>
    api.get(BacktestRunSchema, `/api/v1/research/backtests/${runId}`),
  cancel: (runId: string, req: CancelRunRequest): Promise<BacktestRun> =>
    api.post(BacktestRunSchema, `/api/v1/research/backtests/${runId}/cancel`, req),
  results: (runId: string): Promise<BacktestResultsResponse> =>
    api.get(BacktestResultsResponseSchema, `/api/v1/research/backtests/${runId}/results`),
  metrics: (runId: string): Promise<BacktestMetricsResponse> =>
    api.get(BacktestMetricsResponseSchema, `/api/v1/research/backtests/${runId}/metrics`),
};

export const SimLabApi = {
  listSessions: (): Promise<SimulationSessionList> =>
    api.get(SimulationSessionListSchema, "/api/v1/sim-lab/sessions"),
  createSession: (req: SimulationSessionRequest): Promise<SimulationRun> =>
    api.post(SimulationRunSchema, "/api/v1/sim-lab/sessions", req),
  getSession: (sessionId: string): Promise<SimulationRun> =>
    api.get(SimulationRunSchema, `/api/v1/sim-lab/sessions/${sessionId}`),
  archiveSession: (sessionId: string): Promise<SimulationRun> =>
    api.del(SimulationRunSchema, `/api/v1/sim-lab/sessions/${sessionId}`),
  runSession: (sessionId: string, req: SimulationRunRequest): Promise<SimulationRun> =>
    api.post(SimulationRunSchema, `/api/v1/sim-lab/sessions/${sessionId}/run`, req),
  results: (sessionId: string): Promise<SimulationRun> =>
    api.get(SimulationRunSchema, `/api/v1/sim-lab/sessions/${sessionId}/results`),

  // Deterministic fixed-window historical replay (gate C1). Persists a
  // SimulationRunEvidence and returns events/orders/fills/positions/trades/
  // equity_curve alongside the durable run record.
  batchRun: (req: SimLabBatchRunRequest): Promise<SimLabBatchRunResponse> =>
    api.post(SimLabBatchRunResponseSchema, "/api/v1/research/sim_lab/runs", req),

  // Build the WS path for the deterministic streaming replay (gate C2/C4).
  // Caller hands the result to `useWS` along with `SimLabStreamMessageSchema`.
  streamPath: (req: SimLabBatchRunRequest): string => {
    const params = new URLSearchParams({
      strategy_id: req.strategy_id,
      strategy_version_id: req.strategy_version_id,
      strategy_controls_version_id: req.strategy_controls_version_id,
      execution_plan_version_id: req.execution_plan_version_id,
      risk_plan_version_id: req.risk_plan_version_id,
      scenario_name: req.scenario_name,
      universe: req.universe.join(","),
      timeframe: req.timeframe ?? "5m",
      start: req.start,
      end: req.end,
      initial_cash: String(req.initial_cash ?? 100_000),
      bar_count: String(req.bar_count ?? 12),
    });
    return `/api/v1/research/sim_lab/stream?${params.toString()}`;
  },
};

export const OptimizationApi = {
  list: (): Promise<OptimizationRunList> =>
    api.get(OptimizationRunListSchema, "/api/v1/optimization/runs"),
  create: (req: OptimizationRunRequest): Promise<OptimizationRun> =>
    api.post(OptimizationRunSchema, "/api/v1/optimization/runs", req),
  get: (runId: string): Promise<OptimizationRun> =>
    api.get(OptimizationRunSchema, `/api/v1/optimization/runs/${runId}`),
  archive: (runId: string): Promise<OptimizationRun> =>
    api.del(OptimizationRunSchema, `/api/v1/optimization/runs/${runId}`),
};

export const WalkForwardApi = {
  list: (): Promise<WalkForwardRunList> =>
    api.get(WalkForwardRunListSchema, "/api/v1/walk-forward/runs"),
  create: (req: WalkForwardRunRequest): Promise<WalkForwardRun> =>
    api.post(WalkForwardRunSchema, "/api/v1/walk-forward/runs", req),
  get: (runId: string): Promise<WalkForwardRun> =>
    api.get(WalkForwardRunSchema, `/api/v1/walk-forward/runs/${runId}`),
  archive: (runId: string): Promise<WalkForwardRun> =>
    api.del(WalkForwardRunSchema, `/api/v1/walk-forward/runs/${runId}`),
};

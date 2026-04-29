import { api } from "./client";
import {
  ResearchJobListSchema,
  ResearchJobSummarySchema,
  type ResearchJobList,
  type ResearchJobSubmitRequest,
  type ResearchJobSummary,
} from "./schemas/researchJobs";

/**
 * Async research-job API.
 *
 * Doctrine: the existing sync POSTs (/api/v1/research/backtests,
 * /api/v1/walk-forward/runs, /api/v1/optimization/runs) still work for
 * tests + small runs. Operator-driven runs go through these endpoints so
 * the drawer returns immediately and the JobMonitor surfaces progress +
 * cancellation.
 */
export const ResearchJobsApi = {
  submitBacktest: (req: ResearchJobSubmitRequest): Promise<ResearchJobSummary> =>
    api.post(ResearchJobSummarySchema, "/api/v1/research/jobs/backtest", req),

  submitWalkForward: (req: ResearchJobSubmitRequest): Promise<ResearchJobSummary> =>
    api.post(ResearchJobSummarySchema, "/api/v1/research/jobs/walk-forward", req),

  submitOptimization: (req: ResearchJobSubmitRequest): Promise<ResearchJobSummary> =>
    api.post(ResearchJobSummarySchema, "/api/v1/research/jobs/optimization", req),

  list: (params?: { status?: string; kind?: string; limit?: number }): Promise<ResearchJobList> => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.kind) query.set("kind", params.kind);
    if (params?.limit != null) query.set("limit", String(params.limit));
    const qs = query.toString();
    return api.get(ResearchJobListSchema, `/api/v1/research/jobs${qs ? `?${qs}` : ""}`);
  },

  get: (jobId: string): Promise<ResearchJobSummary> =>
    api.get(ResearchJobSummarySchema, `/api/v1/research/jobs/${jobId}`),

  cancel: (jobId: string): Promise<ResearchJobSummary> =>
    api.post(ResearchJobSummarySchema, `/api/v1/research/jobs/${jobId}/cancel`, {}),
};

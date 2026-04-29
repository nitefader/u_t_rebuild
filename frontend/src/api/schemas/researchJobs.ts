import { z } from "zod";

/**
 * Research job schemas — async dispatch wrappers around the existing
 * Backtest / Walk-Forward / Optimization run shapes.
 *
 * Doctrine: schemas .passthrough() so additive backend fields cannot
 * reject the typed client. ``status`` and ``kind`` stay z.string() so
 * future enum members don't crash the read path.
 */

export const ResearchJobSummarySchema = z
  .object({
    job_id: z.string(),
    kind: z.string(),
    status: z.string(),
    progress_current: z.number().int().nonnegative().default(0),
    progress_total: z.number().int().nonnegative().default(0),
    progress_label: z.string().default(""),
    result_run_id: z.string().nullable().optional(),
    error: z.string().nullable().optional(),
    created_at: z.string(),
    started_at: z.string().nullable().optional(),
    finished_at: z.string().nullable().optional(),
  })
  .passthrough();
export type ResearchJobSummary = z.infer<typeof ResearchJobSummarySchema>;

export const ResearchJobListSchema = z
  .object({
    jobs: z.array(ResearchJobSummarySchema).default([]),
  })
  .passthrough();
export type ResearchJobList = z.infer<typeof ResearchJobListSchema>;

export const ResearchJobSubmitRequestSchema = z
  .object({
    request: z.record(z.unknown()),
    operator_session_id: z.string().nullable().optional(),
    metadata: z.record(z.unknown()).default({}),
  })
  .passthrough();
export type ResearchJobSubmitRequest = z.infer<typeof ResearchJobSubmitRequestSchema>;

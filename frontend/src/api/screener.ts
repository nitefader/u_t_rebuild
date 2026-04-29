import { api } from "./client";
import { z } from "zod";
import {
  MarketListRunResponseSchema,
  MarketListsResponseSchema,
  SaveAsWatchlistRequestSchema,
  SaveAsWatchlistResponseSchema,
  ScreenerAIInterpretRequestSchema,
  ScreenerAIInterpretResponseSchema,
  ScreenerCreateRequestSchema,
  ScreenerFieldsResponseSchema,
  ScreenerFromTemplateRequestSchema,
  ScreenerListResponseSchema,
  ScreenerMetricsResponseSchema,
  ScreenerPatchRequestSchema,
  ScreenerPresetsResponseSchema,
  ScreenerRunDiffSchema,
  ScreenerResponseSchema,
  ScreenerRunListResponseSchema,
  ScreenerRerunRequestSchema,
  ScreenerRunRequestSchema,
  ScreenerRunSchema,
  ScreenerTemplatesResponseSchema,
  ScreenerVersionSchema,
  type MarketListRunResponse,
  type MarketListsResponse,
  type SaveAsWatchlistRequest,
  type SaveAsWatchlistResponse,
  type ScreenerAIInterpretRequest,
  type ScreenerAIInterpretResponse,
  type ScreenerCreateRequest,
  type ScreenerFieldsResponse,
  type ScreenerFromTemplateRequest,
  type ScreenerListResponse,
  type ScreenerPatchRequest,
  type ScreenerResponse,
  type ScreenerRun,
  type ScreenerRunDiff,
  type ScreenerRunListResponse,
  type ScreenerRerunRequest,
  type ScreenerRunRequest,
  type ScreenerTemplatesResponse,
  type ScreenerVersion,
} from "./schemas/screener";

/**
 * Typed client for the Screener API.
 *
 * Doctrine guards (per AGENTS.md):
 *   - Run / save / preset / metrics endpoints never mutate Watchlists.
 *   - Save-as-watchlist creates a NEW Watchlist via the existing
 *     /api/v1/watchlists POST.
 *   - All POST bodies validated against the typed Request schemas before
 *     hitting the wire so operator typos surface client-side.
 */

function ensureCreate(req: ScreenerCreateRequest): ScreenerCreateRequest {
  const parsed = ScreenerCreateRequestSchema.safeParse(req);
  if (!parsed.success) {
    throw new Error(
      `screener create request invalid: ${parsed.error.issues
        .slice(0, 3)
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ")}`,
    );
  }
  return parsed.data;
}

function ensurePatch(req: ScreenerPatchRequest): ScreenerPatchRequest {
  return ScreenerPatchRequestSchema.parse(req);
}

function ensureRun(req: ScreenerRunRequest): ScreenerRunRequest {
  return ScreenerRunRequestSchema.parse(req);
}

function ensureRerun(req: ScreenerRerunRequest): ScreenerRerunRequest {
  return ScreenerRerunRequestSchema.parse(req);
}

function ensureSave(req: SaveAsWatchlistRequest): SaveAsWatchlistRequest {
  return SaveAsWatchlistRequestSchema.parse(req);
}

function ensureFromTemplate(req: ScreenerFromTemplateRequest): ScreenerFromTemplateRequest {
  return ScreenerFromTemplateRequestSchema.parse(req);
}

function ensureAiInterpret(req: ScreenerAIInterpretRequest): ScreenerAIInterpretRequest {
  return ScreenerAIInterpretRequestSchema.parse(req);
}

export const ScreenerApi = {
  list: (): Promise<ScreenerListResponse> =>
    api.get(ScreenerListResponseSchema, "/api/v1/screeners"),

  presets: () => api.get(ScreenerPresetsResponseSchema, "/api/v1/screeners/presets"),

  metrics: () => api.get(ScreenerMetricsResponseSchema, "/api/v1/screeners/metrics"),

  fields: (): Promise<ScreenerFieldsResponse> =>
    api.get(ScreenerFieldsResponseSchema, "/api/v1/screeners/fields"),

  templates: (): Promise<ScreenerTemplatesResponse> =>
    api.get(ScreenerTemplatesResponseSchema, "/api/v1/screeners/templates"),

  marketLists: (): Promise<MarketListsResponse> =>
    api.get(MarketListsResponseSchema, "/api/v1/market-lists"),

  createFromTemplate: (req: ScreenerFromTemplateRequest): Promise<ScreenerResponse> =>
    api.post(ScreenerResponseSchema, "/api/v1/screeners/from-template", ensureFromTemplate(req)),

  interpretAi: (req: ScreenerAIInterpretRequest): Promise<ScreenerAIInterpretResponse> =>
    api.post(
      ScreenerAIInterpretResponseSchema,
      "/api/v1/screeners/ai/interpret",
      ensureAiInterpret(req),
    ),

  runMarketList: (templateKey: string): Promise<MarketListRunResponse> =>
    api.post(MarketListRunResponseSchema, `/api/v1/market-lists/${templateKey}/run`),

  create: (req: ScreenerCreateRequest): Promise<ScreenerResponse> =>
    api.post(ScreenerResponseSchema, "/api/v1/screeners", ensureCreate(req)),

  get: (screenerId: string): Promise<ScreenerResponse> =>
    api.get(ScreenerResponseSchema, `/api/v1/screeners/${screenerId}`),

  patch: (screenerId: string, req: ScreenerPatchRequest): Promise<ScreenerResponse> =>
    api.patch(ScreenerResponseSchema, `/api/v1/screeners/${screenerId}`, ensurePatch(req)),

  delete: (screenerId: string): Promise<unknown> =>
    api.post(z.unknown(), `/api/v1/screeners/${screenerId}/delete`),

  archive: (screenerId: string): Promise<ScreenerResponse> =>
    api.post(ScreenerResponseSchema, `/api/v1/screeners/${screenerId}/archive`),

  addVersion: (screenerId: string, req: ScreenerCreateRequest): Promise<ScreenerVersion> =>
    api.post(
      ScreenerVersionSchema,
      `/api/v1/screeners/${screenerId}/versions`,
      ensureCreate(req),
    ),

  run: (screenerId: string, req: ScreenerRunRequest = {}): Promise<ScreenerRun> =>
    api.post(ScreenerRunSchema, `/api/v1/screeners/${screenerId}/run`, ensureRun(req)),

  listRuns: (screenerId: string): Promise<ScreenerRunListResponse> =>
    api.get(ScreenerRunListResponseSchema, `/api/v1/screeners/${screenerId}/runs`),

  getRun: (runId: string): Promise<ScreenerRun> =>
    api.get(ScreenerRunSchema, `/api/v1/screeners/runs/${runId}`),

  rerun: (runId: string, req: ScreenerRerunRequest = {}): Promise<ScreenerRun> =>
    api.post(ScreenerRunSchema, `/api/v1/screeners/runs/${runId}/rerun`, ensureRerun(req)),

  diffRuns: (runId: string, againstRunId: string): Promise<ScreenerRunDiff> =>
    api.get(
      ScreenerRunDiffSchema,
      `/api/v1/screeners/runs/${runId}/diff?against_run_id=${encodeURIComponent(againstRunId)}`,
    ),

  saveRunAsWatchlist: (
    runId: string,
    req: SaveAsWatchlistRequest,
  ): Promise<SaveAsWatchlistResponse> =>
    api.post(
      SaveAsWatchlistResponseSchema,
      `/api/v1/screeners/runs/${runId}/save-as-watchlist`,
      ensureSave(req),
    ),
};

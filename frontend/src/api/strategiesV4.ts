import { z } from "zod";
import { api, apiFetch } from "./client";
import {
  AISeedFillResponseSchema,
  ExpressionValidateResultSchema,
  FeaturesResponseSchema,
  StrategyVersionV4Schema,
  ValidateDraftResponseSchema,
  type AISeedFillResponse,
  type CatalogEntry,
  type ExpressionValidateResult,
  type StrategyVersionV4,
  type StrategyVersionV4Draft,
  type ValidateDraftResponse,
  type ValidationStatusV4,
} from "./schemas/strategiesV4";

const EXPR_BASE = "/api/v1/strategies/expression";
const V4_BASE = "/api/v1/strategies/v4";

// ------------------------------------------------------------------
// Strategy head summary (global list)
// ------------------------------------------------------------------

export const StrategyHeadSummarySchema = z.object({
  strategy_v4_id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  head_version: z.number().int(),
  head_version_id: z.string(),
  total_versions: z.number().int(),
  created_at: z.string(),
  updated_at: z.string(),
});

export type StrategyHeadSummary = z.infer<typeof StrategyHeadSummarySchema>;

export async function listAllHeads(): Promise<StrategyHeadSummary[]> {
  return api.get(z.array(StrategyHeadSummarySchema), `${V4_BASE}/`);
}

// ------------------------------------------------------------------
// Expression API
// ------------------------------------------------------------------

export async function validateExpressionAbortable(
  src: string,
  variableNames: string[],
  timeframeVariableNames: string[],
  signal: AbortSignal,
): Promise<ExpressionValidateResult> {
  const res = await apiFetch(`${EXPR_BASE}/validate`, {
    method: "POST",
    body: {
      src,
      variables: variableNames,
      timeframe_variables: timeframeVariableNames,
    },
    signal,
  });
  const raw = (await res.json()) as unknown;
  return ExpressionValidateResultSchema.parse(raw);
}

let _featureCache: CatalogEntry[] | null = null;

export async function listExpressionFeatures(): Promise<CatalogEntry[]> {
  if (_featureCache) return _featureCache;
  const data = await api.get(FeaturesResponseSchema, `${EXPR_BASE}/features`);
  _featureCache = data.features;
  return _featureCache;
}

export async function mirrorExpression(src: string): Promise<{ mirrored_text: string }> {
  const schema = z.object({ mirrored_text: z.string() });
  return api.post(schema, `${EXPR_BASE}/mirror`, { src });
}

// ------------------------------------------------------------------
// StrategyVersion v4
// ------------------------------------------------------------------

export async function validateDraft(draft: StrategyVersionV4Draft): Promise<ValidateDraftResponse> {
  return api.post(ValidateDraftResponseSchema, `${V4_BASE}/draft`, { draft });
}

export async function saveDraft(draft: StrategyVersionV4Draft): Promise<StrategyVersionV4> {
  return api.post(StrategyVersionV4Schema, `${V4_BASE}/`, { draft });
}

export async function loadVersion(id: string): Promise<StrategyVersionV4> {
  return api.get(StrategyVersionV4Schema, `${V4_BASE}/${id}`);
}

export async function listByStrategy(strategyId: string): Promise<StrategyVersionV4[]> {
  const schema = z.array(StrategyVersionV4Schema);
  return api.get(schema, `${V4_BASE}/by-strategy/${strategyId}`);
}

export async function editStrategy(
  strategyId: string,
  draft: StrategyVersionV4Draft,
): Promise<StrategyVersionV4> {
  return api.put(StrategyVersionV4Schema, `${V4_BASE}/by-strategy/${strategyId}`, { draft });
}

export async function duplicateVersion(
  versionId: string,
  newName: string,
): Promise<StrategyVersionV4> {
  return api.post(StrategyVersionV4Schema, `${V4_BASE}/${versionId}/duplicate`, {
    new_name: newName,
  });
}

export async function deleteStrategy(strategyId: string): Promise<void> {
  await apiFetch(`${V4_BASE}/by-strategy/${strategyId}`, { method: "DELETE" });
}

// ------------------------------------------------------------------
// AI seed-fill
// ------------------------------------------------------------------

export async function aiFillStrategy(
  prompt: string,
  currentDraft?: StrategyVersionV4Draft,
): Promise<AISeedFillResponse> {
  return api.post(AISeedFillResponseSchema, `${V4_BASE}/ai-fill`, {
    prompt,
    ...(currentDraft !== undefined ? { current_draft: currentDraft } : {}),
  });
}

// Re-export types for convenience
export type {
  AISeedFillResponse,
  CatalogEntry,
  ExpressionValidateResult,
  StrategyVersionV4,
  ValidationStatusV4,
};

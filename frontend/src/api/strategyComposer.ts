import { z } from "zod";
import { api } from "./client";
import {
  AIComposerRequestSchema,
  ConditionParseRequestSchema,
  ConditionParseResponseSchema,
  FeatureAliasMapSchema,
  FeatureCatalogResponseSchema,
  FeaturePlanPreviewRequestSchema,
  FeaturePlanPreviewSchema,
  FeatureReferenceValidationRequestSchema,
  FeatureReferenceValidationSchema,
  ReuseMatchRequestSchema,
  ReuseMatchResponseSchema,
  StrategyDraftSaveRequestSchema,
  StrategyDraftSaveResponseSchema,
  StrategyDraftSchema,
  type AIComposerRequest,
  type ConditionParseRequest,
  type ConditionParseResponse,
  type FeatureAliasMap,
  type FeaturePlanPreview,
  type FeaturePlanPreviewRequest,
  type FeatureReferenceValidation,
  type FeatureReferenceValidationRequest,
  type ReuseMatchRequest,
  type ReuseMatchResponse,
  type StrategyDraft,
  type StrategyDraftSaveRequest,
  type StrategyDraftSaveResponse,
} from "./schemas/strategyComposer";

/**
 * Typed client for the Strategy Builder + AI Composer endpoints.
 *
 * Contract source: docs/system_rebuild_outputs/STRATEGY_BUILDER_FRONTEND_CONTRACT.md
 *
 * All routes go through `api.*` (X-UTOS-API-Key header + zod parse + ApiError surfacing).
 *
 * Doctrine guards:
 *   - The save() endpoint creates draft-only StrategyVersion. Never deploys,
 *     never attaches an Account, never submits an order, never claims live
 *     readiness.
 *   - Validate / parse / preview never persist; safe to call on every keystroke
 *     (callers should debounce).
 */

// Validate the request shape before POST so we surface bad payloads early
// rather than waiting for the backend to 422.
function ensure<T extends z.ZodTypeAny>(schema: T, value: unknown): z.infer<T> {
  const parsed = schema.safeParse(value);
  if (!parsed.success) {
    throw new Error(
      `request payload failed validation: ${parsed.error.issues
        .slice(0, 3)
        .map((i) => `${i.path.join(".")}: ${i.message}`)
        .join("; ")}`,
    );
  }
  return parsed.data;
}

export const StrategyComposerApi = {
  features: (): Promise<z.infer<typeof FeatureCatalogResponseSchema>> =>
    api.get(FeatureCatalogResponseSchema, "/api/v1/strategies/builder/features"),

  featureAliases: (): Promise<FeatureAliasMap> =>
    api.get(FeatureAliasMapSchema, "/api/v1/strategies/builder/features/aliases"),

  validateFeatures: (req: FeatureReferenceValidationRequest): Promise<FeatureReferenceValidation> =>
    api.post(
      FeatureReferenceValidationSchema,
      "/api/v1/strategies/builder/features/validate",
      ensure(FeatureReferenceValidationRequestSchema, req),
    ),

  planPreview: (req: FeaturePlanPreviewRequest): Promise<FeaturePlanPreview> =>
    api.post(
      FeaturePlanPreviewSchema,
      "/api/v1/strategies/builder/features/plan-preview",
      ensure(FeaturePlanPreviewRequestSchema, req),
    ),

  parseCondition: (req: ConditionParseRequest): Promise<ConditionParseResponse> =>
    api.post(
      ConditionParseResponseSchema,
      "/api/v1/strategies/builder/conditions/parse",
      ensure(ConditionParseRequestSchema, req),
    ),

  reuseMatches: (req: ReuseMatchRequest): Promise<ReuseMatchResponse> =>
    api.post(
      ReuseMatchResponseSchema,
      "/api/v1/strategies/builder/reuse-matches",
      ensure(ReuseMatchRequestSchema, req),
    ),

  composerPreview: (req: AIComposerRequest): Promise<StrategyDraft> =>
    api.post(
      StrategyDraftSchema,
      "/api/v1/strategies/composer/preview",
      ensure(AIComposerRequestSchema, req),
    ),

  saveDraft: (req: StrategyDraftSaveRequest): Promise<StrategyDraftSaveResponse> =>
    api.post(
      StrategyDraftSaveResponseSchema,
      "/api/v1/strategies/composer/drafts",
      ensure(StrategyDraftSaveRequestSchema, req),
    ),
};

import { api } from "./client";
import {
  AccountRiskPlanAssignmentSchema,
  CreateRiskPlanRequestSchema,
  NewRiskPlanVersionRequestSchema,
  PatchRiskPlanRequestSchema,
  PutAccountRiskPlanRequestSchema,
  RiskPlanAiDraftRequestSchema,
  RiskPlanAiDraftResponseSchema,
  RiskPlanDetailEnvelopeSchema,
  RiskPlanListResponseSchema,
  RiskPlanVersionListResponseSchema,
  RiskPlanVersionSchema,
  type AccountRiskPlanAssignment,
  type CreateRiskPlanRequest,
  type NewRiskPlanVersionRequest,
  type PatchRiskPlanRequest,
  type PutAccountRiskPlanRequest,
  type RiskPlanAiDraftRequest,
  type RiskPlanAiDraftResponse,
  type RiskPlanDetail,
  type RiskPlanDetailEnvelope,
  type RiskPlanListResponse,
  type RiskPlanVersion,
  type RiskPlanVersionListResponse,
} from "./schemas/riskPlans";

/**
 * Flatten the backend's `{risk_plan, versions, active_version, ...}`
 * envelope into the `RiskPlanDetail` shape consumers expect.
 *
 * Backend (Codex) ships enrichment fields at the top level alongside the
 * `risk_plan` wrapper: `active_version` / `active_version_id` and the
 * §9.3 panes `linked_accounts` / `backtest_usage` / `decision_stats`.
 * We trust those when present and fall back to deriving `active_version`
 * from `versions` only if backend hasn't supplied it.
 */
function flattenRiskPlanDetail(envelope: RiskPlanDetailEnvelope): RiskPlanDetail {
  const versions = envelope.versions ?? [];
  const fallback =
    versions.find((v) => v.status === "active") ??
    (versions.length > 0 ? versions[versions.length - 1] : null);
  const effectiveActive: RiskPlanVersion | null =
    envelope.active_version ?? fallback ?? null;
  return {
    ...envelope.risk_plan,
    active_version: effectiveActive,
    active_version_id:
      envelope.active_version_id ?? effectiveActive?.risk_plan_version_id ?? null,
    versions,
    linked_accounts: envelope.linked_accounts ?? [],
    backtest_usage: envelope.backtest_usage ?? [],
    decision_stats: envelope.decision_stats ?? null,
  };
}

/**
 * RiskPlansApi.
 *
 * Contract: `RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT.md` §8.1 + §8.2.
 * Backend ownership: Operation Turtle Shell (B1..B4).
 *
 * The Zod schemas use `.passthrough()` so additive backend fields do not
 * break the typed UI client. Until backend ships, callers handle the empty
 * case via `LoadingState`/`ErrorState` like every other route.
 */
export const RiskPlansApi = {
  list: (): Promise<RiskPlanListResponse> =>
    api.get(RiskPlanListResponseSchema, "/api/v1/risk-plans"),

  get: (riskPlanId: string): Promise<RiskPlanDetail> =>
    api
      .get(RiskPlanDetailEnvelopeSchema, `/api/v1/risk-plans/${riskPlanId}`)
      .then(flattenRiskPlanDetail),

  create: (body: CreateRiskPlanRequest): Promise<RiskPlanDetail> =>
    api
      .post(
        RiskPlanDetailEnvelopeSchema,
        "/api/v1/risk-plans",
        CreateRiskPlanRequestSchema.parse(body),
      )
      .then(flattenRiskPlanDetail),

  patch: (riskPlanId: string, body: PatchRiskPlanRequest): Promise<RiskPlanDetail> =>
    api
      .patch(
        RiskPlanDetailEnvelopeSchema,
        `/api/v1/risk-plans/${riskPlanId}`,
        PatchRiskPlanRequestSchema.parse(body),
      )
      .then(flattenRiskPlanDetail),

  listVersions: (riskPlanId: string): Promise<RiskPlanVersionListResponse> =>
    api.get(RiskPlanVersionListResponseSchema, `/api/v1/risk-plans/${riskPlanId}/versions`),

  newVersion: (
    riskPlanId: string,
    body: NewRiskPlanVersionRequest,
  ): Promise<RiskPlanVersion> =>
    api.post(
      RiskPlanVersionSchema,
      `/api/v1/risk-plans/${riskPlanId}/versions`,
      NewRiskPlanVersionRequestSchema.parse(body),
    ),

  activate: (riskPlanId: string, versionId?: string): Promise<RiskPlanDetail> =>
    api
      .post(
        RiskPlanDetailEnvelopeSchema,
        `/api/v1/risk-plans/${riskPlanId}/activate`,
        versionId ? { risk_plan_version_id: versionId } : {},
      )
      .then(flattenRiskPlanDetail),

  archive: (riskPlanId: string): Promise<RiskPlanDetail> =>
    api
      .post(RiskPlanDetailEnvelopeSchema, `/api/v1/risk-plans/${riskPlanId}/archive`, {})
      .then(flattenRiskPlanDetail),

  aiDraft: (body: RiskPlanAiDraftRequest): Promise<RiskPlanAiDraftResponse> =>
    api.post(
      RiskPlanAiDraftResponseSchema,
      "/api/v1/risk-plans/ai-draft",
      RiskPlanAiDraftRequestSchema.parse(body),
    ),

  getAccountAssignment: (accountId: string): Promise<AccountRiskPlanAssignment> =>
    api.get(AccountRiskPlanAssignmentSchema, `/api/v1/accounts/${accountId}/risk-plan`),

  putAccountAssignment: (
    accountId: string,
    body: PutAccountRiskPlanRequest,
  ): Promise<AccountRiskPlanAssignment> =>
    api.put(
      AccountRiskPlanAssignmentSchema,
      `/api/v1/accounts/${accountId}/risk-plan`,
      PutAccountRiskPlanRequestSchema.parse(body),
    ),
};

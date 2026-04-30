import { api } from "./client";
import {
  AccountRestrictionsSchema,
  AccountRiskConfigSchema,
  AccountRiskPlanMapSchema,
  type AccountRestrictions,
  type AccountRiskConfig,
  type AccountRiskPlanMap,
  type AccountRiskPlanMapUpdateRequest,
} from "./schemas/risk";

export const RiskApi = {
  getRiskConfig: (accountId: string): Promise<AccountRiskConfig> =>
    api.get(AccountRiskConfigSchema, `/api/v1/broker-accounts/${accountId}/risk-config`),
  putRiskConfig: (
    accountId: string,
    config: Omit<AccountRiskConfig, "account_id" | "version" | "updated_at">,
  ): Promise<AccountRiskConfig> =>
    api.put(AccountRiskConfigSchema, `/api/v1/broker-accounts/${accountId}/risk-config`, config),
  getRestrictions: (accountId: string): Promise<AccountRestrictions> =>
    api.get(AccountRestrictionsSchema, `/api/v1/broker-accounts/${accountId}/restrictions`),
  putRestrictions: (
    accountId: string,
    restrictions: Omit<AccountRestrictions, "account_id" | "version" | "updated_at">,
  ): Promise<AccountRestrictions> =>
    api.put(
      AccountRestrictionsSchema,
      `/api/v1/broker-accounts/${accountId}/restrictions`,
      restrictions,
    ),
};

/**
 * RiskPlanMapApi — AccountRiskPlanMap CRUD.
 *
 * Backend routes (Slice B):
 *   GET /api/v1/broker-accounts/{id}/risk-plan-map
 *   PUT /api/v1/broker-accounts/{id}/risk-plan-map
 *
 * Each PUT is a per-horizon atomic operation: pass `risk_plan_version_id: null`
 * to clear the row for that horizon.
 */
export const RiskPlanMapApi = {
  get: (accountId: string): Promise<AccountRiskPlanMap> =>
    api.get(AccountRiskPlanMapSchema, `/api/v1/broker-accounts/${accountId}/risk-plan-map`),

  update: (
    accountId: string,
    request: AccountRiskPlanMapUpdateRequest,
  ): Promise<AccountRiskPlanMap> =>
    api.put(
      AccountRiskPlanMapSchema,
      `/api/v1/broker-accounts/${accountId}/risk-plan-map`,
      request,
    ),
};

import { api } from "./client";
import {
  AccountRestrictionsSchema,
  AccountRiskConfigSchema,
  type AccountRestrictions,
  type AccountRiskConfig,
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

import { api } from "./client";
import {
  BrokerAccountCredentialUpdateResponseSchema,
  BrokerAccountDeletionResponseSchema,
  BrokerAccountListResponseSchema,
  BrokerAccountResponseSchema,
  type BrokerAccountListResponse,
  type CreateBrokerAccountRequest,
} from "./schemas/accounts";

export const AccountsApi = {
  list: (): Promise<BrokerAccountListResponse> =>
    api.get(BrokerAccountListResponseSchema, "/api/v1/broker-accounts"),

  create: (req: CreateBrokerAccountRequest) =>
    api.post(BrokerAccountResponseSchema, "/api/v1/broker-accounts", req),

  updateDetails: (accountId: string, displayName: string) =>
    api.patch(BrokerAccountResponseSchema, `/api/v1/broker-accounts/${accountId}`, {
      display_name: displayName,
    }),

  replaceCredentials: (accountId: string, apiKey: string, apiSecret: string) =>
    api.put(BrokerAccountCredentialUpdateResponseSchema, `/api/v1/broker-accounts/${accountId}/credentials`, {
      api_key: apiKey,
      api_secret: apiSecret,
    }),

  delete: (accountId: string, confirmDisplayName: string, confirmMode: string) =>
    api.post(BrokerAccountDeletionResponseSchema, `/api/v1/broker-accounts/${accountId}/delete`, {
      confirm_display_name: confirmDisplayName,
      confirm_mode: confirmMode,
    }),

  /**
   * M11 Guardian Assignment — set or remove the Account's Guardian Deployment.
   * Backend route owned by Codex (queued in `INBOX_CODEX.md` 2026-05-02).
   * Pass `null` to clear; pass a deployment_id to assign.
   */
  setGuardian: (accountId: string, deploymentId: string | null) =>
    api.put(BrokerAccountResponseSchema, `/api/v1/broker-accounts/${accountId}/guardian`, {
      guardian_deployment_id: deploymentId,
    }),
};

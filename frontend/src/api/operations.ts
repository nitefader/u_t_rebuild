import { api } from "./client";
import {
  AccountOperationsSchema,
  ControlCommandResponseSchema,
  FlattenRequestResponseSchema,
  OrderDetailSchema,
  RuntimeOverviewSchema,
  type AccountOperations,
  type ControlCommandResponse,
  type FlattenRequestResponse,
  type OrderDetail,
  type RuntimeOverview,
} from "./schemas/operations";

export interface ControlCommandPayload {
  reason: string;
}

export const OperationsApi = {
  overview: (): Promise<RuntimeOverview> =>
    api.get(RuntimeOverviewSchema, "/api/v1/operations/overview"),

  account: (accountId: string): Promise<AccountOperations> =>
    api.get(AccountOperationsSchema, `/api/v1/operations/accounts/${accountId}`),

  pauseAccount: (accountId: string, reason: string): Promise<ControlCommandResponse> =>
    api.post(ControlCommandResponseSchema, `/api/v1/operations/accounts/${accountId}/pause`, {
      reason,
    } satisfies ControlCommandPayload),

  resumeAccount: (accountId: string, reason: string): Promise<ControlCommandResponse> =>
    api.post(ControlCommandResponseSchema, `/api/v1/operations/accounts/${accountId}/resume`, {
      reason,
    } satisfies ControlCommandPayload),

  flattenAccount: (accountId: string, reason: string): Promise<FlattenRequestResponse> =>
    api.post(FlattenRequestResponseSchema, `/api/v1/operations/accounts/${accountId}/flatten`, {
      reason,
    } satisfies ControlCommandPayload),

  pauseDeployment: (deploymentId: string, reason: string): Promise<ControlCommandResponse> =>
    api.post(ControlCommandResponseSchema, `/api/v1/operations/deployments/${deploymentId}/pause`, {
      reason,
    } satisfies ControlCommandPayload),

  resumeDeployment: (deploymentId: string, reason: string): Promise<ControlCommandResponse> =>
    api.post(ControlCommandResponseSchema, `/api/v1/operations/deployments/${deploymentId}/resume`, {
      reason,
    } satisfies ControlCommandPayload),

  flattenDeployment: (deploymentId: string, reason: string): Promise<FlattenRequestResponse> =>
    api.post(FlattenRequestResponseSchema, `/api/v1/operations/deployments/${deploymentId}/flatten`, {
      reason,
    } satisfies ControlCommandPayload),

  globalKill: (reason: string): Promise<ControlCommandResponse> =>
    api.post(ControlCommandResponseSchema, "/api/v1/operations/global/kill", {
      reason,
    } satisfies ControlCommandPayload),

  globalResume: (reason: string): Promise<ControlCommandResponse> =>
    api.post(ControlCommandResponseSchema, "/api/v1/operations/global/resume", {
      reason,
    } satisfies ControlCommandPayload),

  // Trace an external Alpaca broker order id back to internal order detail.
  // Returns 404 when no matching internal order exists; UI should surface
  // an explicit "no match" state, not a silent failure.
  lookupBrokerOrder: (brokerOrderId: string): Promise<OrderDetail> =>
    api.get(
      OrderDetailSchema,
      `/api/v1/operations/broker-orders/${encodeURIComponent(brokerOrderId)}`,
    ),
};

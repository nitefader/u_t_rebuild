import { z } from "zod";
import { api } from "./client";
import {
  DeploymentListResponseSchema,
  DeploymentResponseSchema,
  type DeploymentListResponse,
  type DeploymentResponse,
  type DeploymentWriteRequest,
} from "./schemas/deployments";

export const DeploymentsApi = {
  list: (): Promise<DeploymentListResponse> =>
    api.get(DeploymentListResponseSchema, "/api/v1/deployments"),

  create: (req: DeploymentWriteRequest): Promise<DeploymentResponse> =>
    api.post(DeploymentResponseSchema, "/api/v1/deployments", req),

  get: (id: string): Promise<DeploymentResponse> =>
    api.get(DeploymentResponseSchema, `/api/v1/deployments/${id}`),

  update: (id: string, req: DeploymentWriteRequest): Promise<DeploymentResponse> =>
    api.patch(DeploymentResponseSchema, `/api/v1/deployments/${id}`, req),

  delete: (id: string) => api.post(z.unknown(), `/api/v1/deployments/${id}/delete`),

  start: (id: string, reason: string): Promise<DeploymentResponse> =>
    api.post(DeploymentResponseSchema, `/api/v1/deployments/${id}/start`, { reason }),

  stop: (id: string, reason: string): Promise<DeploymentResponse> =>
    api.post(DeploymentResponseSchema, `/api/v1/deployments/${id}/stop`, { reason }),

  pause: (id: string, reason: string): Promise<DeploymentResponse> =>
    api.post(DeploymentResponseSchema, `/api/v1/deployments/${id}/pause`, { reason }),

  resume: (id: string, reason: string): Promise<DeploymentResponse> =>
    api.post(DeploymentResponseSchema, `/api/v1/deployments/${id}/resume`, { reason }),

  subscribe: (id: string, accountId: string): Promise<DeploymentResponse> =>
    api.post(DeploymentResponseSchema, `/api/v1/deployments/${id}/subscribe`, {
      account_id: accountId,
    }),

  unsubscribe: (id: string, accountId: string): Promise<DeploymentResponse> =>
    api.post(DeploymentResponseSchema, `/api/v1/deployments/${id}/unsubscribe`, {
      account_id: accountId,
    }),
};

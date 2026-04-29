import { z } from "zod";
import { api } from "./client";
import {
  StrategyListResponseSchema,
  StrategyResponseSchema,
  StrategyVersionRecordSchema,
  type StrategyListResponse,
  type StrategyResponse,
  type StrategyVersionPayload,
  type StrategyVersionRecord,
  type StrategyWriteRequest,
} from "./schemas/strategies";

const VersionListSchema = z.array(StrategyVersionRecordSchema);

export const StrategiesApi = {
  list: (): Promise<StrategyListResponse> =>
    api.get(StrategyListResponseSchema, "/api/v1/strategies"),

  create: (req: StrategyWriteRequest): Promise<StrategyResponse> =>
    api.post(StrategyResponseSchema, "/api/v1/strategies", req),

  get: (id: string): Promise<StrategyResponse> =>
    api.get(StrategyResponseSchema, `/api/v1/strategies/${id}`),

  update: (id: string, req: StrategyWriteRequest): Promise<StrategyResponse> =>
    api.patch(StrategyResponseSchema, `/api/v1/strategies/${id}`, req),

  delete: (id: string) => api.post(z.unknown(), `/api/v1/strategies/${id}/delete`),

  deprecate: (id: string): Promise<StrategyResponse> =>
    api.post(StrategyResponseSchema, `/api/v1/strategies/${id}/deprecate`),

  listVersions: (id: string): Promise<StrategyVersionRecord[]> =>
    api.get(VersionListSchema, `/api/v1/strategies/${id}/versions`),

  addVersion: (id: string, payload: StrategyVersionPayload): Promise<StrategyVersionRecord> =>
    api.post(StrategyVersionRecordSchema, `/api/v1/strategies/${id}/versions`, payload),

  // PATCH the *current draft* version's payload. Backend rejects with 400
  // when the version is already frozen. Returns 404 until the route lands;
  // the consuming UI surfaces an `AwaitingApiOrError` panel in that case.
  editDraftVersion: (
    id: string,
    versionId: string,
    payload: StrategyVersionPayload,
  ): Promise<StrategyVersionRecord> =>
    api.patch(
      StrategyVersionRecordSchema,
      `/api/v1/strategies/${id}/versions/${versionId}`,
      payload,
    ),

  freezeVersion: (id: string, versionId: string): Promise<StrategyVersionRecord> =>
    api.post(StrategyVersionRecordSchema, `/api/v1/strategies/${id}/versions/${versionId}/freeze`),
};

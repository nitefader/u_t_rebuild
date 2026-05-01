import { api, apiFetch } from "./client";
import {
  StrategyControlsLibraryListResponseSchema,
  StrategyControlsLibrarySchema,
  StrategyControlsVersionRecordSchema,
  StrategyControlsUsedByResponseSchema,
  type StrategyControlsDraft,
  type StrategyControlsLibrary,
  type StrategyControlsLibraryListResponse,
  type StrategyControlsUsedByResponse,
  type StrategyControlsVersionRecord,
} from "./schemas/strategyControls";

const BASE = "/api/v1/strategy-controls";

export const StrategyControlsApi = {
  list: (): Promise<StrategyControlsLibraryListResponse> =>
    api.get(StrategyControlsLibraryListResponseSchema, BASE),

  get: (id: string): Promise<StrategyControlsLibrary> =>
    api.get(StrategyControlsLibrarySchema, `${BASE}/${id}`),

  getVersion: (id: string, version: number): Promise<StrategyControlsVersionRecord> =>
    api.get(StrategyControlsVersionRecordSchema, `${BASE}/${id}/versions/${version}`),

  create: (name: string, draft: StrategyControlsDraft): Promise<StrategyControlsVersionRecord> =>
    api.post(StrategyControlsVersionRecordSchema, BASE, { name, draft }),

  edit: (id: string, draft: StrategyControlsDraft): Promise<StrategyControlsVersionRecord> =>
    api.put(StrategyControlsVersionRecordSchema, `${BASE}/${id}`, { draft }),

  duplicate: (id: string, newName: string): Promise<StrategyControlsVersionRecord> =>
    api.post(StrategyControlsVersionRecordSchema, `${BASE}/${id}/duplicate`, {
      new_name: newName,
    }),

  retire: (id: string): Promise<void> =>
    apiFetch(`${BASE}/${id}/retire`, { method: "POST" }).then(() => undefined),

  setDefault: (id: string): Promise<void> =>
    apiFetch(`${BASE}/${id}/set-default`, { method: "POST" }).then(() => undefined),

  usedBy: (id: string): Promise<StrategyControlsUsedByResponse> =>
    api.get(StrategyControlsUsedByResponseSchema, `${BASE}/${id}/used-by`),
};

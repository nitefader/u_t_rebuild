import { api, apiFetch } from "./client";
import {
  ExecutionPlanLibraryListResponseSchema,
  ExecutionPlanLibrarySchema,
  ExecutionPlanVersionRecordSchema,
  ExecutionPlanUsedByResponseSchema,
  type ExecutionPlanDraft,
  type ExecutionPlanLibrary,
  type ExecutionPlanLibraryListResponse,
  type ExecutionPlanUsedByResponse,
  type ExecutionPlanVersionRecord,
} from "./schemas/executionPlans";

const BASE = "/api/v1/execution-plans";

export const ExecutionPlansApi = {
  list: (): Promise<ExecutionPlanLibraryListResponse> =>
    api.get(ExecutionPlanLibraryListResponseSchema, BASE),

  get: (id: string): Promise<ExecutionPlanLibrary> =>
    api.get(ExecutionPlanLibrarySchema, `${BASE}/${id}`),

  getVersion: (id: string, version: number): Promise<ExecutionPlanVersionRecord> =>
    api.get(ExecutionPlanVersionRecordSchema, `${BASE}/${id}/versions/${version}`),

  create: (name: string, draft: ExecutionPlanDraft): Promise<ExecutionPlanVersionRecord> =>
    api.post(ExecutionPlanVersionRecordSchema, BASE, { name, draft }),

  edit: (id: string, draft: ExecutionPlanDraft): Promise<ExecutionPlanVersionRecord> =>
    api.put(ExecutionPlanVersionRecordSchema, `${BASE}/${id}`, { draft }),

  duplicate: (id: string, newName: string): Promise<ExecutionPlanVersionRecord> =>
    api.post(ExecutionPlanVersionRecordSchema, `${BASE}/${id}/duplicate`, {
      new_name: newName,
    }),

  retire: (id: string): Promise<void> =>
    apiFetch(`${BASE}/${id}/retire`, { method: "POST" }).then(() => undefined),

  setDefault: (id: string): Promise<void> =>
    apiFetch(`${BASE}/${id}/set-default`, { method: "POST" }).then(() => undefined),

  usedBy: (id: string): Promise<ExecutionPlanUsedByResponse> =>
    api.get(ExecutionPlanUsedByResponseSchema, `${BASE}/${id}/used-by`),
};

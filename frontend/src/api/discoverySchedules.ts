import { api } from "./client";
import { z } from "zod";
import {
  DiscoveryScheduleExecutionListResponseSchema,
  DiscoveryScheduleExecutionSchema,
  DiscoveryScheduleListResponseSchema,
  DiscoverySchedulePatchRequestSchema,
  DiscoveryScheduleSchema,
  DiscoveryScheduleWriteRequestSchema,
  type DiscoverySchedule,
  type DiscoveryScheduleExecution,
  type DiscoveryScheduleExecutionListResponse,
  type DiscoveryScheduleListResponse,
  type DiscoverySchedulePatchRequest,
  type DiscoveryScheduleWriteRequest,
} from "./schemas/discoverySchedules";

function ensureWrite(req: DiscoveryScheduleWriteRequest): DiscoveryScheduleWriteRequest {
  return DiscoveryScheduleWriteRequestSchema.parse(req);
}

function ensurePatch(req: DiscoverySchedulePatchRequest): DiscoverySchedulePatchRequest {
  return DiscoverySchedulePatchRequestSchema.parse(req);
}

export const DiscoverySchedulesApi = {
  list: (): Promise<DiscoveryScheduleListResponse> =>
    api.get(DiscoveryScheduleListResponseSchema, "/api/v1/discovery-schedules"),

  create: (req: DiscoveryScheduleWriteRequest): Promise<DiscoverySchedule> =>
    api.post(DiscoveryScheduleSchema, "/api/v1/discovery-schedules", ensureWrite(req)),

  get: (scheduleId: string): Promise<DiscoverySchedule> =>
    api.get(DiscoveryScheduleSchema, `/api/v1/discovery-schedules/${scheduleId}`),

  patch: (scheduleId: string, req: DiscoverySchedulePatchRequest): Promise<DiscoverySchedule> =>
    api.patch(
      DiscoveryScheduleSchema,
      `/api/v1/discovery-schedules/${scheduleId}`,
      ensurePatch(req),
    ),

  pause: (scheduleId: string): Promise<DiscoverySchedule> =>
    api.post(DiscoveryScheduleSchema, `/api/v1/discovery-schedules/${scheduleId}/pause`),

  resume: (scheduleId: string): Promise<DiscoverySchedule> =>
    api.post(DiscoveryScheduleSchema, `/api/v1/discovery-schedules/${scheduleId}/resume`),

  archive: (scheduleId: string): Promise<DiscoverySchedule> =>
    api.post(DiscoveryScheduleSchema, `/api/v1/discovery-schedules/${scheduleId}/archive`),

  delete: (scheduleId: string): Promise<unknown> =>
    api.post(z.unknown(), `/api/v1/discovery-schedules/${scheduleId}/delete`),

  runNow: (scheduleId: string): Promise<DiscoveryScheduleExecution> =>
    api.post(
      DiscoveryScheduleExecutionSchema,
      `/api/v1/discovery-schedules/${scheduleId}/run-now`,
    ),

  runDue: (): Promise<DiscoveryScheduleExecutionListResponse> =>
    api.post(DiscoveryScheduleExecutionListResponseSchema, "/api/v1/discovery-schedules/run-due"),

  executions: (scheduleId: string): Promise<DiscoveryScheduleExecutionListResponse> =>
    api.get(
      DiscoveryScheduleExecutionListResponseSchema,
      `/api/v1/discovery-schedules/${scheduleId}/executions`,
    ),
};

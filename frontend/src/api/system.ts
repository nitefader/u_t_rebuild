/**
 * System status / streams / settings boundary.
 */
import { api } from "./client";
import {
  SystemSettingsSchema,
  SystemStatusSchema,
  SystemStreamsResponseSchema,
  type SystemSettings,
  type SystemStatus,
  type SystemStreamsResponse,
} from "./schemas/system";

export const SystemApi = {
  status: (): Promise<SystemStatus> => api.get(SystemStatusSchema, "/api/v1/system/status"),
  streams: (): Promise<SystemStreamsResponse> =>
    api.get(SystemStreamsResponseSchema, "/api/v1/system/streams"),
  getSettings: (): Promise<SystemSettings> =>
    api.get(SystemSettingsSchema, "/api/v1/system/settings"),
  putSettings: (settings: SystemSettings): Promise<SystemSettings> =>
    api.put(SystemSettingsSchema, "/api/v1/system/settings", settings),
};

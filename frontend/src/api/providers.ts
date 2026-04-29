import { api } from "./client";
import {
  AIServiceDeletionResponseSchema,
  AIServiceListSchema,
  AIServiceRecordSchema,
  MarketDataServiceDeletionResponseSchema,
  MarketDataServiceListSchema,
  MarketDataServiceRecordSchema,
  type AIServiceList,
  type AIServiceRecord,
  type AIServiceWrite,
  type MarketDataServiceList,
  type MarketDataServiceRecord,
  type MarketDataServiceWrite,
  type ServicePurpose,
} from "./schemas/providers";

export const MarketDataProvidersApi = {
  list: (): Promise<MarketDataServiceList> =>
    api.get(MarketDataServiceListSchema, "/api/v1/market-data/services"),
  create: (req: MarketDataServiceWrite): Promise<MarketDataServiceRecord> =>
    api.post(MarketDataServiceRecordSchema, "/api/v1/market-data/services", req),
  validate: (id: string): Promise<MarketDataServiceRecord> =>
    api.post(MarketDataServiceRecordSchema, `/api/v1/market-data/services/${id}/validate`),
  setDefault: (id: string): Promise<MarketDataServiceRecord> =>
    api.post(MarketDataServiceRecordSchema, `/api/v1/market-data/services/${id}/set-default`),
  setDefaultFor: (id: string, purposes: ServicePurpose[]): Promise<MarketDataServiceRecord> =>
    api.post(MarketDataServiceRecordSchema, `/api/v1/market-data/services/${id}/default-for`, {
      purposes,
    }),
  disable: (id: string): Promise<MarketDataServiceRecord> =>
    api.post(MarketDataServiceRecordSchema, `/api/v1/market-data/services/${id}/disable`),
  enable: (id: string): Promise<MarketDataServiceRecord> =>
    api.post(MarketDataServiceRecordSchema, `/api/v1/market-data/services/${id}/enable`),
  delete: (id: string, confirmName: string) =>
    api.post(MarketDataServiceDeletionResponseSchema, `/api/v1/market-data/services/${id}/delete`, {
      confirm_service_name: confirmName,
    }),
};

export const AIProvidersApi = {
  list: (): Promise<AIServiceList> => api.get(AIServiceListSchema, "/api/v1/ai/providers"),
  create: (req: AIServiceWrite): Promise<AIServiceRecord> =>
    api.post(AIServiceRecordSchema, "/api/v1/ai/providers", req),
  update: (id: string, req: AIServiceWrite): Promise<AIServiceRecord> =>
    api.put(AIServiceRecordSchema, `/api/v1/ai/providers/${id}`, req),
  validate: (id: string): Promise<AIServiceRecord> =>
    api.post(AIServiceRecordSchema, `/api/v1/ai/providers/${id}/validate`),
  setDefault: (id: string): Promise<AIServiceRecord> =>
    api.post(AIServiceRecordSchema, `/api/v1/ai/providers/${id}/set-default`),
  disable: (id: string): Promise<AIServiceRecord> =>
    api.post(AIServiceRecordSchema, `/api/v1/ai/providers/${id}/disable`),
  delete: (id: string, confirmName: string) =>
    api.post(AIServiceDeletionResponseSchema, `/api/v1/ai/providers/${id}/delete`, {
      confirm_service_name: confirmName,
    }),
};

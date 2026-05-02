import { api } from "./client";
import {
  ChartLabHealthSchema,
  ChartLabFeatureLibraryResponseSchema,
  ChartLabPreviewResponseSchema,
  type ChartLabFeatureLibraryResponse,
  type ChartLabHealth,
  type ChartLabPreviewRequest,
  type ChartLabPreviewResponse,
} from "./schemas/chartLab";

export const ChartLabApi = {
  health: (): Promise<ChartLabHealth> =>
    api.get(ChartLabHealthSchema, "/api/v1/chart-lab/health"),
  streamPath: (symbol: string): string =>
    `/api/v1/chart-lab/stream?symbol=${encodeURIComponent(symbol.toUpperCase())}`,
  features: (timeframe: string): Promise<ChartLabFeatureLibraryResponse> =>
    api.get(
      ChartLabFeatureLibraryResponseSchema,
      `/api/v1/chart-lab/features?timeframe=${encodeURIComponent(timeframe)}`,
    ),
  preview: (req: ChartLabPreviewRequest): Promise<ChartLabPreviewResponse> =>
    api.post(ChartLabPreviewResponseSchema, "/api/v1/chart-lab/preview", req),
};

import { api } from "@/api/client";
import {
  HistoricalBarPageSchema,
  HistoricalDatasetDetailSchema,
  HistoricalDatasetListResponseSchema,
} from "@/api/schemas/historicalDatasets";

export const HistoricalDatasetsApi = {
  list() {
    return api.get(HistoricalDatasetListResponseSchema, "/api/v1/data-center/historical-datasets");
  },
  detail(datasetId: string) {
    return api.get(
      HistoricalDatasetDetailSchema,
      `/api/v1/data-center/historical-datasets/${encodeURIComponent(datasetId)}`,
    );
  },
  bars(datasetId: string, params?: { offset?: number; limit?: number }) {
    const q = new URLSearchParams();
    if (params?.offset != null) q.set("offset", String(params.offset));
    if (params?.limit != null) q.set("limit", String(params.limit));
    const suffix = q.toString() ? `?${q.toString()}` : "";
    return api.get(
      HistoricalBarPageSchema,
      `/api/v1/data-center/historical-datasets/${encodeURIComponent(datasetId)}/bars${suffix}`,
    );
  },
};

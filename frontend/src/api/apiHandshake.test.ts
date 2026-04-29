import { afterEach, describe, expect, it, vi } from "vitest";

import { MarketDataProvidersApi } from "./providers";
import {
  MarketDataServiceDeletionResponseSchema,
  MarketDataServiceRecordSchema,
} from "./schemas/providers";

describe("frontend API handshakes", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("parses the market-data hard-delete response contract", () => {
    const parsed = MarketDataServiceDeletionResponseSchema.parse({
      service_id: "4b7be3f7-2ea6-4b93-842d-1fc3687b3aa6",
      message: "Market data service removed from catalog",
    });

    expect(parsed.service_id).toBe("4b7be3f7-2ea6-4b93-842d-1fc3687b3aa6");
  });

  it("does not treat market-data hard-delete as a service record", () => {
    const response = {
      service_id: "4b7be3f7-2ea6-4b93-842d-1fc3687b3aa6",
      message: "Market data service removed from catalog",
    };

    expect(MarketDataServiceDeletionResponseSchema.safeParse(response).success).toBe(true);
    expect(MarketDataServiceRecordSchema.safeParse(response).success).toBe(false);
  });

  it("calls the backend market-data delete route with the deletion response schema", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          service_id: "4b7be3f7-2ea6-4b93-842d-1fc3687b3aa6",
          message: "Market data service removed from catalog",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    const result = await MarketDataProvidersApi.delete(
      "4b7be3f7-2ea6-4b93-842d-1fc3687b3aa6",
      "Alpaca SIP",
    );

    expect(result.message).toContain("removed");
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/market-data/services/4b7be3f7-2ea6-4b93-842d-1fc3687b3aa6/delete",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ confirm_service_name: "Alpaca SIP" }),
      }),
    );
  });
});

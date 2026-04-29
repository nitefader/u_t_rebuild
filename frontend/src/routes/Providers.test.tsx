import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Providers } from "./Providers";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const STATUS_OK = {
  alpaca_endpoint: "https://paper-api.alpaca.markets",
  alpaca_data_feed: "sip",
  alpaca_credentials_present: true,
  alpaca_test_stream: false,
  operator_environment: "paper",
  operator_environment_source: "explicit",
  operator_environment_conflict: null,
};

describe("<Providers />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty Market Data tab when no providers exist", async () => {
    restore = installFetchMock([
      { url: "/api/v1/market-data/services", body: { services: [] } },
      { url: "/api/v1/ai/providers", body: { services: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Providers />);
    await waitFor(() => {
      expect(screen.getByText(/No Market Data Providers configured/i)).toBeInTheDocument();
    });
  });

  it("renders an Alpaca card when one provider is registered", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/market-data/services",
        body: {
          services: [
            {
              id: "abc",
              name: "Algo Trading in Alpaca",
              provider: "alpaca",
              service_type: "market_data",
              status: "valid",
              is_default: true,
              default_for: ["live_streaming"],
              credentials_ref: null,
              has_api_key: true,
              has_api_secret: true,
              validation_status: "valid",
              validation_message: null,
              last_validated_at: new Date().toISOString(),
              capabilities: {},
              capability_notes: [],
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              disabled_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/ai/providers", body: { services: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Providers />);
    await waitFor(() => {
      expect(screen.getByText(/Algo Trading in Alpaca/i)).toBeInTheDocument();
    });
  });

  it("renders an Enable button on a disabled Market Data Provider card", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/market-data/services",
        body: {
          services: [
            {
              id: "yh1",
              name: "Yahoo Historical",
              provider: "yahoo",
              service_type: "market_data",
              status: "disabled",
              is_default: false,
              default_for: [],
              credentials_ref: null,
              has_api_key: false,
              has_api_secret: false,
              validation_status: "disabled",
              validation_message: null,
              last_validated_at: null,
              capabilities: {},
              capability_notes: [],
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              disabled_at: new Date().toISOString(),
            },
          ],
        },
      },
      { url: "/api/v1/ai/providers", body: { services: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Providers />);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Enable$/ })).toBeInTheDocument();
    });
    expect(screen.getByText(/Disabled/)).toBeInTheDocument();
  });

  it("surfaces a degraded read state when market data services fail", async () => {
    restore = installFetchMock([
      { url: "/api/v1/market-data/services", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/ai/providers", body: { services: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Providers />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load providers/i)).toBeInTheDocument();
    });
  });
});

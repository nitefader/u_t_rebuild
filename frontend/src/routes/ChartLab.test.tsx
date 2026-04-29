import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { ChartLab } from "./ChartLab";
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

describe("<ChartLab />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the streaming-disabled banner when health says streaming is off", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/chart-lab/health",
        body: {
          streaming_enabled: false,
          test_stream: false,
          default_symbol: "SPY",
          data_feed: "sip",
          websocket_path: "/api/v1/chart-lab/stream",
          routing_note: "",
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<ChartLab />);
    await waitFor(() => {
      expect(screen.getByText(/Streaming disabled/i)).toBeInTheDocument();
    });
  });

  it("renders the stream card when health is happy", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/chart-lab/health",
        body: {
          streaming_enabled: true,
          test_stream: false,
          default_symbol: "SPY",
          data_feed: "sip",
          websocket_path: "/api/v1/chart-lab/stream",
          routing_note: "",
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<ChartLab />);
    await waitFor(() => {
      expect(screen.getAllByText(/Stream/i).length).toBeGreaterThan(0);
    });
  });

  it("surfaces a degraded read state when health fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/chart-lab/health", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<ChartLab />);
    await waitFor(() => {
      expect(screen.getByText(/Chart Lab not configured/i)).toBeInTheDocument();
    });
  });
});

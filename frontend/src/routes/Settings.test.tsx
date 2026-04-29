import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Settings } from "./Settings";
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

describe("<Settings />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders preferences from the server", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/system/settings",
        body: {
          alpaca_data_feed: "sip",
          alpaca_use_test_stream: false,
          chart_lab_one_symbol_fakepaca: false,
          default_symbol: "SPY",
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Settings />);
    await waitFor(() => {
      expect(screen.getByText(/Live Stock Market Data Stream/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Chart Lab/i).length).toBeGreaterThan(0);
  });

  it("surfaces a degraded read state", async () => {
    restore = installFetchMock([
      { url: "/api/v1/system/settings", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Settings />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load settings/i)).toBeInTheDocument();
    });
  });
});

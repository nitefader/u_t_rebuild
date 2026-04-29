import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Dashboard } from "./Dashboard";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const OVERVIEW_EMPTY = {
  system_recovery_active: false,
  global_kill_active: false,
  control_state: {
    system_recovery_active: false,
    global_kill_active: false,
    paused_account_ids: [],
    paused_deployment_ids: [],
  },
  broker_accounts: [],
  deployments: [],
  stale_sync_accounts: [],
  blocked_deployments: [],
  open_orders_count: 0,
  open_positions_count: 0,
  latest_governor_decisions: [],
  latest_broker_sync_timestamp: null,
  latest_runtime_event_timestamp: null,
  research_evidence_summary: [],
};

describe("<Dashboard />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the platform-state empty path with no hubs and no trade streams", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/system/streams",
        body: { market_data_hubs: [], trade_streams: [], snapshot_at: new Date().toISOString() },
      },
      { url: "/api/v1/operations/overview", body: OVERVIEW_EMPTY },
      {
        url: "/api/v1/system/status",
        body: {
          alpaca_endpoint: "https://paper-api.alpaca.markets",
          alpaca_data_feed: "sip",
          alpaca_credentials_present: true,
          alpaca_test_stream: false,
          operator_environment: "paper",
          operator_environment_source: "explicit",
          operator_environment_conflict: null,
        },
      },
    ]);
    renderRoute(<Dashboard />);
    await waitFor(() => {
      expect(screen.getAllByText(/Live Stock Data/i).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/no hub configured/i)).toBeInTheDocument();
  });

  it("renders the happy path with one running hub and connected trade sync", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/system/streams",
        body: {
          market_data_hubs: [
            {
              provider: "alpaca",
              asset_class: "stock",
              data_feed: "sip",
              is_running: true,
              consumer_count: 1,
              subscribed_symbols: ["AAPL", "MSFT"],
              stream_status: "connected",
              last_error: null,
              last_message_at: new Date().toISOString(),
            },
          ],
          trade_streams: [
            {
              account_id: "11111111-1111-1111-1111-111111111111",
              account_label: "Paper · primary",
              is_running: true,
              last_event_at: new Date().toISOString(),
              last_error: null,
              subscriber_count: 1,
              subscriber_summary_lines: [],
              is_stale: false,
              stale_reason: null,
              idle_note: null,
            },
          ],
          snapshot_at: new Date().toISOString(),
        },
      },
      { url: "/api/v1/operations/overview", body: OVERVIEW_EMPTY },
      {
        url: "/api/v1/system/status",
        body: {
          alpaca_endpoint: "https://paper-api.alpaca.markets",
          alpaca_data_feed: "sip",
          alpaca_credentials_present: true,
          alpaca_test_stream: false,
          operator_environment: "paper",
          operator_environment_source: "explicit",
          operator_environment_conflict: null,
        },
      },
    ]);
    renderRoute(<Dashboard />);
    await waitFor(() => {
      expect(screen.getAllByText(/Running/i).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/SIP/i)).toBeInTheDocument();
  });

  it("renders the degraded path when streams returns a server error", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/system/streams",
        body: { detail: "kaboom" },
        status: 500,
      },
      { url: "/api/v1/operations/overview", body: OVERVIEW_EMPTY },
      {
        url: "/api/v1/system/status",
        body: {
          alpaca_endpoint: "https://paper-api.alpaca.markets",
          alpaca_data_feed: "sip",
          alpaca_credentials_present: true,
          alpaca_test_stream: false,
          operator_environment: "paper",
          operator_environment_source: "explicit",
          operator_environment_conflict: null,
        },
      },
    ]);
    renderRoute(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load platform state/i)).toBeInTheDocument();
    });
  });

  it("renders deployments and open positions from Operations overview", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/system/streams",
        body: {
          market_data_hubs: [],
          trade_streams: [],
          snapshot_at: new Date().toISOString(),
        },
      },
      {
        url: "/api/v1/operations/overview",
        body: {
          ...OVERVIEW_EMPTY,
          deployments: [
            {
              deployment_id: "22222222-2222-2222-2222-222222222222",
              status: "running",
              is_running: true,
              account_id: "11111111-1111-1111-1111-111111111111",
              strategy_version_id: "33333333-3333-3333-3333-333333333333",
              strategy_version: 1,
            },
          ],
          open_orders_count: 2,
          open_positions_count: 3,
        },
      },
      {
        url: "/api/v1/system/status",
        body: {
          alpaca_endpoint: "https://paper-api.alpaca.markets",
          alpaca_data_feed: "sip",
          alpaca_credentials_present: true,
          alpaca_test_stream: false,
          operator_environment: "paper",
          operator_environment_source: "explicit",
          operator_environment_conflict: null,
        },
      },
    ]);
    renderRoute(<Dashboard />);
    await waitFor(() => {
      expect(screen.getByText(/Open Positions/i)).toBeInTheDocument();
    });
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText(/open orders 2/i)).toBeInTheDocument();
    expect(screen.getByText(/1 running - 0 blocked/i)).toBeInTheDocument();
  });
});

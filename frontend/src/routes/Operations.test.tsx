import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Operations } from "./Operations";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const STREAMS_EMPTY = {
  market_data_hubs: [],
  trade_streams: [],
  snapshot_at: new Date().toISOString(),
};

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

const STATUS_OK = {
  alpaca_endpoint: "https://paper-api.alpaca.markets",
  alpaca_data_feed: "sip",
  alpaca_credentials_present: true,
  alpaca_test_stream: false,
  operator_environment: "paper",
  operator_environment_source: "explicit",
  operator_environment_conflict: null,
};

describe("<Operations />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders an empty operations page without crashing", async () => {
    restore = installFetchMock([
      { url: "/api/v1/operations/overview", body: OVERVIEW_EMPTY },
      { url: "/api/v1/system/streams", body: STREAMS_EMPTY },
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/operations/signal-plans", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/operations/evaluations", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/operations/governor-decisions", body: { detail: "not found" }, status: 404 },
    ]);
    renderRoute(<Operations />);
    await waitFor(() => {
      // Wait for the empty branch to render — proves the queries resolved.
      expect(screen.getAllByText(/No Accounts/i).length).toBeGreaterThan(0);
    });
    expect(screen.getByText(/No Deployments/i)).toBeInTheDocument();
  });

  it("renders runtime banners when global kill is active", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/operations/overview",
        body: { ...OVERVIEW_EMPTY, global_kill_active: true },
      },
      { url: "/api/v1/system/streams", body: STREAMS_EMPTY },
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/operations/signal-plans", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/operations/evaluations", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/operations/governor-decisions", body: { detail: "not found" }, status: 404 },
    ]);
    renderRoute(<Operations />);
    await waitFor(() => {
      expect(screen.getByText(/Global kill is active/i)).toBeInTheDocument();
    });
  });

  it("traces an Alpaca broker order id back to internal order detail", async () => {
    const BROKER_ORDER_ID = "alp-deadbeef-1234";
    const ACCOUNT_ID = "11111111-1111-1111-1111-111111111111";
    const ORDER_ID = "22222222-2222-2222-2222-222222222222";
    restore = installFetchMock([
      // Most-specific URL first so the trace lookup wins over the bare overview.
      {
        url: `/api/v1/operations/broker-orders/${BROKER_ORDER_ID}`,
        body: {
          internal_order: {
            order_id: ORDER_ID,
            client_order_id: "ut-deadbeef",
            account_id: ACCOUNT_ID,
            symbol: "SPY",
            side: "buy",
            quantity: 10,
            filled_quantity: 10,
            status: "filled",
            deployment_id: null,
          },
          broker_account_id: ACCOUNT_ID,
          deployment_id: null,
          strategy_version_id: null,
          broker_order_id: BROKER_ORDER_ID,
          broker_status: "filled",
          broker_sync_timestamp: new Date().toISOString(),
          fills: [],
          trade_summary: {},
        },
      },
      { url: "/api/v1/operations/overview", body: OVERVIEW_EMPTY },
      { url: "/api/v1/system/streams", body: STREAMS_EMPTY },
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/operations/signal-plans", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/operations/evaluations", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/operations/governor-decisions", body: { detail: "not found" }, status: 404 },
    ]);
    renderRoute(<Operations />);
    await waitFor(() => {
      expect(screen.getByText(/Trace broker order/i)).toBeInTheDocument();
    });
    const input = screen.getByLabelText(/Broker order id/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: BROKER_ORDER_ID } });
    fireEvent.click(screen.getByRole("button", { name: /^Trace$/i }));
    await waitFor(() => {
      // Result panel surfaces ticker + filled status; broker_status muted badge.
      expect(screen.getByText("SPY")).toBeInTheDocument();
    });
    expect(screen.getAllByText(/manual/i).length).toBeGreaterThanOrEqual(1);
  });

  it("surfaces a degraded read state when overview fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/operations/overview", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/system/streams", body: STREAMS_EMPTY },
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/operations/signal-plans", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/operations/evaluations", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/operations/governor-decisions", body: { detail: "not found" }, status: 404 },
    ]);
    renderRoute(<Operations />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load runtime state/i)).toBeInTheDocument();
    });
  });
});

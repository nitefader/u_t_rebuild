import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Accounts } from "./Accounts";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const STREAMS = {
  market_data_hubs: [],
  trade_streams: [],
  snapshot_at: new Date().toISOString(),
};
const OVERVIEW = {
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

describe("<Accounts />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state with no accounts", async () => {
    restore = installFetchMock([
      { url: "/api/v1/broker-accounts", body: { accounts: [] } },
      { url: "/api/v1/system/streams", body: STREAMS },
      { url: "/api/v1/operations/overview", body: OVERVIEW },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText(/No accounts yet/i)).toBeInTheDocument();
    });
  });

  it("renders one account card on the happy path", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/broker-accounts",
        body: {
          accounts: [
            {
              id: "11111111-1111-1111-1111-111111111111",
              display_name: "Paper Primary",
              provider: "alpaca",
              mode: "BROKER_PAPER",
              external_account_id: null,
              credentials_ref: "alpaca-paper:abc:fingerprint",
              needs_credentials: false,
              validation_status: "valid",
              last_account_snapshot: null,
              broker_sync_freshness: null,
              created_at: new Date().toISOString(),
              is_archived: false,
              archived_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/system/streams", body: STREAMS },
      { url: "/api/v1/operations/overview", body: OVERVIEW },
      { url: "/api/v1/operations/accounts/", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText("Paper Primary")).toBeInTheDocument();
    });
  });

  it("surfaces a degraded read state when accounts list fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/broker-accounts", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/system/streams", body: STREAMS },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Accounts />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load accounts/i)).toBeInTheDocument();
    });
  });
});

import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Deployments } from "./Deployments";
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

describe("<Deployments />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state with no deployments", async () => {
    restore = installFetchMock([
      { url: "/api/v1/deployments", body: { deployments: [] } },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Deployments />);
    await waitFor(() => {
      expect(screen.getByText(/No deployments yet/i)).toBeInTheDocument();
    });
  });

  it("renders a deployment card on the happy path", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/deployments",
        body: {
          deployments: [
            {
              deployment_id: "33333333-3333-3333-3333-333333333333",
              name: "Layered SPY",
              description: null,
              strategy_version_id: "44444444-4444-4444-4444-444444444444",
              watchlist_ids: ["55555555-5555-5555-5555-555555555555"],
              subscribed_account_ids: ["66666666-6666-6666-6666-666666666666"],
              lifecycle_status: "draft",
              runtime_overrides: {},
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              started_at: null,
              stopped_at: null,
            },
          ],
        },
      },
      {
        url: "/api/v1/watchlists",
        body: {
          watchlists: [
            {
              watchlist_id: "55555555-5555-5555-5555-555555555555",
              name: "Alpaca Day Gainers",
              description: null,
              kind: "dynamic",
              static_symbols: [],
              dynamic_rules: { source_type: "screener_version" },
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              latest_snapshot_id: null,
              snapshot_count: 1,
              status: "active",
              archived_at: null,
            },
          ],
        },
      },
      {
        url: "/api/v1/strategies",
        body: {
          strategies: [
            {
              strategy_id: "77777777-7777-7777-7777-777777777777",
              name: "Opening Range Strategy",
              description: null,
              tags: [],
              status: "active",
              created_at: new Date().toISOString(),
              latest_version_id: "44444444-4444-4444-4444-444444444444",
              frozen_version_ids: ["44444444-4444-4444-4444-444444444444"],
              version_count: 1,
            },
          ],
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Deployments />);
    await waitFor(() => {
      expect(screen.getByText("Layered SPY")).toBeInTheDocument();
    });
    expect(screen.getByText("Opening Range Strategy")).toBeInTheDocument();
    expect(screen.getByText("Alpaca Day Gainers")).toBeInTheDocument();
    expect(screen.queryByText(/44444444/)).not.toBeInTheDocument();
  });

  it("allows draft strategy versions to be selected for Deployment attachment", async () => {
    const now = new Date().toISOString();
    restore = installFetchMock([
      { url: "/api/v1/deployments", body: { deployments: [] } },
      {
        url: "/api/v1/watchlists",
        body: {
          watchlists: [
            {
              watchlist_id: "55555555-5555-5555-5555-555555555555",
              name: "Headless Dynamic Entries",
              description: null,
              kind: "dynamic",
              static_symbols: [],
              dynamic_rules: { source_type: "screener_version" },
              created_at: now,
              updated_at: now,
              latest_snapshot_id: null,
              snapshot_count: 1,
              status: "active",
              archived_at: null,
            },
          ],
        },
      },
      {
        url: "/api/v1/strategies/77777777-7777-7777-7777-777777777777/versions",
        body: [
          {
            strategy_version_id: "44444444-4444-4444-4444-444444444444",
            strategy_id: "77777777-7777-7777-7777-777777777777",
            version: 1,
            status: "draft",
            payload: {
              id: "44444444-4444-4444-4444-444444444444",
              strategy_id: "77777777-7777-7777-7777-777777777777",
              version: 1,
              name: "Draft Strategy Version",
              feature_refs: [],
              entry_rules: [],
              exit_rules: [],
              tags: [],
              created_at: now,
            },
            frozen_at: null,
            frozen_by: null,
            created_at: now,
          },
        ],
      },
      {
        url: "/api/v1/strategies",
        body: {
          strategies: [
            {
              strategy_id: "77777777-7777-7777-7777-777777777777",
              name: "Opening Range Strategy",
              description: null,
              tags: [],
              status: "active",
              created_at: now,
              latest_version_id: "44444444-4444-4444-4444-444444444444",
              frozen_version_ids: [],
              version_count: 1,
            },
          ],
        },
      },
      {
        url: "/api/v1/broker-accounts",
        body: {
          accounts: [
            {
              id: "66666666-6666-6666-6666-666666666666",
              display_name: "Alpaca Paper Account",
              provider: "alpaca",
              mode: "BROKER_PAPER",
              credentials_ref: "test",
              needs_credentials: false,
              validation_status: "valid",
              created_at: now,
              is_archived: false,
              archived_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Deployments />);
    await waitFor(() => expect(screen.getByText(/No deployments yet/i)).toBeInTheDocument());

    fireEvent.click(screen.getAllByRole("button", { name: /New Deployment/i })[0]);
    fireEvent.change(await screen.findByLabelText("Strategy"), {
      target: { value: "77777777-7777-7777-7777-777777777777" },
    });

    await waitFor(() => {
      expect(screen.getByLabelText("Strategy version")).toHaveTextContent("v1 - draft");
    });
    expect(screen.queryByText(/No frozen versions/i)).not.toBeInTheDocument();
  });

  it("surfaces a degraded read state when list fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/deployments", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Deployments />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load deployments/i)).toBeInTheDocument();
    });
  });
});

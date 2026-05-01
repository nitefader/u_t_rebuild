import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

async function holdDeleteVerifier(): Promise<void> {
  vi.useFakeTimers();
  const verifier = screen.getByRole("button", { name: /Hold 2 seconds to verify/i });
  fireEvent.pointerDown(verifier);
  await act(async () => {
    vi.advanceTimersByTime(2000);
  });
  vi.useRealTimers();
}

describe("<Deployments />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    vi.useRealTimers();
    restore?.();
    restore = null;
  });

  it("renders the empty state with no deployments", async () => {
    restore = installFetchMock([
      { url: "/api/v1/deployments", body: { deployments: [] } },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/strategies/v4/", body: [] },
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
      { url: "/api/v1/strategies/v4/", body: [] },
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

  it("shows Horizon column for deployments that have a risk_horizon set", async () => {
    const now = new Date().toISOString();
    restore = installFetchMock([
      {
        url: "/api/v1/deployments",
        body: {
          deployments: [
            {
              deployment_id: "33333333-3333-3333-3333-333333333333",
              name: "Intraday Rocket",
              description: null,
              strategy_version_id: "44444444-4444-4444-4444-444444444444",
              watchlist_ids: [],
              subscribed_account_ids: [],
              lifecycle_status: "draft",
              runtime_overrides: {},
              risk_horizon: "intraday",
              created_at: now,
              updated_at: now,
              started_at: null,
              stopped_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/strategies/v4/", body: [] },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Deployments />);
    await waitFor(() => {
      expect(screen.getByText("Intraday Rocket")).toBeInTheDocument();
    });
    expect(screen.getByText("Intraday")).toBeInTheDocument();
  });

  it("shows Rebind button only on ACTIVE deployments", async () => {
    const now = new Date().toISOString();
    restore = installFetchMock([
      {
        url: "/api/v1/deployments",
        body: {
          deployments: [
            {
              deployment_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
              name: "Active One",
              description: null,
              strategy_version_id: "44444444-4444-4444-4444-444444444444",
              watchlist_ids: [],
              subscribed_account_ids: [],
              lifecycle_status: "active",
              runtime_overrides: {},
              created_at: now,
              updated_at: now,
              started_at: now,
              stopped_at: null,
            },
            {
              deployment_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
              name: "Draft One",
              description: null,
              strategy_version_id: "44444444-4444-4444-4444-444444444444",
              watchlist_ids: [],
              subscribed_account_ids: [],
              lifecycle_status: "draft",
              runtime_overrides: {},
              created_at: now,
              updated_at: now,
              started_at: null,
              stopped_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/strategies/v4/", body: [] },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Deployments />);
    await waitFor(() => {
      expect(screen.getByText("Active One")).toBeInTheDocument();
    });
    const rebindButtons = screen.getAllByRole("button", { name: /Rebind/i });
    // Only the active deployment should show a Rebind button
    expect(rebindButtons).toHaveLength(1);
  });

  it("shows v4 strategy name when deployment has strategy_version_v4_id", async () => {
    const now = new Date().toISOString();
    restore = installFetchMock([
      {
        url: "/api/v1/deployments",
        body: {
          deployments: [
            {
              deployment_id: "33333333-3333-3333-3333-333333333333",
              name: "v4 Deployment",
              description: null,
              strategy_version_v4_id: "v4ver-id-0000-0000-000000000000",
              watchlist_ids: [],
              subscribed_account_ids: [],
              lifecycle_status: "draft",
              runtime_overrides: {},
              created_at: now,
              updated_at: now,
              started_at: null,
              stopped_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/strategies", body: { strategies: [] } },
      {
        url: "/api/v1/strategies/v4/",
        body: [
          {
            strategy_v4_id: "v4strat-id-000-0000-000000000000",
            name: "My v4 Strategy",
            description: null,
            head_version: 1,
            head_version_id: "v4ver-id-0000-0000-000000000000",
            total_versions: 1,
            created_at: now,
            updated_at: now,
          },
        ],
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Deployments />);
    await waitFor(() => {
      expect(screen.getByText("My v4 Strategy")).toBeInTheDocument();
    });
  });

  it("legacy create-drawer still accessible from empty-state button", async () => {
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
      { url: "/api/v1/strategies/v4/", body: [] },
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
    // The empty-state "New Deployment" button opens the legacy create drawer.
    // The PageHeader button navigates to the new 6-step screen.
    // Both show text "New Deployment"; the empty-state button is the second one (index 1).
    const newDeploymentButtons = screen.getAllByRole("button", { name: /New Deployment/i });
    expect(newDeploymentButtons.length).toBeGreaterThanOrEqual(1);
    // Clicking the empty-state button opens the legacy create drawer.
    fireEvent.click(newDeploymentButtons[newDeploymentButtons.length - 1]);
    await waitFor(() => {
      expect(screen.getByText(/Pick a Strategy version/i)).toBeInTheDocument();
    });
  });

  it("surfaces a degraded read state when list fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/deployments", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/strategies/v4/", body: [] },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Deployments />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load deployments/i)).toBeInTheDocument();
    });
  });

  it("bulk deletes selected deployments and reports blocked rows", async () => {
    const user = userEvent.setup();
    const now = new Date().toISOString();
    restore = installFetchMock([
      {
        url: "/api/v1/deployments",
        method: "GET",
        body: {
          deployments: [
            {
              deployment_id: "33333333-3333-3333-3333-333333333333",
              name: "Draft Deployment",
              description: null,
              strategy_version_id: "44444444-4444-4444-4444-444444444444",
              watchlist_ids: ["55555555-5555-5555-5555-555555555555"],
              subscribed_account_ids: ["66666666-6666-6666-6666-666666666666"],
              lifecycle_status: "draft",
              runtime_overrides: {},
              created_at: now,
              updated_at: now,
              started_at: null,
              stopped_at: null,
            },
            {
              deployment_id: "99999999-9999-9999-9999-999999999999",
              name: "Active Deployment",
              description: null,
              strategy_version_id: "44444444-4444-4444-4444-444444444444",
              watchlist_ids: ["55555555-5555-5555-5555-555555555555"],
              subscribed_account_ids: ["66666666-6666-6666-6666-666666666666"],
              lifecycle_status: "active",
              runtime_overrides: {},
              created_at: now,
              updated_at: now,
              started_at: now,
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
              name: "Entry List",
              description: null,
              kind: "static",
              static_symbols: ["SPY"],
              dynamic_rules: null,
              created_at: now,
              updated_at: now,
              latest_snapshot_id: null,
              snapshot_count: 0,
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
              created_at: now,
              latest_version_id: "44444444-4444-4444-4444-444444444444",
              frozen_version_ids: ["44444444-4444-4444-4444-444444444444"],
              version_count: 1,
            },
          ],
        },
      },
      { url: "/api/v1/strategies/v4/", body: [] },
      { url: "/api/v1/system/status", body: STATUS_OK },
      {
        url: "/api/v1/deployments/33333333-3333-3333-3333-333333333333/delete",
        method: "POST",
        body: "",
        status: 204,
      },
      {
        url: "/api/v1/deployments/99999999-9999-9999-9999-999999999999/delete",
        method: "POST",
        body: { detail: "deployment must be DRAFT or STOPPED to delete; pause/stop it first" },
        status: 400,
      },
    ]);
    renderRoute(<Deployments />);
    await screen.findByText("Draft Deployment");

    await user.click(screen.getByLabelText(/Select deployment Draft Deployment/i));
    await user.click(screen.getByLabelText(/Select deployment Active Deployment/i));
    await user.click(screen.getByRole("button", { name: /Bulk delete/i }));
    await holdDeleteVerifier();
    await user.click(screen.getByRole("button", { name: /Delete Selected/i }));

    expect(await screen.findByText(/Deleted 1; 1 blocked/i)).toBeInTheDocument();
    expect(screen.getByText(/Active Deployment:/i)).toBeInTheDocument();
  });
});

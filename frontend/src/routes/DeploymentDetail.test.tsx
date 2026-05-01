import { describe, expect, it, afterEach } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { DeploymentDetail } from "./DeploymentDetail";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const NOW = new Date().toISOString();
const DEP_ID = "aaaa0000-0000-0000-0000-000000000001";

const DEPLOYMENT = {
  deployment: {
    deployment_id: DEP_ID,
    name: "Production Breakout",
    description: "Live deployment",
    strategy_version_v4_id: "strat-ver-0000-0000-000000000002",
    lifecycle_status: "active",
    watchlist_ids: ["watch-000-0000-0000-000000000001"],
    subscribed_account_ids: ["acct-0000-0000-0000-000000000001"],
    runtime_overrides: {},
    risk_horizon: "swing",
    created_at: NOW,
    updated_at: NOW,
    started_at: NOW,
    stopped_at: null,
  },
};

const HISTORY_RESPONSE = {
  entries: [
    {
      entry_id: "hist-0000-0000-0000-000000000001",
      deployment_id: DEP_ID,
      timestamp: NOW,
      actor: "operator",
      before: { strategy_controls_version_id: null },
      after: { strategy_controls_version_id: "ctrl-0001-0000-0000-000000000001" },
      effective: "now",
    },
  ],
};

const WATCHLISTS = {
  watchlists: [
    {
      watchlist_id: "watch-000-0000-0000-000000000001",
      name: "Morning Movers",
      description: null,
      kind: "dynamic",
      static_symbols: [],
      dynamic_rules: {},
      created_at: NOW,
      updated_at: NOW,
      latest_snapshot_id: null,
      snapshot_count: 0,
      status: "active",
      archived_at: null,
    },
  ],
};

const ACCOUNTS = {
  accounts: [
    {
      id: "acct-0000-0000-0000-000000000001",
      display_name: "Alpaca Paper",
      provider: "alpaca",
      mode: "BROKER_PAPER",
      credentials_ref: "cred",
      needs_credentials: false,
      validation_status: "valid",
      created_at: NOW,
      is_archived: false,
      archived_at: null,
    },
  ],
};

describe("<DeploymentDetail />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  function renderDetail(): void {
    restore = installFetchMock([
      {
        url: `/api/v1/deployments/${DEP_ID}`,
        method: "GET",
        body: DEPLOYMENT,
      },
      {
        url: `/api/v1/deployments/${DEP_ID}/binding-history`,
        body: HISTORY_RESPONSE,
      },
      { url: "/api/v1/watchlists", body: WATCHLISTS },
      { url: "/api/v1/broker-accounts", body: ACCOUNTS },
      { url: "/api/v1/strategy-controls", body: { libraries: [] } },
      { url: "/api/v1/execution-plans", body: { libraries: [] } },
    ]);
    renderRoute(<DeploymentDetail />, {
      path: "/deployments/:id",
      initialPath: `/deployments/${DEP_ID}`,
    });
  }

  it("renders deployment metadata", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getAllByText("Production Breakout").length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getByText("active")).toBeInTheDocument();
    expect(screen.getByText("Swing")).toBeInTheDocument();
  });

  it("renders watchlist and account names", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getByText("Morning Movers")).toBeInTheDocument();
    });
    expect(screen.getByText("Alpaca Paper")).toBeInTheDocument();
  });

  it("renders binding history entries", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getAllByText(/Controls/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("shows Rebind button for active deployment", async () => {
    renderDetail();
    await waitFor(() => {
      expect(screen.getAllByText("Production Breakout").length).toBeGreaterThanOrEqual(1);
    });
    const rebindBtn = screen.getAllByRole("button", { name: /Rebind/i });
    expect(rebindBtn.length).toBeGreaterThanOrEqual(1);
  });

  it("opens rebind drawer when Rebind is clicked", async () => {
    restore = installFetchMock([
      { url: `/api/v1/deployments/${DEP_ID}`, method: "GET", body: DEPLOYMENT },
      { url: `/api/v1/deployments/${DEP_ID}/binding-history`, body: HISTORY_RESPONSE },
      { url: "/api/v1/watchlists", body: WATCHLISTS },
      { url: "/api/v1/broker-accounts", body: ACCOUNTS },
      { url: "/api/v1/strategy-controls", body: { libraries: [{ strategy_controls_id: "c1", name: "C1", head_version_number: 1, is_default: false, retired_at: null, usage_count: 0 }] } },
      { url: "/api/v1/execution-plans", body: { libraries: [] } },
    ]);
    renderRoute(<DeploymentDetail />, {
      path: "/deployments/:id",
      initialPath: `/deployments/${DEP_ID}`,
    });

    await waitFor(() => {
      expect(screen.getAllByText("Production Breakout").length).toBeGreaterThanOrEqual(1);
    });

    const rebindBtns = screen.getAllByRole("button", { name: /Rebind/i });
    fireEvent.click(rebindBtns[0]);

    await waitFor(() => {
      expect(screen.getByText(/Hot-swap Strategy Controls/i)).toBeInTheDocument();
    });
  });
});

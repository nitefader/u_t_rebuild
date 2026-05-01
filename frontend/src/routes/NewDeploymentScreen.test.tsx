import { describe, expect, it, afterEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { NewDeploymentScreen } from "./NewDeploymentScreen";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const NOW = new Date().toISOString();

const STRATEGY_HEADS = [
  {
    strategy_v4_id: "strat-v4-0000-0000-000000000001",
    name: "Opening Range Breakout",
    description: "ORB strategy",
    head_version: 2,
    head_version_id: "strat-ver-0000-0000-000000000002",
    total_versions: 2,
    created_at: NOW,
    updated_at: NOW,
  },
];

const CONTROLS_LIST = {
  libraries: [
    {
      strategy_controls_id: "ctrl-0001-0000-0000-000000000001",
      name: "Conservative Controls",
      head_version_number: 1,
      is_default: true,
      retired_at: null,
      usage_count: 0,
    },
  ],
};

const EXEC_PLAN_LIST = {
  libraries: [
    {
      execution_plan_id: "ep00-0001-0000-0000-000000000001",
      name: "Market Entry",
      head_version_number: 1,
      is_default: true,
      retired_at: null,
      usage_count: 0,
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
      dynamic_rules: { source_type: "screener_version" },
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

function installFullMock(restore: { current: (() => void) | null }): void {
  restore.current = installFetchMock([
    { url: "/api/v1/strategies/v4/", body: STRATEGY_HEADS },
    { url: "/api/v1/strategy-controls", body: CONTROLS_LIST },
    { url: "/api/v1/execution-plans", body: EXEC_PLAN_LIST },
    { url: "/api/v1/watchlists", body: WATCHLISTS },
    { url: "/api/v1/broker-accounts", body: ACCOUNTS },
    {
      url: "/api/v1/deployments",
      method: "POST",
      body: {
        deployment: {
          deployment_id: "new-depl-0000-0000-000000000001",
          name: "My New Deployment",
          lifecycle_status: "draft",
          watchlist_ids: ["watch-000-0000-0000-000000000001"],
          subscribed_account_ids: ["acct-0000-0000-0000-000000000001"],
          runtime_overrides: {},
          created_at: NOW,
          updated_at: NOW,
          strategy_version_v4_id: "strat-ver-0000-0000-000000000002",
        },
      },
    },
  ]);
}

describe("<NewDeploymentScreen />", () => {
  const restore: { current: (() => void) | null } = { current: null };
  afterEach(() => {
    restore.current?.();
    restore.current = null;
  });

  it("renders step 1 on mount and shows the strategy list", async () => {
    installFullMock(restore);
    renderRoute(<NewDeploymentScreen />);
    await waitFor(() => {
      expect(screen.getByText("Opening Range Breakout")).toBeInTheDocument();
    });
    expect(screen.getByText(/Step 1 of 6/i)).toBeInTheDocument();
  });

  it("Next button is disabled on Step 1 until a strategy is selected", async () => {
    installFullMock(restore);
    renderRoute(<NewDeploymentScreen />);
    await waitFor(() => {
      expect(screen.getByText("Opening Range Breakout")).toBeInTheDocument();
    });
    const nextBtn = screen.getByRole("button", { name: /Next/i });
    expect(nextBtn).toBeDisabled();

    // Select strategy
    fireEvent.click(screen.getByText("Opening Range Breakout"));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Next/i })).not.toBeDisabled();
    });
  });

  it("advances to Step 2 after selecting a strategy", async () => {
    installFullMock(restore);
    renderRoute(<NewDeploymentScreen />);
    await waitFor(() => {
      expect(screen.getByText("Opening Range Breakout")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Opening Range Breakout"));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));

    await waitFor(() => {
      expect(screen.getByText(/Step 2 of 6/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Strategy Controls/i).length).toBeGreaterThanOrEqual(1);
  });

  it("Step 4 (Watchlist) requires at least one selection before Next", async () => {
    installFullMock(restore);
    renderRoute(<NewDeploymentScreen />);
    await waitFor(() => {
      expect(screen.getByText("Opening Range Breakout")).toBeInTheDocument();
    });

    // Step 1
    fireEvent.click(screen.getByText("Opening Range Breakout"));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 2/i)).toBeInTheDocument());

    // Step 2 (Controls — optional)
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 3/i)).toBeInTheDocument());

    // Step 3 (Exec Plan — optional)
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 4/i)).toBeInTheDocument());

    // Next should be disabled (no watchlist selected yet)
    expect(screen.getByRole("button", { name: /Next/i })).toBeDisabled();

    // Select a watchlist via checkbox
    fireEvent.click(screen.getByRole("checkbox", { name: /Morning Movers/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Next/i })).not.toBeDisabled();
    });
  });

  it("Step 5 (Accounts) requires at least one selection before Next", async () => {
    installFullMock(restore);
    renderRoute(<NewDeploymentScreen />);
    await waitFor(() => {
      expect(screen.getByText("Opening Range Breakout")).toBeInTheDocument();
    });

    // Navigate to Step 5
    fireEvent.click(screen.getByText("Opening Range Breakout"));
    fireEvent.click(screen.getByRole("button", { name: /Next/i })); // -> step 2
    await waitFor(() => expect(screen.getByText(/Step 2/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Next/i })); // -> step 3
    await waitFor(() => expect(screen.getByText(/Step 3/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Next/i })); // -> step 4
    await waitFor(() => expect(screen.getByText(/Step 4/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("checkbox", { name: /Morning Movers/i })); // select watchlist
    await waitFor(() => expect(screen.getByRole("button", { name: /Next/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /Next/i })); // -> step 5
    await waitFor(() => expect(screen.getByText(/Step 5/i)).toBeInTheDocument());

    // Next should be disabled (no account yet)
    expect(screen.getByRole("button", { name: /Next/i })).toBeDisabled();

    // Select account via checkbox
    fireEvent.click(screen.getByRole("checkbox", { name: /Alpaca Paper/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Next/i })).not.toBeDisabled();
    });
  });

  it("shows the Create Deployment button on Step 6 and name field is required", async () => {
    installFullMock(restore);
    renderRoute(<NewDeploymentScreen />);
    await waitFor(() => {
      expect(screen.getByText("Opening Range Breakout")).toBeInTheDocument();
    });

    // Navigate to Step 6
    fireEvent.click(screen.getByText("Opening Range Breakout"));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 2/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 3/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 4/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("checkbox", { name: /Morning Movers/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Next/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 5/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("checkbox", { name: /Alpaca Paper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Next/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 6/i)).toBeInTheDocument());

    // Create button should be disabled (no name entered)
    expect(screen.getByRole("button", { name: /Create Deployment/i })).toBeDisabled();

    // Enter a name
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "My New Deployment" },
    });
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Create Deployment/i }),
      ).not.toBeDisabled();
    });
  });

  it("POSTs with strategy_version_v4_id on create", async () => {
    let capturedBody: unknown = null;
    // Install mock first, then wrap it so we can capture the POST body.
    restore.current = installFetchMock([
      { url: "/api/v1/strategies/v4/", body: STRATEGY_HEADS },
      { url: "/api/v1/strategy-controls", body: CONTROLS_LIST },
      { url: "/api/v1/execution-plans", body: EXEC_PLAN_LIST },
      { url: "/api/v1/watchlists", body: WATCHLISTS },
      { url: "/api/v1/broker-accounts", body: ACCOUNTS },
      {
        url: "/api/v1/deployments",
        method: "POST",
        body: {
          deployment: {
            deployment_id: "new-depl-0000-0000-000000000001",
            name: "My New Deployment",
            lifecycle_status: "draft",
            watchlist_ids: [],
            subscribed_account_ids: [],
            runtime_overrides: {},
            created_at: NOW,
            updated_at: NOW,
            strategy_version_v4_id: "strat-ver-0000-0000-000000000002",
          },
        },
      },
    ]);
    // Capture a reference to the installed mock so the spy below can delegate to it.
    const mockFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input, init) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.includes("/api/v1/deployments") && init?.method === "POST") {
        capturedBody = JSON.parse(init.body as string);
      }
      return mockFetch(input, init);
    }) as typeof globalThis.fetch;

    renderRoute(<NewDeploymentScreen />);
    await waitFor(() => {
      expect(screen.getByText("Opening Range Breakout")).toBeInTheDocument();
    });

    // Full wizard flow
    fireEvent.click(screen.getByText("Opening Range Breakout"));
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 2/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 3/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 4/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("checkbox", { name: /Morning Movers/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Next/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 5/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("checkbox", { name: /Alpaca Paper/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /Next/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /Next/i }));
    await waitFor(() => expect(screen.getByText(/Step 6/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "My New Deployment" },
    });

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: /Create Deployment/i }),
      ).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: /Create Deployment/i }));

    await waitFor(() => expect(capturedBody).toBeTruthy());
    const body = capturedBody as Record<string, unknown>;
    expect(body.strategy_version_v4_id).toBe("strat-ver-0000-0000-000000000002");
    expect(body.strategy_version_id).toBeUndefined();
    expect(body.name).toBe("My New Deployment");
  });
});

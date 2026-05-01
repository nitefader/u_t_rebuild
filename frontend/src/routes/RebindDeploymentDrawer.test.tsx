import { describe, expect, it, afterEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { RebindDeploymentDrawer } from "./RebindDeploymentDrawer";
import { installFetchMock, renderRoute } from "@/test/renderRoute";
import type { Deployment } from "@/api/schemas/deployments";

const NOW = new Date().toISOString();

const BASE_DEPLOYMENT: Deployment = {
  deployment_id: "aaaa0000-0000-0000-0000-000000000001",
  name: "Running Deployment",
  lifecycle_status: "active",
  watchlist_ids: [],
  subscribed_account_ids: [],
  runtime_overrides: {},
  created_at: NOW,
  updated_at: NOW,
  strategy_version_id: "44444444-4444-4444-4444-444444444444",
};

const CONTROLS_LIST = {
  libraries: [
    {
      strategy_controls_id: "ctrl-0001-0000-0000-000000000001",
      head_version_id: "ctrlv-0001-0000-0000-000000000001",
      name: "Conservative Controls",
      head_version_number: 1,
      is_default: true,
      retired_at: null,
      usage_count: 3,
    },
    {
      strategy_controls_id: "ctrl-0002-0000-0000-000000000002",
      head_version_id: "ctrlv-0002-0000-0000-000000000002",
      name: "Aggressive Controls",
      head_version_number: 2,
      is_default: false,
      retired_at: null,
      usage_count: 1,
    },
  ],
};

const EXEC_PLAN_LIST = {
  libraries: [
    {
      execution_plan_id: "ep00-0001-0000-0000-000000000001",
      head_version_id: "epv0-0001-0000-0000-000000000001",
      name: "Market Entry",
      head_version_number: 1,
      is_default: true,
      retired_at: null,
      usage_count: 2,
    },
    {
      execution_plan_id: "ep00-0002-0000-0000-000000000002",
      head_version_id: "epv0-0002-0000-0000-000000000002",
      name: "Limit Entry",
      head_version_number: 1,
      is_default: false,
      retired_at: null,
      usage_count: 0,
    },
  ],
};

describe("<RebindDeploymentDrawer />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  function renderOpenDrawer(deployment: Deployment = BASE_DEPLOYMENT): void {
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: CONTROLS_LIST },
      { url: "/api/v1/execution-plans", body: EXEC_PLAN_LIST },
    ]);
    renderRoute(
      <RebindDeploymentDrawer
        open={true}
        onOpenChange={() => undefined}
        deployment={deployment}
      />,
    );
  }

  it("renders Controls and Execution Plan pickers", async () => {
    renderOpenDrawer();
    await waitFor(() => {
      expect(screen.getByText(/Conservative Controls/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Market Entry/i)).toBeInTheDocument();
  });

  it("shows 'Now', 'Next session', and 'Custom' effective-when options", async () => {
    renderOpenDrawer();
    await waitFor(() => {
      expect(screen.getByText(/Conservative Controls/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText("Now")).toBeInTheDocument();
    expect(screen.getByLabelText("Next session")).toBeInTheDocument();
    expect(screen.getByLabelText("Custom")).toBeInTheDocument();
  });

  it("shows custom datetime input when Custom is selected", async () => {
    renderOpenDrawer();
    await waitFor(() => {
      expect(screen.getByLabelText("Custom")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByLabelText("Custom"));
    await waitFor(() => {
      expect(
        screen.getByLabelText(/Effective datetime/i),
      ).toBeInTheDocument();
    });
  });

  it("shows 'No changes' warning when no picker was changed", async () => {
    renderOpenDrawer();
    await waitFor(() => {
      expect(screen.getByText(/No changes/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /Rebind/i })).toBeDisabled();
  });

  it("enables Rebind button after changing Controls", async () => {
    renderOpenDrawer();
    await waitFor(() => {
      expect(screen.getByText(/Conservative Controls/i)).toBeInTheDocument();
    });
    // Change controls selector — select the first library explicitly
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], {
      target: { value: "ctrlv-0001-0000-0000-000000000001" },
    });
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Rebind/i })).not.toBeDisabled();
    });
  });

  it("POSTs rebind with swap-controls-only payload", async () => {
    let capturedBody: unknown = null;
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: CONTROLS_LIST },
      { url: "/api/v1/execution-plans", body: EXEC_PLAN_LIST },
      {
        url: "/api/v1/deployments/aaaa0000-0000-0000-0000-000000000001/rebind",
        method: "POST",
        body: {
          deployment: { ...BASE_DEPLOYMENT, strategy_controls_version_id: "ctrlv-0001-0000-0000-000000000001" },
        },
      },
    ]);

    // Intercept fetch to capture body
    const originalFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input, init) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.includes("/rebind") && init?.method === "POST") {
        capturedBody = JSON.parse(init.body as string);
      }
      return originalFetch(input, init);
    }) as typeof globalThis.fetch;

    renderRoute(
      <RebindDeploymentDrawer
        open={true}
        onOpenChange={() => undefined}
        deployment={BASE_DEPLOYMENT}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Conservative Controls/i)).toBeInTheDocument();
    });

    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], {
      target: { value: "ctrlv-0001-0000-0000-000000000001" },
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Rebind/i })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: /Rebind/i }));

    await waitFor(() => {
      expect(capturedBody).toBeTruthy();
    });
    const body = capturedBody as Record<string, unknown>;
    expect(body.strategy_controls_version_id).toBe("ctrlv-0001-0000-0000-000000000001");
    expect(body.effective).toBe("now");

    globalThis.fetch = originalFetch;
  });

  it("uses next_session when Next session radio is selected", async () => {
    let capturedBody: unknown = null;
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: CONTROLS_LIST },
      { url: "/api/v1/execution-plans", body: EXEC_PLAN_LIST },
      {
        url: "/api/v1/deployments/aaaa0000-0000-0000-0000-000000000001/rebind",
        method: "POST",
        body: { deployment: BASE_DEPLOYMENT },
      },
    ]);
    // Capture the mock (installed above) so the spy below can delegate to it.
    const mockFetch = globalThis.fetch;
    globalThis.fetch = vi.fn(async (input, init) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      if (url.includes("/rebind")) capturedBody = JSON.parse(init?.body as string);
      return mockFetch(input, init);
    }) as typeof globalThis.fetch;

    renderRoute(
      <RebindDeploymentDrawer
        open={true}
        onOpenChange={() => undefined}
        deployment={BASE_DEPLOYMENT}
      />,
    );

    await waitFor(() => expect(screen.getByText(/Conservative Controls/i)).toBeInTheDocument());

    // Change controls
    const selects = screen.getAllByRole("combobox");
    fireEvent.change(selects[0], { target: { value: "ctrlv-0001-0000-0000-000000000001" } });
    // Set effective to next_session
    fireEvent.click(screen.getByLabelText("Next session"));

    await waitFor(() => expect(screen.getByRole("button", { name: /Rebind/i })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: /Rebind/i }));

    await waitFor(() => expect(capturedBody).toBeTruthy());
    expect((capturedBody as Record<string, unknown>).effective).toBe("next_session");
  });
});

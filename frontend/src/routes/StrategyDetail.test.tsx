import { afterEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { StrategyDetail } from "./StrategyDetail";
import { installFetchMock } from "@/test/renderRoute";

const STATUS_OK = {
  alpaca_endpoint: "https://paper-api.alpaca.markets",
  alpaca_data_feed: "sip",
  alpaca_credentials_present: true,
  alpaca_test_stream: false,
  operator_environment: "paper",
  operator_environment_source: "explicit",
  operator_environment_conflict: null,
};

const STRATEGY_ID = "11111111-1111-1111-1111-111111111111";
const DRAFT_VERSION_ID = "22222222-2222-2222-2222-222222222222";
const FROZEN_VERSION_ID = "33333333-3333-3333-3333-333333333333";

function mountAt(path: string): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/strategies/:strategyId" element={<StrategyDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function makeVersion(overrides: Partial<Record<string, unknown>> = {}): Record<string, unknown> {
  return {
    strategy_version_id: DRAFT_VERSION_ID,
    strategy_id: STRATEGY_ID,
    version: 1,
    status: "draft",
    payload: {
      id: DRAFT_VERSION_ID,
      strategy_id: STRATEGY_ID,
      version: 1,
      name: "Trend follower v1",
      description: null,
      feature_refs: ["close", "open"],
      entry_rules: [
        {
          name: "close_above_open",
          side: "long",
          intent_type: "entry",
          condition: {
            kind: "condition",
            left_feature: "close",
            operator: "gt",
            right_feature: "open",
          },
        },
      ],
      exit_rules: [],
      tags: [],
      created_at: "2026-04-27T00:00:00Z",
    },
    frozen_at: null,
    frozen_by: null,
    created_at: "2026-04-27T00:00:00Z",
    ...overrides,
  };
}

describe("<StrategyDetail />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders versions, latest published, and deployments using each version", async () => {
    const frozenPayload = {
      id: FROZEN_VERSION_ID,
      strategy_id: STRATEGY_ID,
      version: 1,
      name: "First publish",
      description: null,
      feature_refs: ["close"],
      entry_rules: [
        {
          name: "x",
          side: "long",
          intent_type: "entry",
          condition: { kind: "condition", left_feature: "close", operator: "gt", right_value: 100 },
        },
      ],
      exit_rules: [],
      tags: [],
      created_at: "2026-04-25T00:00:00Z",
    };
    restore = installFetchMock([
      {
        url: `/api/v1/strategies/${STRATEGY_ID}`,
        body: {
          strategy: {
            strategy_id: STRATEGY_ID,
            name: "Mean Reversion",
            description: "intraday mr",
            tags: ["intraday"],
            status: "active",
            created_at: "2026-04-20T00:00:00Z",
            latest_version_id: FROZEN_VERSION_ID,
            frozen_version_ids: [FROZEN_VERSION_ID],
            version_count: 2,
          },
          versions: [
            makeVersion({
              strategy_version_id: FROZEN_VERSION_ID,
              version: 1,
              status: "frozen",
              payload: frozenPayload,
              frozen_at: "2026-04-26T12:00:00Z",
              frozen_by: "operator-session-123",
              created_at: "2026-04-25T00:00:00Z",
            }),
            makeVersion({ version: 2 }),
          ],
        },
      },
      {
        url: "/api/v1/deployments",
        body: {
          deployments: [
            {
              deployment_id: "44444444-4444-4444-4444-444444444444",
              name: "SPY layered",
              description: null,
              strategy_version_id: FROZEN_VERSION_ID,
              watchlist_ids: [],
              subscribed_account_ids: [],
              lifecycle_status: "active",
              runtime_overrides: {},
              created_at: "2026-04-26T13:00:00Z",
              updated_at: "2026-04-26T13:00:00Z",
              started_at: null,
              stopped_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    mountAt(`/strategies/${STRATEGY_ID}`);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /Mean Reversion/i })).toBeInTheDocument();
    });
    // Latest published card + version row both surface publisher attribution.
    expect(screen.getByText("First publish")).toBeInTheDocument();
    expect(screen.getAllByText("operator-session-123").length).toBeGreaterThanOrEqual(1);
    // Deployments-using-version is linked from the frozen version row.
    expect(screen.getByText("SPY layered")).toBeInTheDocument();
    // Drafts expose an Edit button; frozen rows do not.
    expect(screen.getByRole("button", { name: /^Edit$/i })).toBeInTheDocument();
  });

  it("surfaces an awaiting panel when the strategy id is unknown", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/strategies/${STRATEGY_ID}`,
        body: { detail: "not found" },
        status: 404,
      },
      { url: "/api/v1/deployments", body: { deployments: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    mountAt(`/strategies/${STRATEGY_ID}`);
    await waitFor(() => {
      expect(screen.getByText(/Could not load strategy/i)).toBeInTheDocument();
    });
  });

  it("renders the empty 'no frozen version' state when only a draft exists", async () => {
    restore = installFetchMock([
      {
        url: `/api/v1/strategies/${STRATEGY_ID}`,
        body: {
          strategy: {
            strategy_id: STRATEGY_ID,
            name: "Brand New",
            description: null,
            tags: [],
            status: "draft",
            created_at: "2026-04-27T00:00:00Z",
            latest_version_id: null,
            frozen_version_ids: [],
            version_count: 1,
          },
          versions: [makeVersion()],
        },
      },
      { url: "/api/v1/deployments", body: { deployments: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    mountAt(`/strategies/${STRATEGY_ID}`);
    await waitFor(() => {
      expect(screen.getByText(/No frozen version yet/i)).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: /^Publish$/i })).toBeInTheDocument();
  });
});

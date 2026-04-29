import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { WalkForward } from "./WalkForward";
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

const STRATEGY_ID = "11111111-1111-1111-1111-111111111111";
const VERSION_ID = "22222222-2222-2222-2222-222222222222";
const RUN_ID = "33333333-3333-3333-3333-333333333333";

const STRATEGIES = {
  strategies: [
    {
      strategy_id: STRATEGY_ID,
      name: "Mean Reversion",
      description: null,
      tags: [],
      status: "active",
      created_at: "2026-04-20T00:00:00Z",
      latest_version_id: VERSION_ID,
      frozen_version_ids: [VERSION_ID],
      version_count: 1,
    },
  ],
};

function makeRun(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: RUN_ID,
    strategy_id: STRATEGY_ID,
    strategy_version_id: VERSION_ID,
    window_count: 8,
    passed_window_count: 6,
    metrics: {
      median_oos_sharpe: 1.18,
      oos_vs_is_decay: 0.34,
      regime_fit_score: 0.62,
      recommendation: "recommend",
    },
    created_at: "2026-04-25T12:00:00Z",
    ...overrides,
  };
}

describe("<WalkForward />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state when no runs exist", async () => {
    restore = installFetchMock([
      { url: "/api/v1/walk-forward/runs", body: { runs: [] } },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<WalkForward />);
    await waitFor(() => {
      expect(screen.getByText(/No walk-forward runs yet/i)).toBeInTheDocument();
    });
  });

  it("surfaces an awaiting panel when the runs endpoint is unregistered", async () => {
    restore = installFetchMock([
      { url: "/api/v1/walk-forward/runs", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<WalkForward />);
    await waitFor(() => {
      expect(screen.getByText(/walk-forward runs endpoint is not registered/i)).toBeInTheDocument();
    });
  });

  it("renders the runs table with strategy display name and recommendation badge", async () => {
    restore = installFetchMock([
      { url: "/api/v1/walk-forward/runs", body: { runs: [makeRun()] } },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<WalkForward />);
    await waitFor(() => {
      expect(screen.getByText("Mean Reversion")).toBeInTheDocument();
    });
    expect(screen.getByText(/^recommend$/i)).toBeInTheDocument();
    // Primary labels are not raw UUIDs.
    expect(screen.queryByText(STRATEGY_ID)).not.toBeInTheDocument();
  });

  it("opens detail and renders the summary KpiCards (median OOS Sharpe + decay + regime fit)", async () => {
    restore = installFetchMock([
      { url: `/api/v1/walk-forward/runs/${RUN_ID}`, body: makeRun() },
      { url: "/api/v1/walk-forward/runs", body: { runs: [makeRun()] } },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<WalkForward />);
    await waitFor(() => {
      expect(screen.getByText("Mean Reversion")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Open$/i }));
    await waitFor(() => {
      expect(screen.getByText(/Median OOS Sharpe/i)).toBeInTheDocument();
    });
    expect(screen.getByText("1.18")).toBeInTheDocument();
    expect(screen.getByText(/Regime fit score/i)).toBeInTheDocument();
    // Per-fold / heatmap / regime-breakdown are awaiting backend
    expect(screen.getByText(/Per-fold metrics awaiting backend/i)).toBeInTheDocument();
  });
});

import { afterEach, beforeAll, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { SimLab } from "./SimLab";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

// jsdom does not implement WebSocket; provide a stub so the streaming view
// mounts without exercising real network. The stub never delivers messages,
// so the stream renders its initial empty-state layout — all we are asserting.
class StubWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  readyState = StubWebSocket.CONNECTING;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  constructor(_url: string) {}
  addEventListener(): void {}
  removeEventListener(): void {}
  send(): void {}
  close(): void {
    this.readyState = StubWebSocket.CLOSED;
  }
}
beforeAll(() => {
  (globalThis as { WebSocket: typeof WebSocket }).WebSocket =
    StubWebSocket as unknown as typeof WebSocket;
});

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
const SESSION_A = "33333333-3333-3333-3333-333333333333";
const SESSION_B = "44444444-4444-4444-4444-444444444444";

const STRATEGIES = {
  strategies: [
    {
      strategy_id: STRATEGY_ID,
      name: "Trend Follower",
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

function makeSession(id: string, scenario: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    run_id: id,
    strategy_id: STRATEGY_ID,
    strategy_version_id: VERSION_ID,
    scenario_name: scenario,
    start: "2026-01-01T00:00:00Z",
    end: "2026-04-01T00:00:00Z",
    signal_plan_count: 12,
    simulated_order_count: 8,
    simulated_fill_count: 6,
    metrics: { sharpe: 1.42, hit_rate: 0.58 },
    created_at: "2026-04-25T12:00:00Z",
    ...overrides,
  };
}

describe("<SimLab />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state when no sessions exist", async () => {
    restore = installFetchMock([
      { url: "/api/v1/sim-lab/sessions", body: { sessions: [] } },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<SimLab />);
    await waitFor(() => {
      expect(screen.getByText(/No simulation sessions yet/i)).toBeInTheDocument();
    });
  });

  it("surfaces an awaiting panel when the sessions endpoint is unregistered", async () => {
    restore = installFetchMock([
      { url: "/api/v1/sim-lab/sessions", body: { detail: "not found" }, status: 404 },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<SimLab />);
    await waitFor(() => {
      expect(screen.getByText(/Sim Lab sessions endpoint is not registered/i)).toBeInTheDocument();
    });
  });

  it("renders the sessions table with the strategy display name (no UUIDs as primary label)", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/sim-lab/sessions",
        body: { sessions: [makeSession(SESSION_A, "Bull regime soak")] },
      },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<SimLab />);
    await waitFor(() => {
      expect(screen.getByText("Bull regime soak")).toBeInTheDocument();
    });
    expect(screen.getByText("Trend Follower")).toBeInTheDocument();
    // Primary labels should not be raw UUIDs
    expect(screen.queryByText(STRATEGY_ID)).not.toBeInTheDocument();
  });

  it("exposes the Run batch sim trigger when at least one strategy is loaded", async () => {
    restore = installFetchMock([
      { url: "/api/v1/sim-lab/sessions", body: { sessions: [] } },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<SimLab />);
    await waitFor(() => {
      const btn = screen.getByRole("button", { name: /Run batch sim/i });
      expect(btn).toBeInTheDocument();
      expect(btn).not.toBeDisabled();
    });
  });

  it("compares two sessions side by side and shows numeric deltas", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/sim-lab/sessions",
        body: {
          sessions: [
            makeSession(SESSION_A, "Bull regime soak", {
              signal_plan_count: 10,
              simulated_order_count: 7,
              simulated_fill_count: 5,
            }),
            makeSession(SESSION_B, "Bear regime soak", {
              signal_plan_count: 14,
              simulated_order_count: 9,
              simulated_fill_count: 7,
            }),
          ],
        },
      },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<SimLab />);
    await waitFor(() => {
      expect(screen.getByText("Bull regime soak")).toBeInTheDocument();
    });

    const selects = screen.getAllByRole("combobox");
    expect(selects.length).toBeGreaterThanOrEqual(2);
    fireEvent.change(selects[0], { target: { value: SESSION_A } });
    fireEvent.change(selects[1], { target: { value: SESSION_B } });

    // Both compare cards render, with the side panel labels.
    await waitFor(() => {
      expect(screen.getByText("Left")).toBeInTheDocument();
      expect(screen.getByText("Right")).toBeInTheDocument();
    });
    // Side-by-side comparison surfaces the metrics block ("vs" inline label).
    expect(screen.getAllByText(/^vs/).length).toBeGreaterThanOrEqual(1);
  });
});

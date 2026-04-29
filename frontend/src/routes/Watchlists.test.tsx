import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Watchlists } from "./Watchlists";
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

describe("<Watchlists />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state with no watchlists", async () => {
    restore = installFetchMock([
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Watchlists />);
    await waitFor(() => {
      expect(screen.getByText(/No watchlists yet/i)).toBeInTheDocument();
    });
  });

  it("renders a watchlist card on the happy path", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/watchlists",
        body: {
          watchlists: [
            {
              watchlist_id: "22222222-2222-2222-2222-222222222222",
              name: "Liquid Caps",
              description: null,
              kind: "static",
              static_symbols: ["AAPL", "MSFT"],
              dynamic_rules: null,
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              latest_snapshot_id: null,
              snapshot_count: 0,
              status: "active",
              archived_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Watchlists />);
    await waitFor(() => {
      expect(screen.getByText("Liquid Caps")).toBeInTheDocument();
    });
    expect(screen.getByText(/static entries/i)).toBeInTheDocument();
  });

  it("opens a dynamic watchlist with refresh evidence and archive-first copy", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      {
        url: /\/api\/v1\/watchlists\/22222222-2222-2222-2222-222222222222$/,
        body: {
          watchlist: {
            watchlist_id: "22222222-2222-2222-2222-222222222222",
            name: "Alpaca Day Gainers Dynamic",
            description: "Refreshes from screener evidence",
            kind: "dynamic",
            static_symbols: [],
            dynamic_rules: {
              universe: "us_equities",
              filters: [],
              source_type: "screener_version",
              screener_id: "scr-1",
              screener_version_id: "ver-1",
              refresh_policy: "manual",
              approval_policy: "operator_review",
            },
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            latest_snapshot_id: "snap-1",
            snapshot_count: 1,
            status: "active",
            archived_at: null,
          },
          snapshots: [
            {
              watchlist_snapshot_id: "snap-1",
              watchlist_id: "22222222-2222-2222-2222-222222222222",
              taken_at: new Date().toISOString(),
              symbols: ["NVDA", "AMD"],
              note: "operator-triggered refresh",
              source_run_id: "run-1",
              source_label: "Day Gainers rerun",
              added_symbols: ["AMD"],
              removed_symbols: ["TSLA"],
              stayed_symbols: ["NVDA"],
              evidence: { alpaca_market_list: { provider: "alpaca" } },
            },
          ],
        },
      },
      {
        url: "/api/v1/watchlists",
        body: {
          watchlists: [
            {
              watchlist_id: "22222222-2222-2222-2222-222222222222",
              name: "Alpaca Day Gainers Dynamic",
              description: "Refreshes from screener evidence",
              kind: "dynamic",
              static_symbols: [],
              dynamic_rules: { source_type: "screener_version" },
              created_at: new Date().toISOString(),
              updated_at: new Date().toISOString(),
              latest_snapshot_id: "snap-1",
              snapshot_count: 1,
              status: "active",
              archived_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Watchlists />);
    await user.click(await screen.findByRole("button", { name: /Open/i }));
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Refresh$/i })).toBeInTheDocument();
    });
    expect(screen.getAllByText(/Screener refresh/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Day Gainers rerun/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/\+1 \/ -1 \/ =1/)).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
    expect(screen.getByText("AMD")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Archive$/i })).toBeInTheDocument();
  });

  it("surfaces a degraded read state when list fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/watchlists", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Watchlists />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load watchlists/i)).toBeInTheDocument();
    });
  });
});

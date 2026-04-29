import { afterEach, describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { Screeners } from "./Screeners";
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

function mount(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Screeners />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("<Screeners />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state with no screeners", async () => {
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/screeners/templates", body: { templates: [] } },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
      { url: "/api/v1/screeners", body: { screeners: [] } },
    ]);
    mount();
    await waitFor(() => {
      expect(screen.getByText(/No saved screeners yet/i)).toBeInTheDocument();
    });
    expect(screen.getAllByRole("button", { name: /New Screener/i }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Alpaca Market Lists/i)).toBeInTheDocument();
  });

  it("lists screeners with their last-run badge and operator-readable name", async () => {
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/screeners/templates", body: { templates: [] } },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
      {
        url: "/api/v1/screeners",
        body: {
          screeners: [
            {
              id: "11111111-1111-1111-1111-111111111111",
              name: "Volume Surge",
              description: "Liquid large caps with relative volume > 1.5x",
              tags: ["intraday", "discovery"],
              status: "active",
              created_at: "2026-04-28T01:00:00Z",
              last_run_at: "2026-04-28T01:30:00Z",
              last_run_id: "22222222-2222-2222-2222-222222222222",
              version_count: 2,
              latest_version_id: "33333333-3333-3333-3333-333333333333",
            },
          ],
        },
      },
    ]);
    mount();
    await waitFor(() => {
      expect(screen.getByText("Volume Surge")).toBeInTheDocument();
    });
    // Doctrine: operator-readable last-run timestamp, not the run UUID.
    expect(screen.getByText(/last run/i)).toBeInTheDocument();
    expect(screen.queryByText(/22222222/)).not.toBeInTheDocument();
  });

  it("opens the create drawer when the operator clicks New Screener", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      {
        url: "/api/v1/screeners/templates",
        body: { templates: [] },
      },
      {
        url: "/api/v1/market-lists",
        body: {
          market_lists: [
            {
              key: "day_gainers",
              label: "Day Gainers",
              category: "movers",
              provider: "alpaca",
              source: "alpaca",
              description: "Current session gainers",
            },
          ],
        },
      },
      {
        url: "/api/v1/screeners/fields",
        body: {
          fields: [
            { key: "price", label: "Last price", unit: "$", value_type: "number", supported_operators: ["gte", "lte"] },
            { key: "relative_volume", label: "Relative volume", unit: "x", value_type: "number", supported_operators: ["gte"] },
            { key: "broker.fractionable", label: "Fractionable", unit: null, value_type: "boolean", supported_operators: ["eq"] },
          ],
        },
      },
      {
        url: "/api/v1/screeners/presets",
        body: {
          presets: [
            { key: "liquid_large_caps", label: "Liquid Large Caps", symbol_count: 42, sample_symbols: ["AAPL", "MSFT"] },
          ],
        },
      },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/screeners", body: { screeners: [] } },
    ]);
    mount();
    const buttons = await screen.findAllByRole("button", { name: /New Screener/i });
    await user.click(buttons[0]);
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: /^New Screener$/i })).toBeInTheDocument();
    });
    // Universe Source picker rendered (the picker carries an UPPERCASE label).
    expect(screen.getAllByText(/Universe source/i).length).toBeGreaterThanOrEqual(1);
    // Default criterion section shows up.
    expect(screen.getAllByText(/Criteria/i).length).toBeGreaterThanOrEqual(1);
    // Doctrine guard: the form never asks the operator for a Watchlist UUID
    // — the picker either lists watchlists by name or shows the empty-state.
    expect(screen.queryByText(/UUID/i)).not.toBeInTheDocument();
  });

  it("compiles AI advisory text into visible typed rules before create", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/screeners/templates", body: { templates: [] } },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
      {
        url: "/api/v1/screeners/ai/interpret",
        method: "POST",
        body: {
          advisory_only: true,
          suggested_template_keys: ["alpaca_day_gainers"],
          universe_source: { kind: "market_list", symbols: [], market_list_key: "day_gainers" },
          expression: {
            kind: "all",
            children: [
              {
                kind: "criterion",
                criterion: {
                  metric: "broker.fractionable",
                  operator: "eq",
                  value: true,
                  value_max: null,
                  label: "Fractionable on Alpaca",
                },
              },
            ],
          },
          assumptions: ["Using Alpaca market list data"],
          unsupported_clauses: [],
          audit_preview: {},
        },
      },
      { url: "/api/v1/screeners", body: { screeners: [] } },
    ]);
    mount();
    await user.click(await screen.findByRole("button", { name: /AI Composer/i }));
    await user.click(screen.getByRole("button", { name: /Compile advisory rules/i }));
    await waitFor(() => {
      expect(screen.getAllByText(/Fractionable on Alpaca/i).length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText(/advisory/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/submit order/i)).not.toBeInTheDocument();
  });
});

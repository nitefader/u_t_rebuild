import { afterEach, describe, expect, it, vi } from "vitest";
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
const EMPTY_SCHEDULES = { schedules: [] };
const EMPTY_PRESETS = { presets: [] };

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
      { url: "/api/v1/screeners/presets", body: EMPTY_PRESETS },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
      { url: "/api/v1/discovery-schedules", body: EMPTY_SCHEDULES },
      { url: "/api/v1/screeners", body: { screeners: [] } },
    ]);
    mount();
    await waitFor(() => {
      expect(screen.getByText(/No saved screeners yet/i)).toBeInTheDocument();
    });
    expect(screen.getAllByRole("button", { name: /New Screener/i }).length).toBeGreaterThanOrEqual(
      1,
    );
    expect(screen.getByText(/Alpaca Market Lists/i)).toBeInTheDocument();
  });

  it("surfaces Alpaca market-list load failures instead of an empty provider panel", async () => {
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/screeners/templates", body: { templates: [] } },
      { url: "/api/v1/screeners/presets", body: EMPTY_PRESETS },
      { url: "/api/v1/market-lists", body: { detail: "Alpaca provider timed out" }, status: 503 },
      { url: "/api/v1/discovery-schedules", body: EMPTY_SCHEDULES },
      { url: "/api/v1/screeners", body: { screeners: [] } },
    ]);
    mount();
    expect(await screen.findByText(/Alpaca market lists unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/Alpaca provider timed out/i)).toBeInTheDocument();
  });

  it("keeps Screener templates behind the browse drawer", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      {
        url: "/api/v1/screeners/templates",
        body: {
          templates: [
            {
              key: "momentum_breakout",
              label: "Momentum Breakout",
              category: "intraday",
              description: "Relative volume and broker capability starter",
              universe_source: { kind: "preset", symbols: [], preset: "liquid_large_caps" },
              expression: {
                kind: "criterion",
                criterion: {
                  metric: "relative_volume",
                  operator: "gte",
                  value: 1.5,
                  value_max: null,
                  label: "Relative volume above 1.5x",
                },
              },
              sort_metric: "relative_volume",
              sort_descending: true,
              timeframe: "1d",
              tags: ["momentum", "alpaca"],
            },
          ],
        },
      },
      {
        url: "/api/v1/screeners/presets",
        body: {
          presets: [
            {
              key: "liquid_large_caps",
              label: "Liquid Large Caps",
              symbol_count: 43,
              sample_symbols: ["AAPL", "MSFT", "NVDA"],
            },
          ],
        },
      },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
      { url: "/api/v1/discovery-schedules", body: EMPTY_SCHEDULES },
      { url: "/api/v1/screeners", body: { screeners: [] } },
    ]);
    mount();
    expect(await screen.findByRole("button", { name: /Browse templates/i })).toBeInTheDocument();
    expect(screen.queryByText("Momentum Breakout")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Browse templates/i }));
    expect(await screen.findByRole("heading", { name: /Screener templates/i })).toBeInTheDocument();
    expect(screen.getByText("Momentum Breakout")).toBeInTheDocument();
    expect(screen.getByText(/They are not Watchlists/i)).toBeInTheDocument();
    expect(screen.getByText(/43 symbols/i)).toBeInTheDocument();
    expect(screen.getByText(/samples: AAPL, MSFT, NVDA/i)).toBeInTheDocument();
  });

  it("lists screeners with their last-run badge and operator-readable name", async () => {
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/screeners/templates", body: { templates: [] } },
      { url: "/api/v1/screeners/presets", body: EMPTY_PRESETS },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
      {
        url: "/api/v1/discovery-schedules",
        body: {
          schedules: [
            {
              schedule_id: "99999999-9999-9999-9999-999999999999",
              name: "Volume Surge open",
              target_kind: "screener_run",
              screener_id: "11111111-1111-1111-1111-111111111111",
              screener_version_id: "33333333-3333-3333-3333-333333333333",
              watchlist_id: null,
              cadence: "daily",
              interval_minutes: null,
              time_of_day: "09:15",
              weekdays: [0, 1, 2, 3, 4],
              timezone_name: "America/New_York",
              session_start: null,
              session_end: null,
              approval_policy: "operator_review",
              enabled: true,
              status: "active",
              created_at: "2026-04-28T01:00:00Z",
              updated_at: "2026-04-28T01:00:00Z",
              last_attempt_at: null,
              last_success_at: null,
              next_run_at: "2026-04-29T13:15:00Z",
              last_status: null,
              last_error: null,
              last_screener_run_id: null,
              last_watchlist_snapshot_id: null,
              execution_count: 0,
              audit_events: [],
            },
          ],
        },
      },
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
    expect(screen.getAllByText(/last run/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/22222222/)).not.toBeInTheDocument();
    expect(screen.getByText(/1 scheduled/i)).toBeInTheDocument();
    expect(screen.getByText(/Next automatic run/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Schedule/i })).toBeInTheDocument();
  });

  it("opens the create drawer when the operator clicks New Screener", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      {
        url: "/api/v1/screeners/templates",
        body: { templates: [] },
      },
      { url: "/api/v1/discovery-schedules", body: EMPTY_SCHEDULES },
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
            {
              key: "price",
              label: "Last price",
              unit: "$",
              value_type: "number",
              supported_operators: ["gte", "lte"],
            },
            {
              key: "relative_volume",
              label: "Relative volume",
              unit: "x",
              value_type: "number",
              supported_operators: ["gte"],
            },
            {
              key: "broker.fractionable",
              label: "Fractionable",
              unit: null,
              value_type: "boolean",
              supported_operators: ["eq"],
            },
          ],
        },
      },
      {
        url: "/api/v1/screeners/presets",
        body: {
          presets: [
            {
              key: "liquid_large_caps",
              label: "Liquid Large Caps",
              symbol_count: 42,
              sample_symbols: ["AAPL", "MSFT"],
            },
          ],
        },
      },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      {
        url: "/api/v1/screeners",
        method: "POST",
        body: {
          screener: {
            id: "44444444-4444-4444-4444-444444444444",
            name: "Alpaca Fractionable Movers",
            description: "Day gainers with broker capability gates",
            tags: ["intraday", "alpaca"],
            status: "active",
            created_at: "2026-04-29T10:00:00Z",
            last_run_at: null,
            last_run_id: null,
            version_count: 1,
            latest_version_id: "55555555-5555-5555-5555-555555555555",
          },
          versions: [
            {
              id: "55555555-5555-5555-5555-555555555555",
              screener_id: "44444444-4444-4444-4444-444444444444",
              version: 1,
              name: "Alpaca Fractionable Movers",
              description: null,
              universe_source: { kind: "market_list", symbols: [], market_list_key: "day_gainers" },
              criteria: [],
              expression: null,
              timeframe: "5m",
              source_preference: "alpaca",
              sort_metric: "relative_volume",
              sort_descending: false,
              max_results: 25,
              tags: ["intraday", "alpaca"],
              created_at: "2026-04-29T10:00:00Z",
            },
          ],
          last_run: null,
        },
      },
      { url: "/api/v1/screeners", body: { screeners: [] } },
    ]);
    mount();
    expect((await screen.findAllByText(/live Alpaca/i)).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText(/up to 50 symbols/i)).toBeInTheDocument();
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
    await user.click(screen.getByText(/Advanced run settings/i));
    expect(screen.queryByText(/yahoo/i)).not.toBeInTheDocument();
    await user.clear(screen.getByLabelText(/Display name/i));
    await user.type(screen.getByLabelText(/Display name/i), "Alpaca Fractionable Movers");
    await user.selectOptions(screen.getByLabelText(/Timeframe/i), "5m");
    await user.selectOptions(screen.getByLabelText(/Source preference/i), "alpaca");
    await user.selectOptions(screen.getByLabelText(/Sort metric/i), "relative_volume");
    await user.selectOptions(screen.getByLabelText(/Sort direction/i), "asc");
    await user.clear(screen.getByLabelText(/Max results/i));
    await user.type(screen.getByLabelText(/Max results/i), "25");
    await user.type(screen.getByLabelText(/Tags/i), "intraday, alpaca");
    await user.click(screen.getByRole("button", { name: /^Create Screener$/i }));
    await waitFor(() => {
      const createCall = vi
        .mocked(fetch)
        .mock.calls.find(
          ([url, init]) => String(url).endsWith("/api/v1/screeners") && init?.method === "POST",
        );
      expect(createCall).toBeTruthy();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        name: "Alpaca Fractionable Movers",
        timeframe: "5m",
        source_preference: "alpaca",
        sort_metric: "relative_volume",
        sort_descending: false,
        max_results: 25,
        tags: ["intraday", "alpaca"],
      });
    });
  });

  it("compiles AI advisory text into visible typed rules before create", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/screeners/templates", body: { templates: [] } },
      { url: "/api/v1/screeners/presets", body: EMPTY_PRESETS },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
      { url: "/api/v1/discovery-schedules", body: EMPTY_SCHEDULES },
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

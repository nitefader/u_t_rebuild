import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ScreenerDetail } from "./ScreenerDetail";
import { installFetchMock } from "@/test/renderRoute";

const SCREENER_ID = "11111111-1111-1111-1111-111111111111";
const VERSION_ID = "22222222-2222-2222-2222-222222222222";
const RUN_NEW = "33333333-3333-3333-3333-333333333333";
const RUN_OLD = "44444444-4444-4444-4444-444444444444";

function mount(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/screeners/${SCREENER_ID}`]}>
        <Routes>
          <Route path="/screeners/:screenerId" element={<ScreenerDetail />} />
          <Route path="/screeners" element={<div>Screeners list</div>} />
          <Route path="/watchlists" element={<div>Watchlists list</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function detailBody() {
  return {
    screener: {
      id: SCREENER_ID,
      name: "Alpaca Fractionable Movers",
      description: "Day gainers with Alpaca capability gates",
      tags: ["alpaca"],
      status: "active",
      created_at: "2026-04-28T13:00:00Z",
      last_run_at: "2026-04-28T13:05:00Z",
      last_run_id: RUN_NEW,
      version_count: 1,
      latest_version_id: VERSION_ID,
    },
    versions: [
      {
        id: VERSION_ID,
        screener_id: SCREENER_ID,
        version: 1,
        name: "AI compiled movers",
        description: null,
        universe_source: { kind: "market_list", symbols: [], market_list_key: "day_gainers" },
        criteria: [],
        expression: {
          kind: "all",
          children: [
            {
              kind: "any",
              children: [
                {
                  kind: "criterion",
                  criterion: {
                    metric: "relative_volume",
                    operator: "gte",
                    value: 1.5,
                    value_max: null,
                    label: "Relative volume above 1.5",
                  },
                },
              ],
            },
            {
              kind: "criterion",
              criterion: {
                metric: "broker.fractionable",
                operator: "eq",
                value: true,
                value_max: null,
                label: "Fractionable at Alpaca",
              },
            },
          ],
        },
        timeframe: "1d",
        source_preference: "auto",
        sort_metric: "relative_volume",
        sort_descending: true,
        max_results: 200,
        tags: ["alpaca"],
        created_at: "2026-04-28T13:00:00Z",
      },
    ],
    last_run: null,
  };
}

function runBody(id: string, startedAt: string, matched = 2) {
  return {
    id,
    screener_id: SCREENER_ID,
    screener_version_id: VERSION_ID,
    started_at: startedAt,
    completed_at: startedAt,
    status: "completed",
    run_kind: id === RUN_OLD ? "run" : "rerun",
    parent_run_id: id === RUN_NEW ? RUN_OLD : null,
    universe_size: 3,
    matched_count: matched,
    results: [
      {
        symbol: "NVDA",
        matched: true,
        metrics: {
          "broker.name": "NVIDIA Corp",
          "broker.fractionable": true,
          "broker.tradable": true,
          relative_volume: 2.1,
        },
        failed_criteria: [],
        passed_criteria: ["Fractionable at Alpaca"],
        blocked_reasons: [],
        evidence: { asset_capability: { provider: "alpaca" } },
        score: 2.1,
        sparkline: [1, 2, 3],
      },
      {
        symbol: "AMD",
        matched: true,
        metrics: {
          "broker.name": "Advanced Micro Devices",
          "broker.fractionable": true,
          "broker.tradable": true,
          relative_volume: 1.9,
        },
        failed_criteria: [],
        passed_criteria: ["Fractionable at Alpaca"],
        blocked_reasons: [],
        evidence: { asset_capability: { provider: "alpaca" } },
        score: 1.9,
        sparkline: [1, 1.5, 2],
      },
    ],
    error: null,
    sources_used: ["alpaca_market_list", "alpaca_assets"],
    source_evidence: { alpaca_market_list: { provider: "alpaca", feed: "sip" } },
    source_freshness: { alpaca_market_list: { as_of: "2026-04-28T13:05:00Z" } },
    audit_events: [],
    cache_hit_rate: 1,
    operator_session_id: null,
  };
}

function commonRoutes() {
  return [
    {
      url: /\/api\/v1\/screeners\/11111111-1111-1111-1111-111111111111\/runs$/,
      body: { runs: [runBody(RUN_NEW, "2026-04-28T13:05:00Z"), runBody(RUN_OLD, "2026-04-28T13:00:00Z", 1)] },
    },
    {
      url: /\/api\/v1\/screeners\/11111111-1111-1111-1111-111111111111$/,
      body: detailBody(),
    },
    {
      url: "/api/v1/screeners/fields",
      body: {
        fields: [
          { key: "relative_volume", label: "Relative volume", value_type: "number", unit: "x", supported_operators: ["gte"] },
          { key: "broker.fractionable", label: "Fractionable at Alpaca", value_type: "boolean", unit: null, supported_operators: ["eq"] },
          { key: "broker.tradable", label: "Tradable at Alpaca", value_type: "boolean", unit: null, supported_operators: ["eq"] },
        ],
      },
    },
    { url: "/api/v1/watchlists", body: { watchlists: [] } },
    { url: "/api/v1/screeners/presets", body: { presets: [] } },
    { url: "/api/v1/market-lists", body: { market_lists: [] } },
    {
      url: /\/api\/v1\/screeners\/runs\/33333333-3333-3333-3333-333333333333\/rerun$/,
      method: "POST",
      body: runBody("55555555-5555-5555-5555-555555555555", "2026-04-28T13:10:00Z"),
    },
    {
      url: /\/api\/v1\/screeners\/runs\/33333333-3333-3333-3333-333333333333\/diff/,
      body: {
        run_id: RUN_NEW,
        against_run_id: RUN_OLD,
        added: ["AMD"],
        removed: ["TSLA"],
        stayed: ["NVDA"],
        newly_failed: [],
        reason_changes: [],
      },
    },
    {
      url: /\/api\/v1\/screeners\/11111111-1111-1111-1111-111111111111\/archive$/,
      method: "POST",
      body: {
        ...detailBody(),
        screener: { ...detailBody().screener, status: "archived" },
      },
    },
    {
      url: /\/api\/v1\/screeners\/runs\/33333333-3333-3333-3333-333333333333\/save-as-watchlist$/,
      method: "POST",
      body: {
        watchlist_id: "66666666-6666-6666-6666-666666666666",
        name: "Dynamic movers",
        symbol_count: 2,
      },
    },
    {
      url: /\/api\/v1\/screeners\/11111111-1111-1111-1111-111111111111\/versions$/,
      method: "POST",
      body: {
        ...detailBody().versions[0],
        id: "77777777-7777-7777-7777-777777777777",
        version: 2,
      },
    },
    {
      url: /\/api\/v1\/screeners\/11111111-1111-1111-1111-111111111111\/delete$/,
      method: "POST",
      body: {},
    },
  ];
}

describe("<ScreenerDetail />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("reruns, compares, archives, and saves a dynamic Watchlist", async () => {
    const user = userEvent.setup();
    restore = installFetchMock(commonRoutes());
    mount();

    await screen.findByText("Alpaca Fractionable Movers");
    expect(screen.getByRole("button", { name: /Run latest version/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Alpaca market list/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/alpaca_market_list/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Compare with previous run$/i }));
    await waitFor(() => {
      expect(screen.getByText("Added")).toBeInTheDocument();
      expect(screen.getAllByText("AMD").length).toBeGreaterThanOrEqual(1);
    });

    await user.click(screen.getByRole("button", { name: /^Rerun selected run$/i }));
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/screeners/runs/${RUN_NEW}/rerun`),
        expect.objectContaining({ method: "POST" }),
      );
    });

    await user.click(screen.getByRole("button", { name: /^Archive$/i }));
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/screeners/${SCREENER_ID}/archive`),
        expect.objectContaining({ method: "POST" }),
      );
    });

    await user.click(screen.getByRole("button", { name: /Save matched symbols as Watchlist/i }));
    await user.selectOptions(screen.getByLabelText(/Watchlist kind/i), "dynamic");
    await user.clear(screen.getByLabelText(/Watchlist name/i));
    await user.type(screen.getByLabelText(/Watchlist name/i), "Dynamic movers");
    await user.click(screen.getByRole("button", { name: /^Create Watchlist$/i }));
    await waitFor(() => {
      expect(screen.getByText(/Watchlist created/i)).toBeInTheDocument();
    });
    const saveCall = vi.mocked(fetch).mock.calls.find(([url]) =>
      String(url).includes("/save-as-watchlist"),
    );
    expect(JSON.parse(String(saveCall?.[1]?.body))).toMatchObject({ kind: "dynamic" });
  });

  it("preserves expression-backed version logic when adding a version", async () => {
    const user = userEvent.setup();
    restore = installFetchMock(commonRoutes());
    mount();

    await screen.findByText("Alpaca Fractionable Movers");
    await user.click(screen.getByRole("button", { name: /Duplicate version/i }));
    await waitFor(() => {
      expect(screen.getByText(/Preserved boolean tree/i)).toBeInTheDocument();
      expect(screen.getByText("ALL")).toBeInTheDocument();
      expect(screen.getByText("ANY")).toBeInTheDocument();
    });
    await user.click(screen.getByRole("button", { name: /Save duplicate version/i }));

    await waitFor(() => {
      const versionCall = vi.mocked(fetch).mock.calls.find(([url]) =>
        String(url).endsWith(`/api/v1/screeners/${SCREENER_ID}/versions`),
      );
      expect(versionCall).toBeTruthy();
      const body = JSON.parse(String(versionCall?.[1]?.body));
      expect(body.expression?.kind).toBe("all");
      expect(body.expression?.children?.[0]?.kind).toBe("any");
    });
  });

  it("posts delete only after typed confirmation and audit reason", async () => {
    const user = userEvent.setup();
    restore = installFetchMock(commonRoutes());
    mount();

    await screen.findByText("Alpaca Fractionable Movers");
    await user.click(screen.getByRole("button", { name: /^Delete$/i }));
    await user.type(screen.getByLabelText(/Type "Alpaca Fractionable Movers"/i), "Alpaca Fractionable Movers");
    await user.type(screen.getByLabelText(/Reason/i), "cleanup unused draft");
    await user.click(screen.getByRole("button", { name: /Delete Screener/i }));
    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/screeners/${SCREENER_ID}/delete`),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});

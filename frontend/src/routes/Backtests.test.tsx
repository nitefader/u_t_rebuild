import { afterEach, describe, expect, it } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { Backtests } from "./Backtests";
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

function makeRun(): Record<string, unknown> {
  return {
    run_id: RUN_ID,
    strategy_id: STRATEGY_ID,
    strategy_version_id: VERSION_ID,
    watchlist_snapshot_id: null,
    universe: ["SPY", "QQQ"],
    timeframe: "1d",
    start: "2026-01-01T00:00:00Z",
    end: "2026-04-01T00:00:00Z",
    initial_capital: 100_000,
    cost_model: { commissions: 0, slippage_bps: 5, borrow_cost: 0 },
    status: "completed",
    status_history: [
      { status: "queued", at: "2026-04-25T12:00:00Z" },
      { status: "running", at: "2026-04-25T12:01:00Z" },
      { status: "completed", at: "2026-04-25T12:05:00Z" },
    ],
    bar_count: 60,
    signal_plan_count: 12,
    simulated_trade_count: 8,
    metrics: {},
    results: {},
    created_at: "2026-04-25T12:00:00Z",
  };
}

describe("<Backtests />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state when no runs exist", async () => {
    restore = installFetchMock([
      { url: "/api/v1/research/backtests", body: { runs: [] } },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Backtests />);
    await waitFor(() => {
      expect(screen.getByText(/No backtest runs yet/i)).toBeInTheDocument();
    });
  });

  it("surfaces an awaiting panel when the runs endpoint is unregistered", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/research/backtests",
        body: { detail: "not found" },
        status: 404,
      },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Backtests />);
    await waitFor(() => {
      expect(screen.getByText(/research backtests namespace is not yet registered/i)).toBeInTheDocument();
    });
  });

  it("renders the runs table with the strategy display name (no UUIDs as primary label)", async () => {
    restore = installFetchMock([
      { url: "/api/v1/research/backtests", body: { runs: [makeRun()] } },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Backtests />);
    await waitFor(() => {
      expect(screen.getByText("Mean Reversion")).toBeInTheDocument();
    });
    // Universe rendered as ticker, not UUID
    expect(screen.getByText("SPY, QQQ")).toBeInTheDocument();
    // Status badge shows the human-readable status
    expect(screen.getByText("completed")).toBeInTheDocument();
    // Strategy id is NOT the primary label (full UUID should not appear in the row)
    expect(screen.queryByText(STRATEGY_ID)).not.toBeInTheDocument();
  });

  it("opens detail and renders metrics + per-regime + trade ledger from passthrough payloads", async () => {
    // Route matching is by `url.includes`; the most-specific paths come first
    // so `/results` and `/metrics` resolve before the bare list URL.
    restore = installFetchMock([
      // Metrics envelope including additive fields the schema must accept.
      {
        url: `/api/v1/research/backtests/${RUN_ID}/metrics`,
        body: {
          run_id: RUN_ID,
          status: "completed",
          metrics: {
            cagr: 0.183,
            sharpe: 1.42,
            sortino: 2.01,
            calmar: 1.05,
            max_drawdown: -0.082,
            hit_rate: 0.56,
            profit_factor: 1.78,
            expectancy: 24.5,
            exposure: 0.42,
            turnover: 1.2,
            time_in_market: 0.41,
            // Additive field that must not break the schema
            sharpe_oos: 1.18,
          },
          cost_model: {
            commissions: 0,
            slippage_bps: 5,
            borrow_cost: 0,
            // Additive field
            settlement_days: 1,
          },
          // Additive top-level field
          generated_at: "2026-04-25T12:05:00Z",
        },
      },
      // Results envelope with regime breakdown + trades.
      {
        url: `/api/v1/research/backtests/${RUN_ID}/results`,
        body: {
          run_id: RUN_ID,
          status: "completed",
          equity_curve: [
            { timestamp: "2026-01-02T00:00:00Z", equity: 100_000 },
            { timestamp: "2026-02-02T00:00:00Z", equity: 105_000 },
            { timestamp: "2026-03-02T00:00:00Z", equity: 109_500 },
          ],
          drawdown_series: [
            { timestamp: "2026-01-02T00:00:00Z", drawdown: 0 },
            { timestamp: "2026-02-02T00:00:00Z", drawdown: -0.03 },
            { timestamp: "2026-03-02T00:00:00Z", drawdown: -0.082 },
          ],
          per_symbol_breakdown: [
            { symbol: "SPY", trades: 5, win_rate: 0.6, return_pct: 0.04, pnl: 240 },
          ],
          trade_ledger: [
            {
              symbol: "SPY",
              side: "long",
              quantity: 10,
              entry_price: 510,
              exit_price: 525,
              pnl: 150,
              opened_at: "2026-02-01T14:00:00Z",
              closed_at: "2026-02-03T15:30:00Z",
              regime: "trending",
            },
          ],
          per_regime_metrics: {
            trending: { bars: 35, trades: 6, hit_rate: 0.6, sharpe: 1.6, return_pct: 0.06 },
            sideways: { bars: 25, trades: 2, hit_rate: 0.5, sharpe: 0.4, return_pct: 0.005 },
          },
          // Additive top-level field
          regime_summary: { dominant: "trending" },
        },
      },
      // Detail GET (called when drilling in)
      {
        url: `/api/v1/research/backtests/${RUN_ID}`,
        body: makeRun(),
      },
      { url: "/api/v1/research/backtests", body: { runs: [makeRun()] } },
      { url: "/api/v1/strategies", body: STRATEGIES },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Backtests />);

    await waitFor(() => {
      expect(screen.getByText("Mean Reversion")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /^Open$/i }));

    await waitFor(() => {
      expect(screen.getAllByText("Sharpe").length).toBeGreaterThanOrEqual(1);
    });
    // Metric cards (B4)
    expect(screen.getByText("1.42")).toBeInTheDocument();
    // Per-regime table (B6) renders regime labels (also appears in trade ledger)
    expect(screen.getAllByText("trending").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("sideways")).toBeInTheDocument();
    // Trade ledger (B3) renders symbol + regime tag
    expect(screen.getAllByText("SPY").length).toBeGreaterThanOrEqual(1);
  });
});

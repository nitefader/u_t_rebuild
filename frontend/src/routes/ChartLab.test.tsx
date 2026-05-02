import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const chartCalls = vi.hoisted(() => ({
  props: [] as Array<{
    symbol: string;
    bars: Array<{ isWarmup?: boolean }>;
    visibleFeatureKeys: string[];
    showSignalLabels: boolean;
    density: { showWarmupBars?: boolean };
    chartMode: "candles" | "line";
    resetZoomSignal: number;
    onBarClick?: (index: number) => void;
  }>,
}));

vi.mock("@/components/charts/StrategyPreviewChart", () => ({
  StrategyPreviewChart: (props: {
    symbol: string;
    bars: Array<{ isWarmup?: boolean }>;
    visibleFeatureKeys: string[];
    showSignalLabels?: boolean;
    density: { showWarmupBars?: boolean };
    chartMode: "candles" | "line";
    resetZoomSignal: number;
    onBarClick?: (index: number) => void;
  }) => {
    chartCalls.props.push(props as never);
    return (
      <div data-testid="strategy-preview-chart">
        <span data-testid="chart-mock-signal-label-flag">
          {props.showSignalLabels ? "labels-on" : "labels-off"}
        </span>
        <span data-testid="chart-mock-mode">{props.chartMode}</span>
        <span data-testid="chart-mock-reset">{props.resetZoomSignal}</span>
        {props.symbol} - {props.bars.filter((bar) => bar.isWarmup).length} warm-up -{" "}
        {props.visibleFeatureKeys.length} overlays
        <button
          type="button"
          data-testid="simulate-chart-bar-click"
          onClick={() => props.onBarClick?.(1)}
        >
          Select bar 1
        </button>
      </div>
    );
  },
}));

import { ChartLab } from "./ChartLab";

const STRATEGY_ID = "11111111-1111-1111-1111-111111111111";
const VERSION_ID = "22222222-2222-2222-2222-222222222222";

const STRATEGIES_LIST = {
  strategies: [
    {
      strategy_id: STRATEGY_ID,
      name: "Daily Breakout",
      description: null,
      tags: [],
      status: "draft",
      created_at: "2026-04-01T00:00:00Z",
      latest_version_id: VERSION_ID,
      frozen_version_ids: [],
      version_count: 1,
    },
  ],
};

const VERSIONS_LIST = [
  {
    strategy_version_id: VERSION_ID,
    strategy_id: STRATEGY_ID,
    version: 1,
    status: "draft",
    payload: {
      id: VERSION_ID,
      strategy_id: STRATEGY_ID,
      version: 1,
      name: "Daily Breakout",
      feature_refs: ["5m.ema:length=20[0]", "5m.rsi:length=14[0]"],
      entry_rules: [],
      exit_rules: [],
      tags: [],
      created_at: "2026-04-01T00:00:00Z",
    },
    frozen_at: null,
    frozen_by: null,
    created_at: "2026-04-01T00:00:00Z",
  },
];

const EMA_KEY =
  "v1|symbol|5m|technical.ema|source=close|params={\"length\":20}|lookback=0|shift=0";
const RSI_KEY =
  "v1|symbol|5m|technical.rsi|source=close|params={\"length\":14}|lookback=0|shift=0";
const EMA_REF = "5m.ema:length=20";
const RSI_REF = "5m.rsi:length=14";

const FEATURE_LIBRARY = {
  timeframe: "5m",
  features: [
    {
      feature_key: EMA_KEY,
      feature_ref: EMA_REF,
      name: "EMA 20",
      timeframe: "5m",
      indicator_type: "technical.ema",
      group: "Trend",
      origin: "manual",
      badge: "Manual",
    },
    {
      feature_key: RSI_KEY,
      feature_ref: RSI_REF,
      name: "RSI 14",
      timeframe: "5m",
      indicator_type: "technical.rsi",
      group: "Momentum",
      origin: "manual",
      badge: "Manual",
    },
  ],
};

function previewResponse(args: { strategy?: boolean } = {}) {
  const strategy = args.strategy ?? false;
  return {
    session: {
      id: "33333333-3333-3333-3333-333333333333",
      mode: "chart_lab_batch",
      symbol: "SPY",
      timeframe: "5m",
      start: "2026-04-01T00:00:00Z",
      end: "2026-04-15T23:59:59Z",
      strategy_version_id: strategy ? VERSION_ID : null,
      metadata: {
        provider: "alpaca",
        adjustment_policy: "split_dividend_adjusted",
      },
    },
    feature_plan: {
      id: "44444444-4444-4444-4444-444444444444",
      strategy_version_id: strategy
        ? VERSION_ID
        : "00000000-0000-0000-0000-000000000000",
      consumer: "chart_lab",
      symbols: ["SPY"],
      timeframes: ["5m"],
      feature_specs: [],
      feature_keys: strategy ? [EMA_KEY, RSI_KEY] : [RSI_KEY],
      warmup_by_timeframe: { "5m": 3 },
      data_requirements: [],
    },
    features: strategy
      ? [
          {
            feature_key: EMA_KEY,
            feature_ref: EMA_REF,
            name: "EMA 20",
            timeframe: "5m",
            indicator_type: "technical.ema",
            group: "Trend",
            origin: "derived",
            badge: "Derived from Strategy",
          },
          {
            feature_key: RSI_KEY,
            feature_ref: RSI_REF,
            name: "RSI 14",
            timeframe: "5m",
            indicator_type: "technical.rsi",
            group: "Momentum",
            origin: "manual",
            badge: "Manual",
          },
        ]
      : [
          {
            feature_key: RSI_KEY,
            feature_ref: RSI_REF,
            name: "RSI 14",
            timeframe: "5m",
            indicator_type: "technical.rsi",
            group: "Momentum",
            origin: "manual",
            badge: "Manual",
          },
        ],
    bars: [
      {
        bar_index: 0,
        timestamp: "2026-04-15T14:30:00Z",
        symbol: "SPY",
        timeframe: "5m",
        open: 450,
        high: 451,
        low: 449,
        close: 450.5,
        volume: 1000,
        is_warmup: true,
        feature_values: [
          {
            feature_key: strategy ? EMA_KEY : RSI_KEY,
            value: null,
            availability: "warmup",
            source_timeframe: "5m",
            source_timestamp: "2026-04-15T14:30:00Z",
          },
        ],
        signal_markers: [],
        condition_truth_tree: {},
        non_fire_reasons: strategy ? ["warmup_bar"] : [],
      },
      {
        bar_index: 1,
        timestamp: "2026-04-15T14:35:00Z",
        symbol: "SPY",
        timeframe: "5m",
        open: 451,
        high: 456,
        low: 450,
        close: 455.1234,
        volume: 2000,
        is_warmup: false,
        feature_values: strategy
          ? [
              {
                feature_key: EMA_KEY,
                value: 452.25,
                availability: "available",
                source_timeframe: "5m",
                source_timestamp: "2026-04-15T14:35:00Z",
              },
              {
                feature_key: RSI_KEY,
                value: 61.5,
                availability: "available",
                source_timeframe: "5m",
                source_timestamp: "2026-04-15T14:35:00Z",
              },
            ]
          : [
              {
                feature_key: RSI_KEY,
                value: 61.5,
                availability: "available",
                source_timeframe: "5m",
                source_timestamp: "2026-04-15T14:35:00Z",
              },
            ],
        signal_markers: strategy
          ? [
              {
                timestamp: "2026-04-15T14:35:00Z",
                symbol: "SPY",
                marker_type: "candidate_entry",
                side: "long",
                reason: "close_above_ema",
                signal_name: "Daily Breakout",
              },
            ]
          : [],
        condition_truth_tree: strategy
          ? {
              rules: [
                {
                  name: "close_above_ema",
                  condition: {
                    left_feature: "5m.close[0]",
                    operator: ">",
                    right_feature: "5m.ema:length=20[0]",
                    result: true,
                  },
                },
              ],
            }
          : {},
        non_fire_reasons: [],
      },
    ],
    metadata: {
      provider: "alpaca",
      adjustment: "split_dividend_adjusted",
      total_bars: 2,
      active_bars: 1,
      warmup_bars: 1,
      dataset_count: 1,
      warnings: strategy ? ["partial data from provider cache"] : [],
    },
    evidence: strategy
      ? {
          evidence_id: "55555555-5555-5555-5555-555555555555",
          strategy_id: STRATEGY_ID,
          strategy_version_id: VERSION_ID,
          symbol: "SPY",
          timeframe: "5m",
          start: "2026-04-01T00:00:00Z",
          end: "2026-04-15T23:59:59Z",
          feature_snapshot_count: 4,
          signal_marker_count: 1,
        }
      : null,
  };
}

describe("<ChartLab />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
    chartCalls.props.length = 0;
  });

  function mount(previewBody: unknown = previewResponse()) {
    restore = installFetchMock([
      { url: "/api/v1/strategies", body: STRATEGIES_LIST },
      { url: `/api/v1/strategies/${STRATEGY_ID}/versions`, body: VERSIONS_LIST },
      { url: "/api/v1/chart-lab/features", body: FEATURE_LIBRARY },
      {
        url: "/api/v1/chart-lab/preview",
        method: "POST",
        body: previewBody,
      },
    ]);
    return renderRoute(<ChartLab />);
  }

  it("runs without a strategy as Feature Explorer and posts only manual feature refs", async () => {
    mount(previewResponse({ strategy: false }));

    await waitFor(() => {
      expect(screen.getByText(/Feature Explorer/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Features Used by Strategy/i)).not.toBeInTheDocument();

    await userEvent.click(await screen.findByRole("button", { name: /Add RSI 14/i }));
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(screen.getByTestId("strategy-preview-chart")).toHaveTextContent("1 warm-up");
    });
    expect(screen.getByRole("heading", { name: /Manual Overlays/i })).toBeInTheDocument();
    expect(screen.getAllByText(/Manual/i).length).toBeGreaterThan(0);
    expect(screen.getByText("61.5000")).toBeInTheDocument();

    const previewCalls = (
      globalThis.fetch as unknown as { mock: { calls: unknown[][] } }
    ).mock.calls.filter(([url]) => String(url).includes("/api/v1/chart-lab/preview"));
    const [, init] = previewCalls[0] as [unknown, RequestInit];
    const parsed = JSON.parse(init.body as string);
    expect(parsed.strategy_version_id).toBeNull();
    expect(parsed.manual_feature_refs).toEqual([RSI_REF]);
    expect(parsed.symbol).toBe("SPY");
  });

  it("separates derived Strategy features from manual overlays", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /v1 - draft/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(screen.getByTestId("strategy-preview-chart")).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText("61.5000")).toBeInTheDocument();
    });
    expect(screen.getByText(/Features Used by Strategy/i)).toBeInTheDocument();
    expect(screen.getByText(/Derived from Strategy/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Manual Overlays/i })).toBeInTheDocument();
    expect(screen.getAllByText("EMA 20").length).toBeGreaterThan(0);
    expect(screen.getAllByText("RSI 14").length).toBeGreaterThan(0);
    expect(screen.getByText(/close_above_ema/i)).toBeInTheDocument();
    expect(screen.getByText(/Entry signal/i)).toBeInTheDocument();

    const previewCalls = (
      globalThis.fetch as unknown as { mock: { calls: unknown[][] } }
    ).mock.calls.filter(([url]) => String(url).includes("/api/v1/chart-lab/preview"));
    const [, init] = previewCalls[0] as [unknown, RequestInit];
    const parsed = JSON.parse(init.body as string);
    expect(parsed.strategy_version_id).toBe(VERSION_ID);
    expect(parsed.manual_feature_refs).toEqual(
      expect.arrayContaining([EMA_REF, RSI_REF]),
    );
    expect(parsed.manual_feature_refs).toHaveLength(2);
  });

  it("renders warm-up bars distinctly through the chart contract and timeline", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /v1 - draft/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(chartCalls.props.at(-1)?.bars.some((bar) => bar.isWarmup)).toBe(true);
    });
    expect(screen.getByTestId("strategy-preview-chart")).toHaveTextContent("1 warm-up");
    expect(screen.getAllByText(/warm-up/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/active/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("455.12").length).toBeGreaterThan(0);
  });

  it("renders the data context strip with human-readable metadata and visible warnings", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(screen.getByTestId("chart-lab-context-strip")).toHaveTextContent("ProviderAlpaca");
    });
    const strip = screen.getByTestId("chart-lab-context-strip");
    expect(strip).toHaveTextContent("AdjustmentSplit + dividend");
    expect(strip).toHaveTextContent("Total bars2");
    expect(strip).toHaveTextContent("Active bars1");
    expect(strip).toHaveTextContent("Warm-up bars1");
    expect(strip).toHaveTextContent("Datasets1");
    expect(screen.getByTestId("chart-lab-context-warnings")).toHaveTextContent(
      "partial data from provider cache",
    );
    expect(strip).not.toHaveTextContent("44444444-4444-4444-4444-444444444444");
  });

  it("switches between candle and close-line modes and exposes reset zoom", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(screen.getByTestId("chart-mock-mode")).toHaveTextContent("candles");
    });
    await userEvent.click(screen.getByRole("button", { name: /Line/i }));
    await waitFor(() => {
      expect(screen.getByTestId("chart-mock-mode")).toHaveTextContent("line");
    });
    await userEvent.click(screen.getByRole("button", { name: /Reset Zoom/i }));
    await waitFor(() => {
      expect(screen.getByTestId("chart-mock-reset")).toHaveTextContent("1");
    });
  });

  it("defaults signal labels off so the chart chrome does not imply raw marker text spam", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(screen.getByTestId("chart-mock-signal-label-flag")).toHaveTextContent("labels-off");
    });
    expect(screen.getByLabelText("Show signal labels")).not.toBeChecked();
    expect(screen.queryByText(/draft_entry_short/i)).not.toBeInTheDocument();
  });

  it("toggles Show signal labels and forwards the preference to the chart", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() =>
      expect(screen.getByLabelText("Show signal labels")).not.toBeChecked(),
    );
    await userEvent.click(screen.getByLabelText("Show signal labels"));
    await waitFor(() =>
      expect(screen.getByTestId("chart-mock-signal-label-flag")).toHaveTextContent("labels-on"),
    );
  });

  it("routes chart clicks to Bar Inspector selection", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(screen.getByTestId("simulate-chart-bar-click")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId("simulate-chart-bar-click"));

    await waitFor(() => {
      const panel = screen.getByText(/Signals \(verification\)/i).closest("section");
      expect(panel?.textContent ?? "").toMatch(/Entry signal/);
      expect(panel?.textContent ?? "").toMatch(/true/);
    });
  });

  it("renders Bar Inspector derived feature values separately from manual overlays", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(screen.getByTestId("bar-inspector-derived-features")).toHaveTextContent("EMA 20");
    });
    expect(screen.getByTestId("bar-inspector-manual-features")).toHaveTextContent("RSI 14");
  });

  it("requests warm-up density defaults that keep warm-up candles addressable in the chart", async () => {
    mount(previewResponse({ strategy: true }));

    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    fireEvent.click(screen.getByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(chartCalls.props.at(-1)?.density?.showWarmupBars).toBe(true);
    });
  });

  it("surfaces an error state when the backend rejects the load", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies", body: STRATEGIES_LIST },
      { url: "/api/v1/chart-lab/features", body: FEATURE_LIBRARY },
      {
        url: "/api/v1/chart-lab/preview",
        method: "POST",
        status: 422,
        body: { detail: "no bars available for SPY 5m in window" },
      },
    ]);
    renderRoute(<ChartLab />);

    fireEvent.click(await screen.findByRole("button", { name: /Load Data/i }));

    await waitFor(() => {
      expect(screen.getByText(/ChartLab load failed/i)).toBeInTheDocument();
    });
  });
});

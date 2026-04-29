import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

// jsdom cannot render lightweight-charts (no canvas / ResizeObserver
// edge cases). Replace the chart components with placeholders so the
// surrounding form / checklist / signal-table behavior stays under test.
vi.mock("@/components/charts/StrategyPreviewChart", () => ({
  StrategyPreviewChart: (props: { symbol: string }) => (
    <div data-testid="strategy-preview-chart">{props.symbol}</div>
  ),
}));
vi.mock("@/components/charts/PriceChart", () => ({
  PriceChart: (props: { symbol: string }) => (
    <div data-testid="price-chart">{props.symbol}</div>
  ),
}));

import { ChartLab } from "./ChartLab";

// jsdom does not implement WebSocket. Chart Lab's stream pane opens one
// when the operator hits Stream. The stub never delivers messages so the
// stream pane renders its empty state cleanly during tests.
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
      feature_refs: ["5m.close[0]", "1d.high[0]"],
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

const PREVIEW_RESPONSE = {
  session: {
    id: "33333333-3333-3333-3333-333333333333",
    mode: "chart_lab_batch",
    symbol: "SPY",
    timeframe: "5m",
    start: "2026-04-01T00:00:00Z",
    end: "2026-04-15T23:59:59Z",
    strategy_version_id: VERSION_ID,
  },
  feature_plan: {
    id: "44444444-4444-4444-4444-444444444444",
    strategy_version_id: VERSION_ID,
    consumer: "chart_lab",
    symbols: ["SPY"],
    timeframes: ["5m", "1d"],
    feature_specs: [
      {
        kind: "close",
        namespace: "price",
        timeframe: "5m",
        source: "bar",
        params: {},
        lookback: 0,
        shift: 0,
        scope: "symbol",
        version: "v1",
      },
      {
        kind: "high",
        namespace: "price",
        timeframe: "1d",
        source: "bar",
        params: {},
        lookback: 0,
        shift: 0,
        scope: "symbol",
        version: "v1",
      },
    ],
    feature_keys: [
      "v1|symbol|5m|price.close|source=bar|params={}|lookback=0|shift=0",
      "v1|symbol|1d|price.high|source=bar|params={}|lookback=0|shift=0",
    ],
  },
  bars: [
    {
      timestamp: "2026-04-15T15:00:00Z",
      symbol: "SPY",
      timeframe: "5m",
      feature_values: [
        {
          feature_key: "v1|symbol|5m|price.close|source=bar|params={}|lookback=0|shift=0",
          value: 101,
          availability: "available",
          source_timeframe: "5m",
          source_timestamp: "2026-04-15T15:00:00Z",
        },
        {
          feature_key: "v1|symbol|1d|price.high|source=bar|params={}|lookback=0|shift=0",
          value: 100,
          availability: "available",
          source_timeframe: "1d",
          source_timestamp: "2026-04-14T21:00:00Z",
        },
      ],
      signal_markers: [
        {
          timestamp: "2026-04-15T15:00:00Z",
          symbol: "SPY",
          marker_type: "candidate_entry",
          side: "long",
          reason: "close_above_prior_high",
          signal_name: "Daily Breakout",
        },
      ],
      condition_truth_tree: { intent_count: 1 },
      non_fire_reasons: [],
    },
  ],
  evidence: {
    evidence_id: "55555555-5555-5555-5555-555555555555",
    strategy_id: STRATEGY_ID,
    strategy_version_id: VERSION_ID,
    symbol: "SPY",
    timeframe: "5m",
    start: "2026-04-01T00:00:00Z",
    end: "2026-04-15T23:59:59Z",
    feature_snapshot_count: 2,
    signal_marker_count: 1,
  },
};

describe("<ChartLab /> stream pane", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the streaming-disabled banner when health says streaming is off", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/chart-lab/health",
        body: {
          streaming_enabled: false,
          test_stream: false,
          default_symbol: "SPY",
          data_feed: "sip",
          websocket_path: "/api/v1/chart-lab/stream",
          routing_note: "",
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/strategies", body: STRATEGIES_LIST },
    ]);
    renderRoute(<ChartLab />);
    await waitFor(() => {
      expect(screen.getByText(/Streaming disabled/i)).toBeInTheDocument();
    });
  });

  it("renders the stream card when health is happy", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/chart-lab/health",
        body: {
          streaming_enabled: true,
          test_stream: false,
          default_symbol: "SPY",
          data_feed: "sip",
          websocket_path: "/api/v1/chart-lab/stream",
          routing_note: "",
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/strategies", body: STRATEGIES_LIST },
    ]);
    renderRoute(<ChartLab />);
    await waitFor(() => {
      expect(screen.getAllByText(/Stream/i).length).toBeGreaterThan(0);
    });
  });

  it("surfaces a degraded read state when health fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/chart-lab/health", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: "/api/v1/strategies", body: STRATEGIES_LIST },
    ]);
    renderRoute(<ChartLab />);
    await waitFor(() => {
      expect(screen.getByText(/Chart Lab not configured/i)).toBeInTheDocument();
    });
  });
});

describe("<ChartLab /> strategy preview pane", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  function mountWithPreview(overrides: { previewBody?: unknown; previewStatus?: number } = {}) {
    restore = installFetchMock([
      {
        url: "/api/v1/chart-lab/health",
        body: {
          streaming_enabled: true,
          test_stream: false,
          default_symbol: "SPY",
          data_feed: "sip",
          websocket_path: "/api/v1/chart-lab/stream",
          routing_note: "",
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
      { url: `/api/v1/strategies/${STRATEGY_ID}/versions`, body: VERSIONS_LIST },
      { url: "/api/v1/strategies", body: STRATEGIES_LIST },
      {
        url: "/api/v1/chart-lab/preview",
        method: "POST",
        body: overrides.previewBody ?? PREVIEW_RESPONSE,
        status: overrides.previewStatus ?? 200,
      },
    ]);
    return renderRoute(<ChartLab />);
  }

  async function switchToPreviewTab(): Promise<void> {
    const user = userEvent.setup();
    await user.click(screen.getByRole("tab", { name: /Strategy preview/i }));
  }

  it("loads strategies after switching to the preview tab", async () => {
    mountWithPreview();
    await switchToPreviewTab();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
  });

  it("posts a preview request and renders the chart-first surface", async () => {
    mountWithPreview();
    await switchToPreviewTab();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });

    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /v1 - draft/i }),
      ).toBeInTheDocument();
    });

    const runButton = screen.getByRole("button", { name: /Run preview/i });
    fireEvent.click(runButton);

    await waitFor(() => {
      expect(screen.getByText(/1 signals/i)).toBeInTheDocument();
    });
    // Feature checklist exposes both feature_keys (default-selected).
    await waitFor(() => {
      expect(
        screen.getByLabelText(/Toggle v1\|symbol\|5m\|price\.close/i),
      ).toBeChecked();
      expect(
        screen.getByLabelText(/Toggle v1\|symbol\|1d\|price\.high/i),
      ).toBeChecked();
    });
    // Signal-markers table shows the candidate_entry row.
    expect(screen.getByText(/candidate_entry/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Daily Breakout/).length).toBeGreaterThan(0);

    const previewCalls = (
      globalThis.fetch as unknown as { mock: { calls: unknown[][] } }
    ).mock.calls.filter(([url]) => String(url).includes("/api/v1/chart-lab/preview"));
    expect(previewCalls.length).toBe(1);
    const [, init] = previewCalls[0] as [unknown, RequestInit];
    expect(init.method).toBe("POST");
    expect(typeof init.body).toBe("string");
    const parsed = JSON.parse(init.body as string);
    expect(parsed.strategy_version_id).toBe(VERSION_ID);
    expect(parsed.symbol).toBe("SPY");
    expect(parsed.timeframe).toBe("5m");
    expect(parsed.source).toBe("alpaca");
  });

  it("toggling a feature_key off removes it from the selected count", async () => {
    mountWithPreview();
    await switchToPreviewTab();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /v1 - draft/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Run preview/i }));

    const closeCheckbox = await screen.findByLabelText(
      /Toggle v1\|symbol\|5m\|price\.close/i,
    );
    expect(screen.getByText(/2\/2 on chart/)).toBeInTheDocument();
    fireEvent.click(closeCheckbox);
    expect(screen.getByText(/1\/2 on chart/)).toBeInTheDocument();
  });

  it("surfaces a banner when the preview request fails", async () => {
    mountWithPreview({
      previewBody: { detail: "no bars available for SPY 5m in window" },
      previewStatus: 422,
    });
    await switchToPreviewTab();
    await waitFor(() => {
      expect(screen.getByRole("option", { name: /Daily Breakout/i })).toBeInTheDocument();
    });
    await userEvent.selectOptions(screen.getByLabelText("Strategy"), STRATEGY_ID);
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /v1 - draft/i }),
      ).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: /Run preview/i }));

    await waitFor(() => {
      expect(screen.getAllByText(/Preview failed/i).length).toBeGreaterThan(0);
    });
  });
});

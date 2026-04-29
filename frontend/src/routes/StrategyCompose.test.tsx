import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { StrategyCompose } from "./StrategyCompose";

beforeAll(() => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).confirm = vi.fn(() => true);
});

beforeEach(() => {
  window.localStorage.clear();
});

const FEATURE_CATALOG = [
  {
    kind: "ema",
    display_name: "EMA",
    namespace: "technical",
    scope: "symbol",
    source: "close",
    allowed_params: ["length"],
    default_params: { length: 20 },
    supported_timeframes: ["1m", "5m", "15m", "1h"],
    supported_consumers: ["backtest"],
    supported_modes: ["batch"],
    example_refs: [],
  },
  {
    kind: "close",
    display_name: "Close",
    namespace: "price",
    scope: "symbol",
    source: "close",
    allowed_params: [],
    default_params: {},
    supported_timeframes: ["1m", "5m", "1d"],
    supported_consumers: ["backtest"],
    supported_modes: ["batch"],
    example_refs: [],
  },
];

const STRATEGY_DRAFT = {
  draft_id: "00000000-0000-0000-0000-0000000000aa",
  prompt: "Long EMA crossover",
  strategy: {
    id: "00000000-0000-0000-0000-0000000000bb",
    strategy_id: "00000000-0000-0000-0000-0000000000cc",
    version: 1,
    name: "Composer draft",
    description: "Long EMA crossover",
    feature_refs: ["5m.ema:length=20[0]", "5m.close[0]"],
    entry_rules: [
      {
        name: "draft_entry_long",
        side: "long",
        intent_type: "entry",
        condition: {
          kind: "condition",
          left_feature: "5m.ema:length=20[0]",
          operator: "gt",
          right_feature: "5m.close[0]",
        },
      },
    ],
    exit_rules: [
      {
        name: "draft_logical_exit_long",
        side: "long",
        intent_type: "exit",
        logical_exit_rule: { kind: "time_in_position_seconds", seconds: 1800 },
      },
    ],
    tags: ["ai_composer", "draft"],
    created_at: "2026-04-28T01:50:00Z",
  },
  strategy_controls: {
    id: "00000000-0000-0000-0000-0000000000dd",
    strategy_controls_id: "00000000-0000-0000-0000-0000000000ee",
    version: 1,
    name: "Draft Controls (wizard)",
    timeframe: "5m",
    trading_horizon: "intraday",
    allowed_directions: "long",
    higher_timeframe_confirmation_required: false,
    session_preference: "regular_only",
    earnings_news_blackout_enabled: false,
  },
  execution_style: {
    id: "00000000-0000-0000-0000-0000000000ee",
    execution_style_id: "00000000-0000-0000-0000-0000000000ff",
    version: 1,
    name: "Market In / Market Out",
    entry_order_type: "market",
    feature_refs: [],
    preset: { kind: "market_entry_market_exit" },
    created_at: "2026-04-28T01:50:00Z",
  },
  backtest_plan: {
    symbols: ["SPY"],
    timeframe: "5m",
    initial_capital: 100000,
    cost_model: { commission_per_trade: 0, slippage_bps: 1 },
  },
  launch_plans: {
    chart_lab: { surface: "chart_lab", method: "POST", route: "/api/v1/research/chart-lab/preview", request: {}, ready: false, missing_fields: [] },
    backtest: { surface: "backtest", method: "POST", route: "/api/v1/research/backtests/run", request: {}, ready: false, missing_fields: [] },
    walk_forward: { surface: "walk_forward", method: "POST", route: "/api/v1/research/walk-forward/run", request: {}, ready: false, missing_fields: [] },
  },
  signal_plan_shape: { intents: [], placeholder_copy: "[symbol] · open · market · qty=full" },
  validation: { valid: true, errors: [], warnings: [], normalized_feature_refs: ["5m.ema:length=20[0]", "5m.close[0]"] },
};

const SAVE_RESPONSE = {
  strategy_version: {
    strategy_version_id: "00000000-0000-0000-0000-000000000111",
    strategy_id: "00000000-0000-0000-0000-000000000222",
    version: 1,
    status: "draft",
    payload: STRATEGY_DRAFT.strategy,
    created_at: "2026-04-28T01:55:00Z",
  },
  draft: STRATEGY_DRAFT,
  component_version_snapshots: {
    execution_style: STRATEGY_DRAFT.execution_style,
    backtest_plan: STRATEGY_DRAFT.backtest_plan,
    launch_plans: STRATEGY_DRAFT.launch_plans,
  },
  deployment_created: false,
  broker_action_created: false,
  live_readiness_claimed: false,
};

interface MountResult {
  capturedComposerBody: () => unknown;
  capturedSaveBody: () => unknown;
}

function mount(): MountResult {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  let composerBody: unknown = null;
  let saveBody: unknown = null;

  globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url;

    if (url.includes("/strategies/composer/preview")) {
      composerBody = init?.body ? JSON.parse(init.body as string) : null;
      return new Response(JSON.stringify(STRATEGY_DRAFT), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes("/strategies/composer/drafts")) {
      saveBody = init?.body ? JSON.parse(init.body as string) : null;
      return new Response(JSON.stringify(SAVE_RESPONSE), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    if (url.includes("/strategies/builder/features/validate")) {
      return new Response(
        JSON.stringify({
          valid: true,
          errors: [],
          warnings: [],
          items: [],
          normalized_feature_refs: [],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (url.includes("/strategies/builder/features")) {
      return new Response(JSON.stringify(FEATURE_CATALOG), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ detail: `unmocked ${url}` }), { status: 599 });
  }) as unknown as typeof globalThis.fetch;

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/strategies/compose"]}>
        <Routes>
          <Route path="/strategies/compose" element={<StrategyCompose />} />
          <Route
            path="/strategies/:strategyId"
            element={<div data-testid="strategy-detail">Strategy detail</div>}
          />
          <Route path="/strategies" element={<div data-testid="strategies-list">Strategies</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return {
    capturedComposerBody: () => composerBody,
    capturedSaveBody: () => saveBody,
  };
}

describe("<StrategyCompose /> — wizard + editor flow", () => {
  afterEach(() => {
    document.body.innerHTML = "";
    window.localStorage.clear();
  });

  it("mounts on Page 1 with the wizard textarea and starter panel; no FeatureIndex on Page 1", () => {
    mount();
    expect(screen.getByTestId("wizard-prompt")).toBeInTheDocument();
    expect(screen.getByTestId("wizard-intent")).toBeInTheDocument();
    expect(screen.getByTestId("starter-template-panel")).toBeInTheDocument();
    expect(screen.getByTestId("template-card-vwap-reclaim")).toBeInTheDocument();
    expect(screen.getByTestId("template-card-opening-range-breakout")).toBeInTheDocument();
    expect(screen.queryByTestId("feature-index-drawer")).not.toBeInTheDocument();
  });

  it("AI never fires while typing — Generate click sends wizard_intent in the body", async () => {
    const user = userEvent.setup();
    const { capturedComposerBody } = mount();

    await user.type(
      screen.getByTestId("wizard-prompt"),
      "Long when 5m close above EMA(20) for momentum",
    );
    expect(capturedComposerBody()).toBeNull();

    await user.click(screen.getByTestId("generate-with-ai-button"));

    await waitFor(() => expect(capturedComposerBody()).not.toBeNull());
    const body = capturedComposerBody() as Record<string, unknown>;

    expect(body.wizard_intent).toBeDefined();
    expect((body.wizard_intent as Record<string, unknown>).direction).toBe("long");
    expect((body.wizard_intent as Record<string, unknown>).horizon).toBe("intraday");
    expect((body.wizard_intent as Record<string, unknown>).base_timeframe).toBe("5m");
    expect(body).not.toHaveProperty("symbols");
    expect(body).not.toHaveProperty("universe");
    expect(body).not.toHaveProperty("notes");
  });

  it("after Generate succeeds, advances to Page 2 prefilled editor with all 14 sections", async () => {
    const user = userEvent.setup();
    mount();

    await user.type(
      screen.getByTestId("wizard-prompt"),
      "Long when 5m close above EMA(20) for momentum",
    );
    await user.click(screen.getByTestId("generate-with-ai-button"));

    await waitFor(() => {
      expect(screen.getByTestId("editor-page")).toBeInTheDocument();
    });
    expect(screen.getByTestId("section-summary")).toBeInTheDocument();
    expect(screen.getByTestId("section-required-features")).toBeInTheDocument();
    expect(screen.getByTestId("section-entry-long")).toBeInTheDocument();
    expect(screen.getByTestId("section-entry-plan")).toBeInTheDocument();
    expect(screen.getByTestId("section-stop-plan")).toBeInTheDocument();
    expect(screen.getByTestId("section-target-plan")).toBeInTheDocument();
    expect(screen.getByTestId("section-runner-plan")).toBeInTheDocument();
    expect(screen.getByTestId("section-logical-exit")).toBeInTheDocument();
    expect(screen.getByTestId("section-time-based-exit")).toBeInTheDocument();
    expect(screen.getByTestId("section-strategy-controls")).toBeInTheDocument();
    expect(screen.getByTestId("section-execution-preset")).toBeInTheDocument();
    expect(screen.getByTestId("section-coherence")).toBeInTheDocument();
    expect(screen.getByTestId("section-research-actions")).toBeInTheDocument();
    expect(screen.getByTestId("editor-toc")).toBeInTheDocument();
    expect(screen.getByTestId("editor-save-bar")).toBeInTheDocument();

    // Summary section is prefilled from the AI draft.
    const nameInput = screen.getByTestId("summary-name") as HTMLInputElement;
    expect(nameInput.value).toBe("Composer draft");
  });

  it("Save posts the draft envelope and navigates to /strategies/:id with the toast state", async () => {
    const user = userEvent.setup();
    const { capturedSaveBody } = mount();

    await user.type(
      screen.getByTestId("wizard-prompt"),
      "Long when 5m close above EMA(20) for momentum",
    );
    await user.click(screen.getByTestId("generate-with-ai-button"));
    await waitFor(() => expect(screen.getByTestId("editor-page")).toBeInTheDocument());

    await user.click(screen.getByTestId("editor-save"));
    await waitFor(() => expect(screen.getByTestId("strategy-detail")).toBeInTheDocument());

    const body = capturedSaveBody() as { draft?: Record<string, unknown> } | null;
    expect(body).not.toBeNull();
    expect(body?.draft).toBeDefined();
    // Save sends the WHOLE draft envelope (S6-D8: only-saver doctrine).
    expect(body?.draft).toMatchObject({
      strategy: { name: "Composer draft" },
      strategy_controls: { trading_horizon: "intraday" },
    });
  });

  it("editing the Summary section's name flows into the saved draft", async () => {
    const user = userEvent.setup();
    const { capturedSaveBody } = mount();

    await user.type(
      screen.getByTestId("wizard-prompt"),
      "Long when 5m close above EMA(20) for momentum",
    );
    await user.click(screen.getByTestId("generate-with-ai-button"));
    await waitFor(() => expect(screen.getByTestId("editor-page")).toBeInTheDocument());

    const name = screen.getByTestId("summary-name") as HTMLInputElement;
    await user.clear(name);
    await user.type(name, "Renamed by operator");

    await user.click(screen.getByTestId("editor-save"));
    await waitFor(() => {
      const body = capturedSaveBody() as { draft?: { strategy?: { name?: string } } } | null;
      expect(body?.draft?.strategy?.name).toBe("Renamed by operator");
    });
  });

  it("Skip wizard goes straight to the no-draft landing with no draft loaded", async () => {
    const user = userEvent.setup();
    mount();

    await user.click(screen.getByTestId("skip-wizard-button"));
    expect(screen.getByTestId("page2-stub")).toBeInTheDocument();
    expect(screen.getByTestId("page2-draft-loaded").textContent).toContain("no");
    expect(screen.getByText(/Skipped wizard/)).toBeInTheDocument();
  });

  it("applying a template seeds prompt + wizard intent", async () => {
    const user = userEvent.setup();
    mount();

    const card = screen.getByTestId("template-card-connors-rsi-2");
    await user.click(within(card).getByRole("button", { expanded: false }));
    await user.click(screen.getByTestId("apply-template-connors-rsi-2"));

    expect((screen.getByTestId("wizard-prompt") as HTMLTextAreaElement).value).toMatch(
      /Connors|RSI|down_streak/,
    );
    const dailyTimeframe = screen.getByTestId("base-timeframe-select") as HTMLSelectElement;
    expect(dailyTimeframe.value).toBe("1d");
  });

  it("wizard state persists to localStorage and restores on remount", async () => {
    const user = userEvent.setup();
    mount();
    await user.type(screen.getByTestId("wizard-prompt"), "Persisted prompt content");
    expect(window.localStorage.getItem("compose:wizard:draft")).toMatch(/Persisted prompt content/);
    document.body.innerHTML = "";

    mount();
    expect((screen.getByTestId("wizard-prompt") as HTMLTextAreaElement).value).toBe(
      "Persisted prompt content",
    );
  });

  it("deferred SESSION-template card has Generate disabled with the explicit reason", async () => {
    const user = userEvent.setup();
    mount();

    const card = screen.getByTestId("template-card-opening-range-breakout");
    expect(card).toHaveAttribute("data-blocked", "true");
    await user.click(within(card).getByRole("button", { expanded: false }));

    const applyBtn = screen.getByTestId("apply-template-opening-range-breakout");
    expect(applyBtn).toBeDisabled();
    expect(within(card).getByText(/Requires SESSION execution.*Slice 6a-ii/)).toBeInTheDocument();
  });

  it("Exit clears persisted state and navigates back", async () => {
    const user = userEvent.setup();
    mount();
    await user.type(screen.getByTestId("wizard-prompt"), "Some prompt content");
    expect(window.localStorage.getItem("compose:wizard:draft")).not.toBeNull();

    await user.click(screen.getByRole("button", { name: /Exit/i }));
    expect(window.localStorage.getItem("compose:wizard:draft")).toBeNull();
  });
});

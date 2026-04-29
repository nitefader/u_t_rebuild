import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { StrategyDraft } from "@/api/schemas/strategyComposer";
import { EditorPage } from "./EditorPage";

/**
 * Slice C-3 — clicking a row in the validation popover flips the tab
 * via ?tab= and closes the popover. We trigger the
 * `logical_exit_fires_immediately_after_entry` coherence error
 * (sectionId: section-logical-exit, which lives on the
 * Stop · Target · Execution tab) and assert the tab change.
 */

const DRAFT_TRIGGERING_LOGICAL_EXIT_ERROR = {
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
    // Feature-condition exit referencing the same feature as entry,
    // with NO minimum hold → triggers the error rule.
    exit_rules: [
      {
        name: "draft_logical_exit_long",
        side: "long",
        intent_type: "exit",
        logical_exit_rule: {
          kind: "feature_condition",
          feature_condition: {
            kind: "condition",
            left_feature: "5m.ema:length=20[0]",
            operator: "lt",
            right_feature: "5m.close[0]",
          },
        },
      },
    ],
    tags: ["ai_composer", "draft"],
    created_at: "2026-04-28T01:50:00Z",
  },
  strategy_controls: {
    id: "00000000-0000-0000-0000-0000000000dd",
    strategy_controls_id: "00000000-0000-0000-0000-0000000000ee",
    version: 1,
    name: "Draft Controls",
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
    chart_lab: {
      surface: "chart_lab",
      method: "POST",
      route: "/api/v1/research/chart-lab/preview",
      request: {},
      ready: false,
      missing_fields: [],
    },
    backtest: {
      surface: "backtest",
      method: "POST",
      route: "/api/v1/research/backtests/run",
      request: {},
      ready: false,
      missing_fields: [],
    },
    walk_forward: {
      surface: "walk_forward",
      method: "POST",
      route: "/api/v1/research/walk-forward/run",
      request: {},
      ready: false,
      missing_fields: [],
    },
  },
  signal_plan_shape: { intents: [], placeholder_copy: "[symbol] · open · market · qty=full" },
  validation: {
    valid: true,
    errors: [],
    warnings: [],
    normalized_feature_refs: ["5m.ema:length=20[0]", "5m.close[0]"],
  },
} as unknown as StrategyDraft;

function mount(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });

  globalThis.fetch = vi.fn(async () => {
    return new Response(JSON.stringify([]), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof globalThis.fetch;

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/strategies/compose"]}>
        <EditorPage
          draft={DRAFT_TRIGGERING_LOGICAL_EXIT_ERROR}
          prompt={null}
          intent={null}
          onSaved={() => {}}
          onRegenerate={() => {}}
          onDiscard={() => {}}
          regenerating={false}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EditorPage — Slice C-3 jump-from-popover", () => {
  it("clicking a coherence error in the validation popover switches to the section's tab", async () => {
    const user = userEvent.setup();
    mount();

    // Wait until the editor mounts and the error has been computed.
    await waitFor(() => {
      expect(screen.getByTestId("editor-validation-trigger")).toBeInTheDocument();
    });

    // Default tab is Core; section-logical-exit lives on Stop · Target · Execution.
    expect(screen.getByTestId("page2-tab-content-core")).toHaveAttribute(
      "data-state",
      "active",
    );

    // Open the validation popover.
    await user.click(screen.getByTestId("editor-validation-trigger"));
    const jumpButton = await screen.findByTestId(
      "coherence-warning-jump-logical_exit_fires_immediately_after_entry",
    );

    await user.click(jumpButton);

    // Tab flipped to Stop · Target · Execution.
    await waitFor(() => {
      expect(screen.getByTestId("page2-tab-content-stop-target-exec")).toHaveAttribute(
        "data-state",
        "active",
      );
    });
    expect(screen.getByTestId("page2-tab-content-core")).toHaveAttribute(
      "data-state",
      "inactive",
    );
  });
});

import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { StrategyDraft } from "@/api/schemas/strategyComposer";
import { EditorPage } from "./EditorPage";

/**
 * Slice F — Validation badge severity tone.
 *
 * The save bar's "Validation" button shows a per-severity colored badge
 * so the operator can tell at a glance whether the popover holds blocking
 * errors, advisory warnings, or purely informational notes.
 *
 *   error tone (red)    → at least one error
 *   warn tone  (amber)  → at least one warn, no errors
 *   info tone  (muted)  → at least one info, no warns/errors
 *   no badge            → none of the above
 */

function baseDraft(overrides: Partial<StrategyDraft>): StrategyDraft {
  const draft: StrategyDraft = {
    draft_id: "00000000-0000-0000-0000-0000000000aa",
    prompt: "",
    strategy: {
      id: "00000000-0000-0000-0000-0000000000bb",
      strategy_id: "00000000-0000-0000-0000-0000000000cc",
      version: 1,
      name: "Composer draft",
      description: "",
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
      name: "Draft Controls",
      timeframe: "5m",
      trading_horizon: "swing",
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
  return { ...draft, ...overrides };
}

function mount(draft: StrategyDraft): void {
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
          draft={draft}
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

describe("Slice F — validation badge severity tone", () => {
  it("renders no badge when there are no warnings, errors, or infos", async () => {
    mount(baseDraft({}));
    await waitFor(() => {
      expect(screen.getByTestId("editor-validation-trigger")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("editor-validation-badge")).toBeNull();
  });

  it("uses the danger tone when there is at least one error", async () => {
    // Backend error → error tone.
    mount(
      baseDraft({
        validation: {
          valid: false,
          errors: ["Strategy is missing a name."],
          warnings: [],
          normalized_feature_refs: ["5m.ema:length=20[0]", "5m.close[0]"],
        },
      } as Partial<StrategyDraft>),
    );
    await waitFor(() => {
      expect(screen.getByTestId("editor-validation-badge")).toBeInTheDocument();
    });
    const badge = screen.getByTestId("editor-validation-badge");
    expect(badge).toHaveAttribute("data-tone", "danger");
    expect(badge).toHaveAttribute("data-error-count", "1");
    expect(badge).toHaveAttribute("data-warn-count", "0");
    expect(badge).toHaveAttribute("data-info-count", "0");
  });

  it("uses the warn tone when there are warnings but no errors", async () => {
    mount(
      baseDraft({
        validation: {
          valid: true,
          errors: [],
          warnings: ["Backend advisory: thin liquidity in pre-market."],
          normalized_feature_refs: ["5m.ema:length=20[0]", "5m.close[0]"],
        },
      } as Partial<StrategyDraft>),
    );
    await waitFor(() => {
      expect(screen.getByTestId("editor-validation-badge")).toBeInTheDocument();
    });
    const badge = screen.getByTestId("editor-validation-badge");
    expect(badge).toHaveAttribute("data-tone", "warn");
    expect(badge).toHaveAttribute("data-warn-count", "1");
    expect(badge).toHaveAttribute("data-error-count", "0");
  });

  it("uses the info tone when there are only informational notes", async () => {
    // Trigger the §15 info rule: multi_target_scale_out, slice sum < 1, stop_pct present.
    mount(
      baseDraft({
        execution_style: {
          id: "00000000-0000-0000-0000-0000000000ee",
          execution_style_id: "00000000-0000-0000-0000-0000000000ff",
          version: 1,
          name: "Multi-target scale-out",
          entry_order_type: "market",
          feature_refs: [],
          preset: {
            kind: "multi_target_scale_out",
            overrides: {
              targets: [
                { target_pct: 1.0, slice_pct: 0.25 },
                { target_pct: 2.0, slice_pct: 0.25 },
              ],
              stop_pct: 1.0,
            },
          },
          created_at: "2026-04-28T01:50:00Z",
        },
      } as Partial<StrategyDraft>),
    );
    await waitFor(() => {
      expect(screen.getByTestId("editor-validation-badge")).toBeInTheDocument();
    });
    const badge = screen.getByTestId("editor-validation-badge");
    expect(badge).toHaveAttribute("data-tone", "info");
    expect(badge).toHaveAttribute("data-info-count", "1");
    expect(badge).toHaveAttribute("data-error-count", "0");
    expect(badge).toHaveAttribute("data-warn-count", "0");
  });
});

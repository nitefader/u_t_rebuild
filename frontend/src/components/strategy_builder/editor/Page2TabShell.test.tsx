import { useState } from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { StrategyDraft } from "@/api/schemas/strategyComposer";
import type { CoherenceWarning, SectionId } from "./coherenceValidator";
import {
  computeBlueprintChips,
  Page2TabShell,
  presetCardVisibility,
  SECTION_TO_TAB,
} from "./Page2TabShell";
import type { ExecutionStylePresetValue } from "../ExecutionStylePresetRow";
import { editorStateFromDraft, type EditorState } from "./editorState";

const STRATEGY_DRAFT: StrategyDraft = {
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

interface HarnessProps {
  warnings?: CoherenceWarning[];
  initialEntries?: string[];
  initialState?: EditorState;
}

function Harness(props: HarnessProps): JSX.Element {
  const { warnings = [], initialEntries = ["/strategies/compose"], initialState } = props;
  const [state, setState] = useState<EditorState>(
    () => initialState ?? editorStateFromDraft(STRATEGY_DRAFT),
  );
  const warningsFor = (sectionId: SectionId) =>
    warnings.filter((w) => w.sectionId === sectionId);

  return (
    <MemoryRouter initialEntries={initialEntries}>
      <Page2TabShell
        state={state}
        setState={setState}
        catalog={[]}
        invalidFeatureRefs={new Set()}
        warnings={warnings}
        warningsFor={warningsFor}
        showShortSection={false}
      />
    </MemoryRouter>
  );
}

describe("<Page2TabShell />", () => {
  it("defaults to the Core tab and shows Summary content", () => {
    render(<Harness />);
    const coreContent = screen.getByTestId("page2-tab-content-core");
    expect(coreContent).toHaveAttribute("data-state", "active");
    expect(screen.getByTestId("section-summary")).toBeInTheDocument();
  });

  it("switching to Signals reveals EntryRules content while Core is inactive", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByTestId("page2-tab-trigger-signals"));

    const signalsContent = screen.getByTestId("page2-tab-content-signals");
    expect(signalsContent).toHaveAttribute("data-state", "active");
    const coreContent = screen.getByTestId("page2-tab-content-core");
    expect(coreContent).toHaveAttribute("data-state", "inactive");
    // EntryRules section is mounted under Signals.
    expect(screen.getByTestId("section-entry-long")).toBeInTheDocument();
  });

  it("forceMount keeps edits in non-active tabs alive across switches", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    const nameField = screen.getByTestId("summary-name") as HTMLInputElement;
    await user.clear(nameField);
    await user.type(nameField, "Edited in Core");

    await user.click(screen.getByTestId("page2-tab-trigger-controls"));
    expect(screen.getByTestId("page2-tab-content-controls")).toHaveAttribute(
      "data-state",
      "active",
    );

    await user.click(screen.getByTestId("page2-tab-trigger-core"));
    const nameAfter = screen.getByTestId("summary-name") as HTMLInputElement;
    expect(nameAfter.value).toBe("Edited in Core");
  });

  it("?tab=controls deep-links straight to the Controls tab", () => {
    render(<Harness initialEntries={["/strategies/compose?tab=controls"]} />);
    expect(screen.getByTestId("page2-tab-content-controls")).toHaveAttribute(
      "data-state",
      "active",
    );
    expect(screen.getByTestId("page2-tab-content-core")).toHaveAttribute(
      "data-state",
      "inactive",
    );
  });

  it("renders a red dot with count on the tab whose section has an error", () => {
    const warnings: CoherenceWarning[] = [
      {
        id: "stop-error",
        severity: "error",
        sectionId: "section-stop-plan",
        message: "Stop plan must have a stop distance.",
        dismissed: false,
      },
    ];
    render(<Harness warnings={warnings} />);
    const dot = screen.getByTestId("page2-tab-error-dot-stop-target-exec");
    expect(dot).toHaveTextContent("1");
  });

  it("blueprint chip 'Stop' is filled when bracket_stop_target preset has a stop_pct", () => {
    const baseState = editorStateFromDraft(STRATEGY_DRAFT);
    const stateWithBracket: EditorState = {
      ...baseState,
      preset: {
        kind: "bracket_stop_target",
        overrides: { stop_pct: 1.0, target_pct: 2.0 },
      },
    };
    render(<Harness initialState={stateWithBracket} />);
    const chip = screen.getByTestId("blueprint-chip-stop");
    expect(chip).toHaveAttribute("data-filled", "true");
  });

  it("SECTION_TO_TAB maps every coherence section id to a known tab", () => {
    const sectionIds: SectionId[] = [
      "section-required-features",
      "section-entry-long",
      "section-entry-short",
      "section-stop-plan",
      "section-target-plan",
      "section-runner-plan",
      "section-logical-exit",
      "section-time-based-exit",
      "section-strategy-controls",
      "section-execution-preset",
    ];
    for (const id of sectionIds) {
      expect(SECTION_TO_TAB[id]).toBeDefined();
    }
  });

  it("presetCardVisibility hides stop/target/runner for market_entry_market_exit", () => {
    expect(presetCardVisibility("market_entry_market_exit")).toEqual({
      stop: false,
      target: false,
      runner: false,
    });
  });

  it("presetCardVisibility hides stop/target/runner for stop_entry_market_exit", () => {
    expect(presetCardVisibility("stop_entry_market_exit")).toEqual({
      stop: false,
      target: false,
      runner: false,
    });
  });

  it("presetCardVisibility shows stop+target only for bracket_stop_target", () => {
    expect(presetCardVisibility("bracket_stop_target")).toEqual({
      stop: true,
      target: true,
      runner: false,
    });
  });

  it("presetCardVisibility shows all three for bracket_runner", () => {
    expect(presetCardVisibility("bracket_runner")).toEqual({
      stop: true,
      target: true,
      runner: true,
    });
  });

  it("presetCardVisibility shows all three for multi_target_scale_out", () => {
    expect(presetCardVisibility("multi_target_scale_out")).toEqual({
      stop: true,
      target: true,
      runner: true,
    });
  });

  it("Stop·Target·Execution tab hides Stop/Target/Runner cards on market_entry_market_exit", () => {
    render(<Harness initialEntries={["/strategies/compose?tab=stop-target-exec"]} />);
    expect(screen.getByTestId("section-execution-preset")).toBeInTheDocument();
    expect(screen.queryByTestId("section-stop-plan")).toBeNull();
    expect(screen.queryByTestId("section-target-plan")).toBeNull();
    expect(screen.queryByTestId("section-runner-plan")).toBeNull();
  });

  it("Stop·Target·Execution tab hides Runner only on bracket_stop_target", () => {
    const baseState = editorStateFromDraft(STRATEGY_DRAFT);
    const bracketPreset: ExecutionStylePresetValue = {
      kind: "bracket_stop_target",
      overrides: { stop_pct: 1.0, target_pct: 2.0 },
    };
    render(
      <Harness
        initialEntries={["/strategies/compose?tab=stop-target-exec"]}
        initialState={{ ...baseState, preset: bracketPreset }}
      />,
    );
    expect(screen.getByTestId("section-stop-plan")).toBeInTheDocument();
    expect(screen.getByTestId("section-target-plan")).toBeInTheDocument();
    expect(screen.queryByTestId("section-runner-plan")).toBeNull();
  });

  it("Stop·Target·Execution tab shows all three on bracket_runner", () => {
    const baseState = editorStateFromDraft(STRATEGY_DRAFT);
    const runnerPreset: ExecutionStylePresetValue = {
      kind: "bracket_runner",
      overrides: { first_target_pct: 1.0, first_slice_pct: 0.5, trail_pct: 1.0 },
    };
    render(
      <Harness
        initialEntries={["/strategies/compose?tab=stop-target-exec"]}
        initialState={{ ...baseState, preset: runnerPreset }}
      />,
    );
    expect(screen.getByTestId("section-stop-plan")).toBeInTheDocument();
    expect(screen.getByTestId("section-target-plan")).toBeInTheDocument();
    expect(screen.getByTestId("section-runner-plan")).toBeInTheDocument();
  });

  it("computeBlueprintChips reports empty stop/target/runner on market preset", () => {
    const state = editorStateFromDraft(STRATEGY_DRAFT);
    const chips = computeBlueprintChips(state);
    expect(chips.find((c) => c.id === "stop")?.filled).toBe(false);
    expect(chips.find((c) => c.id === "target")?.filled).toBe(false);
    expect(chips.find((c) => c.id === "runner")?.filled).toBe(false);
    // Entry + exit are filled by the seeded draft.
    expect(chips.find((c) => c.id === "entry")?.filled).toBe(true);
    expect(chips.find((c) => c.id === "exit")?.filled).toBe(true);
  });
});

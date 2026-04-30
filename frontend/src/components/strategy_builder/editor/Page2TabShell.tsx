import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type {
  ExecutionMode,
  ExecutionStylePresetKind,
  FeatureCatalogItem,
} from "@/api/schemas/strategyComposer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { cn } from "@/lib/cn";
import type { ExecutionStylePresetValue } from "../ExecutionStylePresetRow";
import type { CoherenceWarning, SectionId } from "./coherenceValidator";
import {
  applyExecutionModeToDraft,
  applyPresetToDraft,
  applyStrategyControlsToDraft,
  applyStrategyToDraft,
  readExecutionMode,
  type EditorState,
} from "./editorState";
import { ExecutionPreviewRail } from "./ExecutionPreviewRail";
import { EntryPlanSection } from "./sections/EntryPlanSection";
import { EntryRulesSection } from "./sections/EntryRulesSection";
import { ExecutionPresetSection } from "./sections/ExecutionPresetSection";
import { LogicalExitSection } from "./sections/LogicalExitSection";
import { RequiredFeaturesSection } from "./sections/RequiredFeaturesSection";
import { RunnerPlanSection } from "./sections/RunnerPlanSection";
import { StopPlanSection } from "./sections/StopPlanSection";
import { StrategyControlsSection } from "./sections/StrategyControlsSection";
import { SummarySection } from "./sections/SummarySection";
import { TargetPlanSection } from "./sections/TargetPlanSection";
import { TimeBasedExitSection } from "./sections/TimeBasedExitSection";

/**
 * Page2TabShell — presentational 4-tab parent for the Page-2 editor.
 *
 * The 14 section components are unchanged; this shell only re-parents
 * them under tabs so the operator can navigate by intent rather than
 * scrolling through a 14-section column. Per memory
 * compose_page2_section_to_signalplan_mapping the section→field
 * contract is unchanged: each section still mutates exactly one
 * SignalPlan / StrategyControls field.
 *
 * Tab layout (final, mirrors the implementation plan):
 *   Core                       → Summary, RequiredFeatures
 *   Signals                    → EntryRules(long), EntryRules(short, gated), EntryPlan
 *   Stop · Target · Execution  → ExecutionPreset, StopPlan, TargetPlan,
 *                                 RunnerPlan, LogicalExit, TimeBasedExit
 *   Strategy Controls          → StrategyControls (single section for now)
 */

export type Page2TabId = "core" | "signals" | "stop-target-exec" | "controls";

const TAB_IDS: Page2TabId[] = ["core", "signals", "stop-target-exec", "controls"];

/**
 * Per active preset, which of {stop, target, runner} cards belong on the
 * Stop · Target · Execution tab.
 *
 * Source of truth is the preset shape itself (see ExecutionStylePresetRow):
 *   - market_entry_market_exit  → no stop, no target, no runner leg
 *   - stop_entry_market_exit    → stop is on the *entry*, exit is market
 *                                 → no exit-side stop, no target, no runner
 *   - bracket_stop_target       → stop + target leg, no runner
 *   - bracket_runner            → stop (trail) + first-target + runner
 *   - multi_target_scale_out    → optional stop + tier list (target),
 *                                 runner is the implicit final tier
 */
export interface PresetCardVisibility {
  stop: boolean;
  target: boolean;
  runner: boolean;
}

export function presetCardVisibility(kind: ExecutionStylePresetKind): PresetCardVisibility {
  switch (kind) {
    case "market_entry_market_exit":
    case "stop_entry_market_exit":
      return { stop: false, target: false, runner: false };
    case "bracket_stop_target":
      return { stop: true, target: true, runner: false };
    case "bracket_runner":
    case "multi_target_scale_out":
      return { stop: true, target: true, runner: true };
  }
}

export const SECTION_TO_TAB: Record<SectionId, Page2TabId> = {
  "section-required-features": "core",
  "section-entry-long": "signals",
  "section-entry-short": "signals",
  "section-stop-plan": "stop-target-exec",
  "section-target-plan": "stop-target-exec",
  "section-runner-plan": "stop-target-exec",
  "section-logical-exit": "stop-target-exec",
  "section-time-based-exit": "stop-target-exec",
  "section-strategy-controls": "controls",
  "section-execution-preset": "stop-target-exec",
};

export interface Page2TabShellProps {
  state: EditorState;
  setState: React.Dispatch<React.SetStateAction<EditorState>>;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs: Set<string>;
  warnings: CoherenceWarning[];
  warningsFor: (sectionId: SectionId) => CoherenceWarning[];
  showShortSection: boolean;
}

export function Page2TabShell(props: Page2TabShellProps): JSX.Element {
  const {
    state,
    setState,
    catalog,
    invalidFeatureRefs,
    warnings,
    warningsFor,
    showShortSection,
  } = props;

  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab");
  const activeTab: Page2TabId =
    tabFromUrl && (TAB_IDS as string[]).includes(tabFromUrl)
      ? (tabFromUrl as Page2TabId)
      : "core";

  function handleTabChange(next: string): void {
    const tab = (TAB_IDS as string[]).includes(next) ? (next as Page2TabId) : "core";
    const params = new URLSearchParams(searchParams);
    params.set("tab", tab);
    setSearchParams(params, { replace: true });
  }

  const errorCountsByTab = useMemo(() => {
    const counts: Record<Page2TabId, number> = {
      core: 0,
      signals: 0,
      "stop-target-exec": 0,
      controls: 0,
    };
    for (const w of warnings) {
      if (w.severity !== "error") continue;
      const tab = SECTION_TO_TAB[w.sectionId];
      if (tab) counts[tab] += 1;
    }
    return counts;
  }, [warnings]);

  const warnCountsByTab = useMemo(() => {
    const counts: Record<Page2TabId, number> = {
      core: 0,
      signals: 0,
      "stop-target-exec": 0,
      controls: 0,
    };
    for (const w of warnings) {
      if (w.severity !== "warn" || w.dismissed) continue;
      const tab = SECTION_TO_TAB[w.sectionId];
      if (tab) counts[tab] += 1;
    }
    return counts;
  }, [warnings]);

  const blueprintChips = computeBlueprintChips(state);
  const cardVisibility = presetCardVisibility(state.preset.kind);

  function setPreset(next: ExecutionStylePresetValue): void {
    setState((prev) => applyPresetToDraft(prev, next));
  }

  function setExecutionMode(next: ExecutionMode): void {
    setState((prev) => applyExecutionModeToDraft(prev, next));
  }

  const executionMode = readExecutionMode(state);

  return (
    <div className="flex flex-col gap-3" data-testid="page2-tab-shell">
      <BlueprintChipRow chips={blueprintChips} />
      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList data-testid="page2-tabs-list">
          <TabTrigger
            id="core"
            label="Core"
            errorCount={errorCountsByTab.core}
            warnCount={warnCountsByTab.core}
          />
          <TabTrigger
            id="signals"
            label="Signals"
            errorCount={errorCountsByTab.signals}
            warnCount={warnCountsByTab.signals}
          />
          <TabTrigger
            id="stop-target-exec"
            label="Stop · Target · Execution"
            errorCount={errorCountsByTab["stop-target-exec"]}
            warnCount={warnCountsByTab["stop-target-exec"]}
          />
          <TabTrigger
            id="controls"
            label="Strategy Controls"
            errorCount={errorCountsByTab.controls}
            warnCount={warnCountsByTab.controls}
          />
        </TabsList>

        <TabsContent value="core" forceMount data-testid="page2-tab-content-core">
          <div className="flex flex-col gap-3">
            <SummarySection
              strategy={state.draft.strategy}
              onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
            />
            <RequiredFeaturesSection
              strategy={state.draft.strategy}
              warnings={warningsFor("section-required-features")}
            />
          </div>
        </TabsContent>

        <TabsContent value="signals" forceMount data-testid="page2-tab-content-signals">
          <div className="flex flex-col gap-3">
            <EntryRulesSection
              side="long"
              number={3}
              strategy={state.draft.strategy}
              onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
              catalog={catalog}
              invalidFeatureRefs={invalidFeatureRefs}
              warnings={warningsFor("section-entry-long")}
            />
            {showShortSection ? (
              <EntryRulesSection
                side="short"
                number={4}
                strategy={state.draft.strategy}
                onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
                catalog={catalog}
                invalidFeatureRefs={invalidFeatureRefs}
                shortGated
                warnings={warningsFor("section-entry-short")}
              />
            ) : null}
            <EntryPlanSection preset={state.preset} />
          </div>
        </TabsContent>

        <TabsContent
          value="stop-target-exec"
          forceMount
          data-testid="page2-tab-content-stop-target-exec"
        >
          <div className="flex flex-col gap-3">
            <ExecutionPresetSection
              preset={state.preset}
              onChange={setPreset}
              executionMode={executionMode}
              onExecutionModeChange={setExecutionMode}
              warnings={warningsFor("section-execution-preset")}
            />
            <ExecutionPreviewRail preset={state.preset} />
            {cardVisibility.stop ? (
              <StopPlanSection
                preset={state.preset}
                onChange={setPreset}
                warnings={warningsFor("section-stop-plan")}
              />
            ) : null}
            {cardVisibility.target ? (
              <TargetPlanSection
                preset={state.preset}
                onChange={setPreset}
                warnings={warningsFor("section-target-plan")}
              />
            ) : null}
            {cardVisibility.runner ? (
              <RunnerPlanSection
                preset={state.preset}
                onChange={setPreset}
                warnings={warningsFor("section-runner-plan")}
              />
            ) : null}
            <LogicalExitSection
              strategy={state.draft.strategy}
              onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
              catalog={catalog}
              invalidFeatureRefs={invalidFeatureRefs}
              warnings={warningsFor("section-logical-exit")}
            />
            <TimeBasedExitSection
              strategy={state.draft.strategy}
              onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
              warnings={warningsFor("section-time-based-exit")}
            />
          </div>
        </TabsContent>

        <TabsContent value="controls" forceMount data-testid="page2-tab-content-controls">
          <div className="flex flex-col gap-3">
            <StrategyControlsSection
              controls={state.draft.strategy_controls ?? null}
              onChange={(next) => setState((prev) => applyStrategyControlsToDraft(prev, next))}
              warnings={warningsFor("section-strategy-controls")}
            />
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

interface TabTriggerProps {
  id: Page2TabId;
  label: string;
  errorCount: number;
  warnCount: number;
}

function TabTrigger({ id, label, errorCount, warnCount }: TabTriggerProps): JSX.Element {
  return (
    <TabsTrigger value={id} data-testid={`page2-tab-trigger-${id}`}>
      <span>{label}</span>
      {errorCount > 0 ? (
        <span
          className="ml-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-danger px-1 text-[10px] font-semibold leading-none text-bg"
          data-testid={`page2-tab-error-dot-${id}`}
        >
          {errorCount}
        </span>
      ) : warnCount > 0 ? (
        <span
          className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-warn"
          data-testid={`page2-tab-warn-dot-${id}`}
          aria-label={`${warnCount} warning${warnCount === 1 ? "" : "s"}`}
        />
      ) : null}
    </TabsTrigger>
  );
}

// ---------------------------------------------------------------------------
// Blueprint chips
// ---------------------------------------------------------------------------

export interface BlueprintChip {
  id: "entry" | "stop" | "target" | "runner" | "exit";
  label: string;
  filled: boolean;
}

export function computeBlueprintChips(state: EditorState): BlueprintChip[] {
  const strategy = state.draft.strategy;
  const preset = state.preset;
  const presetRecord = preset.overrides as Record<string, unknown> | null | undefined;

  const hasEntry = (strategy.entry_rules ?? []).length > 0;

  let hasStop = false;
  let hasTarget = false;
  let runnerFilled = false;

  if (preset.kind === "bracket_stop_target") {
    const o = presetRecord as { stop_pct?: number; target_pct?: number } | undefined;
    hasStop = typeof o?.stop_pct === "number" && o.stop_pct > 0;
    hasTarget = typeof o?.target_pct === "number" && o.target_pct > 0;
  } else if (preset.kind === "bracket_runner") {
    const o = presetRecord as
      | { first_target_pct?: number; trail_pct?: number }
      | undefined;
    hasStop = typeof o?.trail_pct === "number" && o.trail_pct > 0;
    hasTarget = typeof o?.first_target_pct === "number" && o.first_target_pct > 0;
    runnerFilled = hasTarget && hasStop;
  } else if (preset.kind === "multi_target_scale_out") {
    const o = presetRecord as
      | { stop_pct?: number | null; targets?: Array<{ target_pct?: number }> }
      | undefined;
    hasStop = typeof o?.stop_pct === "number" && (o.stop_pct ?? 0) > 0;
    const tiers = (o?.targets ?? []).filter(
      (t) => typeof t.target_pct === "number" && (t.target_pct ?? 0) > 0,
    );
    hasTarget = tiers.length > 0;
    runnerFilled = tiers.length > 1;
  }

  const exitRules = strategy.exit_rules ?? [];
  const hasExit = exitRules.some((rule) => Boolean(rule.logical_exit_rule));

  return [
    { id: "entry", label: "Entry", filled: hasEntry },
    { id: "stop", label: "Stop", filled: hasStop },
    { id: "target", label: "Target", filled: hasTarget },
    { id: "runner", label: "Runner", filled: runnerFilled },
    { id: "exit", label: "Exit", filled: hasExit },
  ];
}

function BlueprintChipRow({ chips }: { chips: BlueprintChip[] }): JSX.Element {
  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      data-testid="page2-blueprint-chips"
      aria-label="Strategy blueprint summary"
    >
      {chips.map((chip) => (
        <span
          key={chip.id}
          data-testid={`blueprint-chip-${chip.id}`}
          data-filled={chip.filled ? "true" : "false"}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
            chip.filled
              ? "border-ok/40 bg-ok-subtle/40 text-ok"
              : "border-border bg-bg-subtle text-fg-muted",
          )}
        >
          {chip.label}
          <span aria-hidden="true">{chip.filled ? "✓" : "—"}</span>
        </span>
      ))}
    </div>
  );
}

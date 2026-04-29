import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Save, Sparkles, Trash2 } from "lucide-react";
import type { ApiError } from "@/api/client";
import { StrategyComposerApi } from "@/api/strategyComposer";
import type {
  ExecutionStylePresetKind,
  StrategyDraft,
  StrategyDraftSaveResponse,
} from "@/api/schemas/strategyComposer";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import {
  defaultPresetValue,
  validatePreset,
  type ExecutionStylePresetValue,
} from "../ExecutionStylePresetRow";
import {
  applyPresetToDraft,
  applyStrategyControlsToDraft,
  applyStrategyToDraft,
  collectAllFeatureRefs,
  editorStateFromDraft,
  type EditorState,
} from "./editorState";
import { validateCoherence } from "./coherenceValidator";
import type { CoherenceWarning } from "./coherenceValidator";
import { CoherenceWarningsPanel } from "./sections/CoherenceWarningsPanel";
import { EntryPlanSection } from "./sections/EntryPlanSection";
import { EntryRulesSection } from "./sections/EntryRulesSection";
import { ExecutionPresetSection } from "./sections/ExecutionPresetSection";
import { LogicalExitSection } from "./sections/LogicalExitSection";
import { RequiredFeaturesSection } from "./sections/RequiredFeaturesSection";
import { ResearchActionsBar } from "./sections/ResearchActionsBar";
import { RunnerPlanSection } from "./sections/RunnerPlanSection";
import { StopPlanSection } from "./sections/StopPlanSection";
import { StrategyControlsSection } from "./sections/StrategyControlsSection";
import { SummarySection } from "./sections/SummarySection";
import { TargetPlanSection } from "./sections/TargetPlanSection";
import { TimeBasedExitSection } from "./sections/TimeBasedExitSection";

/**
 * EditorPage — Page-2 prefilled editor host.
 *
 * Layout (≥1024px):
 *   ┌──────────────────┬──────────────┐
 *   │ Section list     │ Sticky TOC   │
 *   │ (scrollable)     │ (right rail) │
 *   ├──────────────────┴──────────────┤
 *   │ Sticky save bar                  │
 *   └──────────────────────────────────┘
 *
 * Owns the EditorState. Each section receives a slice + onChange and
 * mutates locally; the host stitches changes back into the draft.
 *
 * Save flow (S6-D8): Page 2 is the only saver. POST /composer/drafts
 * with the current draft, then call onSaved with the saved version's
 * strategy_id + version_id so the parent can navigate to the detail
 * page with a Verify-in-Backtest banner (per StrategyDetail's
 * `composerSavedToast` location.state contract).
 */
export interface EditorPageProps {
  draft: StrategyDraft;
  /** Original wizard prompt + intent — used for the Regenerate button. */
  prompt: string | null;
  intent: Record<string, unknown> | null;
  onSaved: (response: StrategyDraftSaveResponse) => void;
  onRegenerate: () => void;
  onDiscard: () => void;
  regenerating: boolean;
}

interface SaveError {
  message: string;
}

export function EditorPage(props: EditorPageProps): JSX.Element {
  const { draft, onSaved, onRegenerate, onDiscard, regenerating } = props;
  const [state, setState] = useState<EditorState>(() => editorStateFromDraft(draft));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<SaveError | null>(null);
  const [dismissedWarnings, setDismissedWarnings] = useState<Set<string>>(() => new Set());

  // Catalog for FeatureIndex drawers + condition pickers.
  const catalog = useQuery({
    queryKey: ["strategy-builder", "features"],
    queryFn: () => StrategyComposerApi.features(),
    staleTime: 5 * 60_000,
  });

  // Tier-1 validate the union of feature refs in play, so condition
  // pickers can decorate invalid refs with the danger style.
  const refs = useMemo(() => collectAllFeatureRefs(state.draft.strategy), [state.draft.strategy]);
  const refsValidation = useQuery({
    queryKey: ["strategy-builder", "validate", "backtest", refs.join("\n")],
    queryFn: () =>
      StrategyComposerApi.validateFeatures({ feature_refs: refs, consumer: "backtest" }),
    enabled: refs.length > 0,
    staleTime: 30_000,
  });
  const invalidRefs = useMemo(() => {
    const out = new Set<string>();
    for (const item of refsValidation.data?.items ?? []) {
      if (!item.valid) out.add(item.input);
    }
    return out;
  }, [refsValidation.data]);

  // Client-side coherence warnings (run on every state change).
  const coherenceWarnings = useMemo(
    () => validateCoherence(state, catalog.data ?? [], dismissedWarnings),
    [state, catalog.data, dismissedWarnings],
  );

  const handleDismiss = useCallback((id: string) => {
    setDismissedWarnings((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  // Per-section warning slices.
  function warningsFor(sectionId: string): CoherenceWarning[] {
    return coherenceWarnings.filter((w) => w.sectionId === sectionId);
  }

  const presetValidation = validatePreset(state.preset);
  const showShortSection =
    state.draft.strategy_controls?.allowed_directions === "short" ||
    state.draft.strategy_controls?.allowed_directions === "both" ||
    (state.draft.strategy.entry_rules ?? []).some((r) => r.side === "short");

  function setPreset(next: ExecutionStylePresetValue): void {
    setState((prev) => applyPresetToDraft(prev, next));
  }

  function setPresetKind(kind: ExecutionStylePresetKind): void {
    setState((prev) => applyPresetToDraft(prev, defaultPresetValue(kind)));
  }
  void setPresetKind; // ergonomic helper, retained for future callers

  function handleSave(): void {
    setSaving(true);
    setSaveError(null);
    StrategyComposerApi.saveDraft({ draft: state.draft })
      .then((response) => {
        setSaving(false);
        onSaved(response);
      })
      .catch((err: ApiError | Error) => {
        setSaving(false);
        const detail = (err as ApiError).detail;
        setSaveError({
          message: detail || (err as Error).message || "Save failed.",
        });
      });
  }

  const backendErrors = state.draft.validation.errors ?? [];
  const coherenceErrors = coherenceWarnings.filter((w) => w.severity === "error");
  const canSave =
    !saving &&
    !regenerating &&
    presetValidation.valid &&
    backendErrors.length === 0 &&
    coherenceErrors.length === 0;

  const saveHintMessages = coherenceErrors.slice(0, 3).map((w) => w.message);

  return (
    <main
      className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_240px] grid-rows-[1fr_auto] gap-4 px-4 py-4"
      data-testid="editor-page"
    >
      {/* Section list */}
      <div className="row-start-1 col-start-1 flex flex-col gap-3 overflow-y-auto pr-2">
        <SummarySection
          strategy={state.draft.strategy}
          onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
        />
        <RequiredFeaturesSection
          strategy={state.draft.strategy}
          warnings={warningsFor("section-required-features")}
        />
        <EntryRulesSection
          side="long"
          number={3}
          strategy={state.draft.strategy}
          onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
          catalog={catalog.data ?? []}
          invalidFeatureRefs={invalidRefs}
          warnings={warningsFor("section-entry-long")}
        />
        {showShortSection ? (
          <EntryRulesSection
            side="short"
            number={4}
            strategy={state.draft.strategy}
            onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
            catalog={catalog.data ?? []}
            invalidFeatureRefs={invalidRefs}
            shortGated
            warnings={warningsFor("section-entry-short")}
          />
        ) : null}
        <EntryPlanSection preset={state.preset} />
        <StopPlanSection
          preset={state.preset}
          onChange={setPreset}
          warnings={warningsFor("section-stop-plan")}
        />
        <TargetPlanSection
          preset={state.preset}
          onChange={setPreset}
          warnings={warningsFor("section-target-plan")}
        />
        <RunnerPlanSection
          preset={state.preset}
          onChange={setPreset}
          warnings={warningsFor("section-runner-plan")}
        />
        <LogicalExitSection
          strategy={state.draft.strategy}
          onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
          catalog={catalog.data ?? []}
          invalidFeatureRefs={invalidRefs}
          warnings={warningsFor("section-logical-exit")}
        />
        <TimeBasedExitSection
          strategy={state.draft.strategy}
          onChange={(next) => setState((prev) => applyStrategyToDraft(prev, next))}
          warnings={warningsFor("section-time-based-exit")}
        />
        <StrategyControlsSection
          controls={state.draft.strategy_controls ?? null}
          onChange={(next) => setState((prev) => applyStrategyControlsToDraft(prev, next))}
          warnings={warningsFor("section-strategy-controls")}
        />
        <ExecutionPresetSection
          preset={state.preset}
          onChange={setPreset}
          warnings={warningsFor("section-execution-preset")}
        />
        <CoherenceWarningsPanel
          draft={state.draft}
          warnings={coherenceWarnings}
          onDismiss={handleDismiss}
        />
        <ResearchActionsBar savedStrategyId={null} />
      </div>

      {/* Sticky right-rail TOC */}
      <aside className="row-start-1 col-start-2 sticky top-0 self-start" aria-label="Editor table of contents">
        <nav
          className="flex flex-col gap-0.5 rounded border border-border bg-bg-raised p-2 text-[11px]"
          data-testid="editor-toc"
        >
          <TocLink id="section-summary" label="1 · Summary" />
          <TocLink id="section-required-features" label="2 · Required features" />
          <TocLink id="section-entry-long" label="3 · Long entry" />
          {showShortSection ? <TocLink id="section-entry-short" label="4 · Short entry" /> : null}
          <TocLink id="section-entry-plan" label="5 · Entry plan" />
          <TocLink id="section-stop-plan" label="6 · Stop plan" />
          <TocLink id="section-target-plan" label="7 · Target plan" />
          <TocLink id="section-runner-plan" label="8 · Runner plan" />
          <TocLink id="section-logical-exit" label="9 · Logical exit" />
          <TocLink id="section-time-based-exit" label="10 · Time-based exit" />
          <TocLink id="section-strategy-controls" label="11 · Strategy Controls" />
          <TocLink id="section-execution-preset" label="12 · Execution preset" />
          <TocLink id="section-coherence" label="13 · Validation" />
          <TocLink id="section-research-actions" label="14 · Research actions" />
        </nav>
      </aside>

      {/* Sticky save bar (full width across both columns) */}
      <div
        className="row-start-2 col-span-2 flex flex-wrap items-center justify-between gap-3 rounded border border-border bg-bg-raised px-3 py-2"
        data-testid="editor-save-bar"
      >
        <div className="flex items-center gap-2">
          {saveError ? (
            <Banner severity="danger" title="Save failed" message={saveError.message} />
          ) : null}
          {!presetValidation.valid ? (
            <span className="text-[11px] text-danger" data-testid="preset-invalid-hint">
              Preset overrides invalid: {presetValidation.errors.slice(0, 1).join("")}
            </span>
          ) : coherenceErrors.length > 0 ? (
            <span className="text-[11px] text-danger" data-testid="coherence-error-hint">
              {saveHintMessages.join(" · ")}
            </span>
          ) : backendErrors.length > 0 ? (
            <span className="text-[11px] text-danger" data-testid="draft-invalid-hint">
              {backendErrors.length} validation error{backendErrors.length === 1 ? "" : "s"} — see Section 13.
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            leftIcon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={onDiscard}
            data-testid="editor-discard"
          >
            Discard
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={onRegenerate}
            loading={regenerating}
            disabled={regenerating || saving}
            data-testid="editor-regenerate"
          >
            Regenerate strategy
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            leftIcon={<Save className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={handleSave}
            loading={saving}
            disabled={!canSave}
            data-testid="editor-save"
          >
            Save as draft
          </Button>
        </div>
      </div>
    </main>
  );
}

function TocLink({ id, label }: { id: string; label: string }): JSX.Element {
  return (
    <a
      href={`#${id}`}
      className="rounded px-2 py-1 text-fg-muted hover:bg-bg-inset hover:text-fg"
      data-testid={`toc-${id}`}
    >
      {label}
    </a>
  );
}

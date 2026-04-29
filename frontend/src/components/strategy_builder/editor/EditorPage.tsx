import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ExternalLink, Save, Sparkles, Trash2 } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import type { ApiError } from "@/api/client";
import { StrategyComposerApi } from "@/api/strategyComposer";
import type {
  StrategyDraft,
  StrategyDraftSaveResponse,
} from "@/api/schemas/strategyComposer";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/Dialog";
import { cn } from "@/lib/cn";
import { validatePreset } from "../ExecutionStylePresetRow";
import {
  collectAllFeatureRefs,
  editorStateFromDraft,
  type EditorState,
} from "./editorState";
import { validateCoherence } from "./coherenceValidator";
import type { CoherenceWarning } from "./coherenceValidator";
import { CoherenceWarningsPanel } from "./sections/CoherenceWarningsPanel";
import { Page2TabShell, SECTION_TO_TAB } from "./Page2TabShell";

/**
 * EditorPage — Page-2 prefilled editor host.
 *
 * Layout (≥1024px):
 *   ┌──────────────────────────────────┐
 *   │ Page2TabShell                    │
 *   │ (4 tabs, blueprint chips)        │
 *   ├──────────────────────────────────┤
 *   │ Sticky save bar                   │
 *   │  · Validation popover trigger     │
 *   │  · Research action deep-links     │
 *   │  · Discard / Regenerate / Save    │
 *   └──────────────────────────────────┘
 *
 * Owns the EditorState. Each section receives a slice + onChange and
 * mutates locally; the host stitches changes back into the draft.
 *
 * Save flow (S6-D8): Page 2 is the only saver. POST /composer/drafts
 * with the current draft, then call onSaved with the saved version's
 * strategy_id + version_id so the parent can navigate to the detail
 * page with a Verify-in-Backtest banner.
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
  const [validationOpen, setValidationOpen] = useState(false);
  const [, setSearchParams] = useSearchParams();

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
  const warningsFor = useCallback(
    (sectionId: string): CoherenceWarning[] =>
      coherenceWarnings.filter((w) => w.sectionId === sectionId),
    [coherenceWarnings],
  );

  // Slice C-3: jump from a validation row to the offending section.
  // Switches the tab via ?tab=, closes the popover, then on the next
  // animation frame scrolls the section card into view (giving Radix
  // a tick to mark the new TabsContent active).
  const handleJumpToSection = useCallback(
    (sectionId: CoherenceWarning["sectionId"]) => {
      const tab = SECTION_TO_TAB[sectionId];
      if (tab) {
        setSearchParams(
          (prev) => {
            const next = new URLSearchParams(prev);
            next.set("tab", tab);
            return next;
          },
          { replace: true },
        );
      }
      setValidationOpen(false);
      if (typeof window !== "undefined") {
        window.requestAnimationFrame(() => {
          const el = document.getElementById(sectionId);
          if (el) {
            el.scrollIntoView({ behavior: "smooth", block: "start" });
          }
        });
      }
    },
    [setSearchParams],
  );

  const presetValidation = validatePreset(state.preset);
  const showShortSection =
    state.draft.strategy_controls?.allowed_directions === "short" ||
    state.draft.strategy_controls?.allowed_directions === "both" ||
    (state.draft.strategy.entry_rules ?? []).some((r) => r.side === "short");

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
  const backendWarnings = state.draft.validation.warnings ?? [];
  const coherenceErrors = coherenceWarnings.filter((w) => w.severity === "error");
  const undismissedClientWarns = coherenceWarnings.filter(
    (w) => w.severity === "warn" && !w.dismissed,
  );
  const undismissedClientInfos = coherenceWarnings.filter(
    (w) => w.severity === "info" && !w.dismissed,
  );
  // Validation badge counts split by severity so the operator can tell at a
  // glance whether the popover holds blocking errors, advisory warnings, or
  // purely informational notes.
  const validationErrorCount = backendErrors.length + coherenceErrors.length;
  const validationWarnCount = backendWarnings.length + undismissedClientWarns.length;
  const validationInfoCount = undismissedClientInfos.length;
  const validationTotalCount =
    validationErrorCount + validationWarnCount + validationInfoCount;
  const validationBadgeTone: "danger" | "warn" | "info" | "none" =
    validationErrorCount > 0
      ? "danger"
      : validationWarnCount > 0
      ? "warn"
      : validationInfoCount > 0
      ? "info"
      : "none";
  const canSave =
    !saving &&
    !regenerating &&
    presetValidation.valid &&
    backendErrors.length === 0 &&
    coherenceErrors.length === 0;

  const saveHintMessages = coherenceErrors.slice(0, 3).map((w) => w.message);

  return (
    <main
      className="grid min-h-0 flex-1 grid-rows-[1fr_auto] gap-4 px-4 py-4"
      data-testid="editor-page"
    >
      {/* Tabbed section list (full width — TOC removed) */}
      <div className="row-start-1 flex flex-col gap-3 overflow-y-auto pr-2">
        <Page2TabShell
          state={state}
          setState={setState}
          catalog={catalog.data ?? []}
          invalidFeatureRefs={invalidRefs}
          warnings={coherenceWarnings}
          warningsFor={warningsFor}
          showShortSection={showShortSection}
        />
      </div>

      {/* Sticky save bar */}
      <div
        className="row-start-2 flex flex-wrap items-center justify-between gap-3 rounded border border-border bg-bg-raised px-3 py-2"
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
              {backendErrors.length} validation error{backendErrors.length === 1 ? "" : "s"} — open Validation.
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          <Dialog open={validationOpen} onOpenChange={setValidationOpen}>
            <DialogTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                leftIcon={<AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />}
                data-testid="editor-validation-trigger"
              >
                Validation
                {validationTotalCount > 0 ? (
                  <span
                    className={cn(
                      "ml-1 inline-flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold leading-none",
                      validationBadgeTone === "danger"
                        ? "bg-danger text-bg"
                        : validationBadgeTone === "warn"
                        ? "bg-warn text-bg"
                        : "bg-bg-inset text-fg-muted ring-1 ring-border",
                    )}
                    data-testid="editor-validation-badge"
                    data-tone={validationBadgeTone}
                    data-error-count={validationErrorCount}
                    data-warn-count={validationWarnCount}
                    data-info-count={validationInfoCount}
                  >
                    {validationTotalCount}
                  </span>
                ) : null}
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-xl" data-testid="editor-validation-popover">
              <DialogHeader>
                <DialogTitle>Validation</DialogTitle>
              </DialogHeader>
              <CoherenceWarningsPanel
                draft={state.draft}
                warnings={coherenceWarnings}
                onDismiss={handleDismiss}
                onJumpToSection={handleJumpToSection}
              />
            </DialogContent>
          </Dialog>

          <ResearchActionLink
            label="Verify in Backtest"
            href="#"
            disabled
            testid="editor-action-backtest"
          />
          <ResearchActionLink
            label="Sim Lab"
            href="#"
            disabled
            testid="editor-action-sim-lab"
          />
          <ResearchActionLink
            label="Chart Lab"
            href="#"
            disabled
            testid="editor-action-chart-lab"
          />

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

interface ResearchActionLinkProps {
  label: string;
  href: string;
  disabled: boolean;
  testid: string;
}

function ResearchActionLink({ label, href, disabled, testid }: ResearchActionLinkProps): JSX.Element {
  if (disabled) {
    return (
      <Button
        type="button"
        size="sm"
        variant="ghost"
        disabled
        leftIcon={<ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />}
        title="Save first"
        data-testid={testid}
      >
        {label}
      </Button>
    );
  }
  return (
    <Link to={href} data-testid={testid}>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        leftIcon={<ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />}
      >
        {label}
      </Button>
    </Link>
  );
}

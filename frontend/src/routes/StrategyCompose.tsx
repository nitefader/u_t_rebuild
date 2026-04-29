import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { ApiError } from "@/api/client";
import { StrategyComposerApi } from "@/api/strategyComposer";
import type {
  AIComposerRequest,
  StrategyDraft,
  StrategyDraftSaveResponse,
  WizardIntent,
} from "@/api/schemas/strategyComposer";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { useApplyTheme } from "@/store/useAppShell";
import {
  StarterTemplatePanel,
} from "@/components/strategy_builder/wizard/StarterTemplatePanel";
import type { StarterTemplate } from "@/components/strategy_builder/wizard/templates";
import {
  DEFAULT_WIZARD_INTENT,
  WizardStep1,
} from "@/components/strategy_builder/wizard/WizardStep1";
import { EditorPage } from "@/components/strategy_builder/editor/EditorPage";

/**
 * StrategyCompose — focused-mode AI Composer route.
 *
 * Mounts OUTSIDE the global AppShell (router.tsx). Two-page wizard host:
 *
 *   Page 1 (Slice 6b — wizard):
 *     - Prompt textarea + intent checkboxes (`WizardIntent`)
 *     - Side panel of curated starter templates (`StarterTemplatePanel`)
 *     - "Skip wizard" → straight to Page 2 with no `WizardIntent`
 *     - "Generate with AI" → POST /composer/preview with WizardIntent
 *
 *   Page 2 (Slice 6c — prefilled editor):
 *     - 14 fixed sections, each mapped 1:1 to a SignalPlan leg or a
 *       Strategy Controls field. See `EditorPage`.
 *     - Save → POST /composer/drafts → navigate to /strategies/:id
 *       with `composerSavedToast` location.state for the Verify-in-
 *       Backtest banner.
 *     - Regenerate → re-runs /composer/preview with the current prompt
 *       + intent and replaces the draft. Per S6-D9, this is the
 *       page-level full regenerate; per-section regenerate is deferred
 *       to 6c-bis.
 *
 * Doctrine guards:
 *   - Strategy is symbol-agnostic (no symbol field anywhere here).
 *   - FeatureIndex is an assistive editor tool, mounted as a drawer
 *     from individual editor sections — never a left rail.
 *   - All downstream surfaces (Backtest, Sim Lab, Chart Lab,
 *     Optimization, Walk-Forward, Runtime) derive features from the
 *     saved StrategyVersion, never from a parallel UI selection.
 *   - AI never fires while the operator types — explicit Generate /
 *     Regenerate clicks only.
 *   - Esc-on-dirty confirms before exit. Save is the only commit.
 */

const WIZARD_STATE_KEY = "compose:wizard:draft";

type WizardStep = "page1" | "page2";

interface PersistedWizardState {
  step: WizardStep;
  prompt: string;
  intent: WizardIntent;
}

function readPersistedState(): PersistedWizardState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(WIZARD_STATE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedWizardState;
    if (parsed.step !== "page1" && parsed.step !== "page2") return null;
    if (typeof parsed.prompt !== "string") return null;
    if (!parsed.intent || typeof parsed.intent !== "object") return null;
    return parsed;
  } catch {
    return null;
  }
}

function writePersistedState(state: PersistedWizardState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(WIZARD_STATE_KEY, JSON.stringify(state));
  } catch {
    // Silent — localStorage unavailable.
  }
}

function clearPersistedState(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(WIZARD_STATE_KEY);
  } catch {
    // Silent.
  }
}

export function StrategyCompose(): JSX.Element {
  useApplyTheme();
  const navigate = useNavigate();

  const initial = useMemo(() => readPersistedState(), []);
  const [step, setStep] = useState<WizardStep>(initial?.step ?? "page1");
  const [prompt, setPrompt] = useState<string>(initial?.prompt ?? "");
  const [intent, setIntent] = useState<WizardIntent>(initial?.intent ?? DEFAULT_WIZARD_INTENT);
  const [draft, setDraft] = useState<StrategyDraft | null>(null);
  const [skippedWizard, setSkippedWizard] = useState(false);

  // Persist on every change.
  useEffect(() => {
    writePersistedState({ step, prompt, intent });
  }, [step, prompt, intent]);

  const dirty =
    prompt.trim().length > 0 ||
    intent.direction !== DEFAULT_WIZARD_INTENT.direction ||
    intent.horizon !== DEFAULT_WIZARD_INTENT.horizon ||
    intent.base_timeframe !== DEFAULT_WIZARD_INTENT.base_timeframe ||
    intent.higher_timeframe_confirmation !== DEFAULT_WIZARD_INTENT.higher_timeframe_confirmation ||
    Boolean(draft);

  // Body-overflow lock for focused-mode chrome.
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  // Esc-on-dirty confirms before exit (operator-locked: minimal keyboard).
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;
  useEffect(() => {
    function onKey(e: KeyboardEvent): void {
      if (e.key !== "Escape") return;
      if (dirtyRef.current && !window.confirm("Discard draft and exit composer?")) return;
      clearPersistedState();
      navigate(-1);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  const generate = useMutation({
    mutationFn: (req: AIComposerRequest) => StrategyComposerApi.composerPreview(req),
    onSuccess: (next) => {
      setDraft(next);
      setStep("page2");
    },
  });

  function buildRequest(): AIComposerRequest {
    return {
      prompt: prompt.trim(),
      timeframe: intent.base_timeframe,
      initial_capital: 100_000,
      feature_refs: [],
      execution_style_preset: "market_entry_market_exit",
      execution_style_overrides: null,
      wizard_intent: intent,
    };
  }

  function handleGenerate(): void {
    generate.reset();
    generate.mutate(buildRequest());
  }

  function handleRegenerate(): void {
    if (
      window.confirm(
        "Regenerate the strategy from the current prompt + wizard intent? This replaces all prefilled sections.",
      )
    ) {
      handleGenerate();
    }
  }

  function handleSkipWizard(): void {
    setSkippedWizard(true);
    setStep("page2");
  }

  function handleApplyTemplate(template: StarterTemplate): void {
    setPrompt(template.prompt_seed);
    setIntent(template.wizard_intent_seed);
  }

  function handleExit(): void {
    if (dirty && !window.confirm("Discard draft and exit composer?")) return;
    clearPersistedState();
    navigate(-1);
  }

  function handleSaved(response: StrategyDraftSaveResponse): void {
    const versionId = response.strategy_version.strategy_version_id;
    const strategyId = response.strategy_version.strategy_id;
    clearPersistedState();
    navigate(`/strategies/${strategyId}`, {
      state: {
        composerSavedToast: {
          name: response.strategy_version.payload.name,
          versionId,
          verifyInBacktestHref: `/strategies/${strategyId}?launch=backtest&version=${versionId}`,
        },
      },
    });
  }

  function handleDiscardDraft(): void {
    if (window.confirm("Discard the AI draft and return to Page 1?")) {
      setDraft(null);
      setStep("page1");
    }
  }

  const generateError =
    generate.error instanceof ApiError
      ? generate.error.detail || generate.error.message
      : generate.error
        ? String(generate.error)
        : null;

  return (
    <div id="compose-root" className="flex h-screen w-screen flex-col bg-bg">
      <header className="flex items-center justify-between border-b border-border bg-bg-raised px-4 py-2">
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleExit}
            leftIcon={<ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />}
          >
            Exit
          </Button>
          <span className="text-[11px] text-fg-muted">
            Composer · Page {step === "page1" ? "1" : "2"} of 2
          </span>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-fg-muted">
          {step === "page2" && !skippedWizard ? (
            <Button variant="ghost" size="sm" onClick={() => setStep("page1")} data-testid="back-to-page1">
              ← Back to wizard
            </Button>
          ) : null}
        </div>
      </header>

      {step === "page1" ? (
        <main className="grid min-h-0 flex-1 grid-cols-[1fr_360px]">
          <WizardStep1
            prompt={prompt}
            onPromptChange={setPrompt}
            intent={intent}
            onIntentChange={setIntent}
            onGenerate={handleGenerate}
            onSkipWizard={handleSkipWizard}
            generating={generate.isPending}
            generateError={generateError}
          />
          <StarterTemplatePanel prompt={prompt} onApplyTemplate={handleApplyTemplate} />
        </main>
      ) : draft ? (
        <EditorPage
          key={draft.draft_id ?? draft.strategy.id}
          draft={draft}
          prompt={prompt}
          intent={intent as unknown as Record<string, unknown>}
          onSaved={handleSaved}
          onRegenerate={handleRegenerate}
          onDiscard={handleDiscardDraft}
          regenerating={generate.isPending}
        />
      ) : (
        <SkippedWizardLanding onBack={() => setStep("page1")} />
      )}
    </div>
  );
}

interface SkippedWizardLandingProps {
  onBack: () => void;
}

/** When the operator clicks Skip Wizard there is no draft yet, so the
 * editor cannot mount. Render a small affordance explaining the path
 * forward — Page 2 is the only saver, and Save needs a draft (S6-D8).
 * Operator either generates from Page 1 or aborts. */
function SkippedWizardLanding(props: SkippedWizardLandingProps): JSX.Element {
  return (
    <main
      className="flex flex-1 items-center justify-center p-6"
      data-testid="page2-stub"
    >
      <div className="max-w-xl rounded border border-border bg-bg-subtle p-6">
        <h2 className="text-lg font-semibold">No draft to edit</h2>
        <p className="mt-2 text-sm text-fg-muted">
          You skipped the wizard, but the editor needs a starting draft. Return to Page 1 and
          either pick a template or generate from a prompt.
        </p>
        <div className="mt-3" data-testid="page2-draft-loaded" data-draft-loaded="no">
          no
        </div>
        <p className="mt-3 text-[11px] text-fg-muted">Skipped wizard (legacy path).</p>
        <Banner
          severity="info"
          title="Composer is wizard-driven"
          message="Page 2 is the only saver. Page 1 captures intent, AI generates the prefilled draft, then Page 2 lets you edit and save."
          className="mt-3"
        />
        <div className="mt-4">
          <Button variant="primary" size="sm" onClick={props.onBack}>
            ← Back to wizard
          </Button>
        </div>
      </div>
    </main>
  );
}

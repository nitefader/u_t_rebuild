/**
 * AIPromptTab — AI seed-fill tab inside StarterStrategyPanel.
 *
 * Operator types a strategy idea, clicks Generate, reviews the AI draft,
 * then either Applies it to the editor or Discards it.
 *
 * Apply fires the same onApplyTemplate callback used by template cards;
 * the parent page does not distinguish between AI and template origins.
 */

import { useState } from "react";
import { Loader2, ChevronDown, ChevronRight } from "lucide-react";
import { ApiError } from "@/api/client";
import { aiFillStrategy } from "@/api/strategiesV4";
import type { AISeedFillResponse } from "@/api/strategiesV4";
import type { StrategyVersionV4Draft } from "@/api/schemas/strategiesV4";

const SUGGESTION_CHIPS = [
  "FVG long-only on 5m",
  "Mean reversion with RSI(2) on 1d",
  "Opening range breakout with volume confirmation",
  "VWAP reclaim intraday",
  "Momentum breakout with ATR stop on 15m",
] as const;

const MIN_PROMPT_LENGTH = 8;

interface AIPromptTabProps {
  /** Called when the operator clicks Apply — same signature as template Apply. */
  onApplyTemplate: (draft: StrategyVersionV4Draft) => void;
  /** Optional current draft to pass as context to the AI. */
  currentDraft?: StrategyVersionV4Draft;
}

type Status =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; response: AISeedFillResponse }
  | { kind: "error"; message: string; is412: boolean };

export function AIPromptTab({ onApplyTemplate, currentDraft }: AIPromptTabProps): JSX.Element {
  const [prompt, setPrompt] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [detailsOpen, setDetailsOpen] = useState(false);

  const canGenerate = prompt.trim().length >= MIN_PROMPT_LENGTH && status.kind !== "loading";

  async function handleGenerate(): Promise<void> {
    if (!canGenerate) return;
    setStatus({ kind: "loading" });
    setDetailsOpen(false);
    try {
      const response = await aiFillStrategy(prompt.trim(), currentDraft);
      setStatus({ kind: "success", response });
    } catch (err) {
      if (err instanceof ApiError) {
        const is412 = err.status === 412;
        setStatus({ kind: "error", message: err.detail || err.message, is412 });
      } else if (err instanceof Error) {
        setStatus({ kind: "error", message: err.message, is412: false });
      } else {
        setStatus({ kind: "error", message: "Unexpected error", is412: false });
      }
    }
  }

  function handleApply(response: AISeedFillResponse): void {
    onApplyTemplate(response.draft);
    // Parent switches back to Templates tab via its own state; we just reset ours.
    setStatus({ kind: "idle" });
    setPrompt("");
  }

  function handleDiscard(): void {
    setStatus({ kind: "idle" });
  }

  function handleRetry(): void {
    void handleGenerate();
  }

  return (
    <div className="flex flex-col gap-3 px-3 py-3">
      {/* Textarea */}
      <div className="flex flex-col gap-1">
        <label htmlFor="ai-prompt-input" className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">
          Strategy idea
        </label>
        <textarea
          id="ai-prompt-input"
          rows={3}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder='e.g. "FVG strategy on 5m, long-only, with 1R target"'
          className="w-full resize-none rounded border border-border bg-bg-inset px-2 py-1.5 text-xs text-fg placeholder-fg-subtle focus:border-accent focus:outline-none"
          aria-label="Strategy idea prompt"
        />
      </div>

      {/* Suggestion chips */}
      <div className="flex flex-wrap gap-1" role="list" aria-label="Prompt suggestions">
        {SUGGESTION_CHIPS.map((chip) => (
          <button
            key={chip}
            type="button"
            role="listitem"
            className="rounded-full border border-border bg-bg-inset px-2 py-0.5 text-[10px] text-fg-subtle hover:border-accent hover:text-accent transition-colors focus:outline-none"
            onClick={() => setPrompt(chip)}
            aria-label={`Fill prompt: ${chip}`}
          >
            {chip}
          </button>
        ))}
      </div>

      {/* Generate button */}
      <button
        type="button"
        disabled={!canGenerate}
        onClick={() => void handleGenerate()}
        className="flex items-center justify-center gap-2 rounded border border-accent bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20 transition-colors focus:outline-none disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="Generate with AI"
        data-testid="ai-generate-btn"
      >
        {status.kind === "loading" ? (
          <>
            <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
            Generating...
          </>
        ) : (
          "Generate with AI"
        )}
      </button>

      {/* Loading skeleton */}
      {status.kind === "loading" && (
        <div className="flex flex-col gap-2" aria-live="polite" aria-label="Generating strategy">
          <div className="h-3 rounded bg-bg-inset animate-pulse w-3/4" />
          <div className="h-3 rounded bg-bg-inset animate-pulse w-1/2" />
          <div className="h-3 rounded bg-bg-inset animate-pulse w-5/6" />
        </div>
      )}

      {/* Success result card */}
      {status.kind === "success" && (
        <ResultCard
          response={status.response}
          detailsOpen={detailsOpen}
          onToggleDetails={() => setDetailsOpen((v) => !v)}
          onApply={() => handleApply(status.response)}
          onDiscard={handleDiscard}
        />
      )}

      {/* Error banner */}
      {status.kind === "error" && (
        <ErrorBanner
          message={status.message}
          is412={status.is412}
          onRetry={handleRetry}
        />
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Result card sub-component
// ---------------------------------------------------------------------------

interface ResultCardProps {
  response: AISeedFillResponse;
  detailsOpen: boolean;
  onToggleDetails: () => void;
  onApply: () => void;
  onDiscard: () => void;
}

function ResultCard({
  response,
  detailsOpen,
  onToggleDetails,
  onApply,
  onDiscard,
}: ResultCardProps): JSX.Element {
  const { draft, validation_status, provider_used, model_used, raw_response_excerpt, notes } = response;

  const entryPreview =
    draft.entries.long?.expression_text ??
    draft.entries.short?.expression_text ??
    "(no entry expression)";

  const hasErrors = !validation_status.valid;

  return (
    <div
      className="rounded-lg border border-border bg-bg-raised overflow-hidden"
      data-testid="ai-result-card"
      role="region"
      aria-label="AI generated strategy result"
    >
      {/* Header */}
      <div className="px-3 pt-2.5 pb-2">
        <div className="flex items-start justify-between gap-2">
          <p className="text-xs font-semibold text-fg leading-tight">{draft.name}</p>
          {validation_status.valid ? (
            <span
              className="shrink-0 inline-flex items-center gap-1 rounded-full bg-ok-subtle px-1.5 py-0.5 text-[9px] font-medium text-ok"
              data-testid="ai-validation-pill-valid"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-ok" />
              Valid
            </span>
          ) : (
            <span
              className="shrink-0 inline-flex items-center gap-1 rounded-full bg-warn-subtle px-1.5 py-0.5 text-[9px] font-medium text-warn"
              data-testid="ai-validation-pill-invalid"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-warn" />
              {validation_status.errors.length} error{validation_status.errors.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        <p className="mt-0.5 text-[10px] text-fg-muted leading-snug font-mono truncate">
          {entryPreview}
        </p>
        <p className="mt-0.5 text-[9px] text-fg-subtle">
          via {provider_used} / {model_used}
        </p>
        {notes.length > 0 && (
          <p className="mt-1 text-[10px] text-fg-muted italic leading-snug">{notes[0]}</p>
        )}
      </div>

      {/* Validation warning banner — shown when AI output has errors */}
      {hasErrors && (
        <div
          className="border-t border-warn/30 bg-warn-subtle px-3 py-2"
          role="alert"
          data-testid="ai-validation-warning-banner"
        >
          <p className="text-[10px] font-semibold text-warn mb-1">AI output has validation errors.</p>
          {validation_status.errors.slice(0, 2).map((err, i) => (
            <p key={i} className="text-[10px] text-warn/80 leading-snug">
              {err}
            </p>
          ))}
          <p className="mt-1 text-[10px] text-fg-muted">Apply anyway and fix manually, or discard.</p>
        </div>
      )}

      {/* Show details toggle */}
      <div className="border-t border-border">
        <button
          type="button"
          className="flex w-full items-center gap-1 px-3 py-1.5 text-[10px] text-fg-subtle hover:text-fg transition-colors focus:outline-none"
          onClick={onToggleDetails}
          aria-expanded={detailsOpen}
          aria-label="Show AI response details"
          data-testid="ai-toggle-details"
        >
          {detailsOpen ? (
            <ChevronDown className="h-3 w-3" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-3 w-3" aria-hidden="true" />
          )}
          Show details
        </button>
        {detailsOpen && (
          <div className="px-3 pb-2 pt-0">
            <p className="text-[9px] font-semibold uppercase tracking-wider text-fg-subtle mb-0.5">
              Raw response excerpt
            </p>
            <pre className="text-[9px] text-fg-muted font-mono whitespace-pre-wrap break-all leading-snug">
              {raw_response_excerpt}
            </pre>
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 border-t border-border px-3 py-2">
        <button
          type="button"
          className="flex-1 rounded border border-accent bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20 transition-colors focus:outline-none"
          onClick={onApply}
          aria-label="Apply AI draft to editor"
          data-testid="ai-apply-btn"
        >
          Apply to draft
        </button>
        <button
          type="button"
          className="rounded border border-border px-3 py-1.5 text-xs text-fg-subtle hover:bg-bg-raised transition-colors focus:outline-none"
          onClick={onDiscard}
          aria-label="Discard AI generated draft"
          data-testid="ai-discard-btn"
        >
          Discard
        </button>
      </div>
    </div>
  );
}


// ---------------------------------------------------------------------------
// Error banner sub-component
// ---------------------------------------------------------------------------

interface ErrorBannerProps {
  message: string;
  is412: boolean;
  onRetry: () => void;
}

function ErrorBanner({ message, is412, onRetry }: ErrorBannerProps): JSX.Element {
  if (is412) {
    return (
      <div
        className="rounded-lg border border-danger/40 bg-danger-subtle px-3 py-2"
        role="alert"
        data-testid="ai-error-412"
      >
        <p className="text-[10px] font-semibold text-danger">No default AI provider configured.</p>
        <p className="mt-0.5 text-[10px] text-danger/80">
          Configure one in{" "}
          <a href="/providers" className="underline hover:opacity-80">
            Providers settings
          </a>
          .
        </p>
      </div>
    );
  }

  return (
    <div
      className="rounded-lg border border-danger/40 bg-danger-subtle px-3 py-2 flex items-start justify-between gap-2"
      role="alert"
      data-testid="ai-error-banner"
    >
      <div className="flex-1 min-w-0">
        <p className="text-[10px] font-semibold text-danger">AI generation failed.</p>
        <p className="mt-0.5 text-[10px] text-danger/80 break-words">{message}</p>
      </div>
      <button
        type="button"
        className="shrink-0 rounded border border-danger/40 px-2 py-1 text-[10px] font-medium text-danger hover:bg-danger/10 transition-colors focus:outline-none"
        onClick={onRetry}
        aria-label="Retry AI generation"
        data-testid="ai-retry-btn"
      >
        Retry
      </button>
    </div>
  );
}

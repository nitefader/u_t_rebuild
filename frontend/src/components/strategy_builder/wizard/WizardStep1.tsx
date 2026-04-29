import { useEffect, useMemo, useRef } from "react";
import { Sparkles } from "lucide-react";
import type { WizardIntent } from "@/api/schemas/strategyComposer";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { cn } from "@/lib/cn";
import {
  detectConflicts,
  extractIntent,
  type WizardConflict,
} from "./intentExtraction";

const SUPPORTED_TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;

const HORIZON_LABEL: Record<WizardIntent["horizon"], string> = {
  scalping: "Scalping",
  intraday: "Intraday",
  swing: "Swing",
  position: "Position",
};

const DIRECTION_LABEL: Record<WizardIntent["direction"], string> = {
  long: "Long",
  short: "Short",
  both: "Both",
};

export const DEFAULT_WIZARD_INTENT: WizardIntent = {
  direction: "long",
  horizon: "intraday",
  base_timeframe: "5m",
  higher_timeframe_confirmation: false,
  has_stop: true,
  has_target: false,
  has_multiple_targets: false,
  has_runner: false,
  has_logical_exit: true,
  has_time_based_exit: false,
};

export interface WizardStep1Props {
  prompt: string;
  onPromptChange: (next: string) => void;
  intent: WizardIntent;
  onIntentChange: (next: WizardIntent) => void;
  onGenerate: () => void;
  onSkipWizard: () => void;
  generating: boolean;
  generateError: string | null;
}

export function WizardStep1({
  prompt,
  onPromptChange,
  intent,
  onIntentChange,
  onGenerate,
  onSkipWizard,
  generating,
  generateError,
}: WizardStep1Props): JSX.Element {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const conflicts: WizardConflict[] = useMemo(
    () => detectConflicts(extractIntent(prompt), intent),
    [prompt, intent],
  );

  const promptOk = prompt.trim().length >= 10;
  const canGenerate = promptOk && !generating;

  function handleAdjustToPrompt(field: WizardConflict["field"], next: string) {
    onIntentChange({ ...intent, [field]: next as never });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>): void {
    // Cmd/Ctrl+Enter triggers Generate (Enter alone allows newlines in textarea).
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canGenerate) {
      e.preventDefault();
      onGenerate();
    }
  }

  return (
    <section className="flex h-full flex-col gap-4 overflow-y-auto p-4" aria-label="Compose wizard">
      <header className="flex items-start justify-between gap-3">
        <div>
          <h1 className="text-base font-semibold">Describe what you want to trade</h1>
          <p className="mt-1 text-[12px] text-fg-muted">
            Pick a starter on the right or describe your idea below. The AI never fires while you type — click{" "}
            <strong>Generate with AI</strong> when you&rsquo;re ready.
          </p>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onSkipWizard}
          data-testid="skip-wizard-button"
          title="Skip the wizard and build from scratch on Page 2."
        >
          Skip wizard
        </Button>
      </header>

      <div>
        <label htmlFor="wizard-prompt" className="block text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
          Strategy idea
        </label>
        <textarea
          id="wizard-prompt"
          ref={textareaRef}
          value={prompt}
          onChange={(e) => onPromptChange(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={6}
          className={cn(
            "mt-1 block w-full rounded border bg-bg-inset px-3 py-2 text-sm focus:outline-none",
            promptOk ? "border-border focus:border-accent" : "border-border focus:border-accent",
          )}
          placeholder="e.g. Long when 5m close > 20-EMA and RSI > 55. Stop 1× ATR below entry. Exit 30 minutes after entry, or 5 minutes before close."
          data-testid="wizard-prompt"
        />
        <div className="mt-1 flex items-center justify-between text-[10.5px] text-fg-subtle">
          <span>{prompt.trim().length} characters · ⌘⏎ to Generate</span>
          {!promptOk ? <span>Add a few sentences before Generate is enabled.</span> : null}
        </div>
      </div>

      <fieldset className="rounded border border-border bg-bg-subtle p-3" data-testid="wizard-intent">
        <legend className="px-1 text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
          Intent
        </legend>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <RadioGroup
            label="Direction"
            value={intent.direction}
            options={[
              ["long", "Long only"],
              ["short", "Short only"],
              ["both", "Both"],
            ]}
            onChange={(v) => onIntentChange({ ...intent, direction: v as WizardIntent["direction"] })}
            name="direction"
          />
          <RadioGroup
            label="Horizon"
            value={intent.horizon}
            options={[
              ["scalping", "Scalping"],
              ["intraday", "Intraday"],
              ["swing", "Swing"],
              ["position", "Position"],
            ]}
            onChange={(v) => onIntentChange({ ...intent, horizon: v as WizardIntent["horizon"] })}
            name="horizon"
          />
          <Select
            label="Base timeframe"
            value={intent.base_timeframe}
            onChange={(e) => onIntentChange({ ...intent, base_timeframe: e.target.value })}
            data-testid="base-timeframe-select"
          >
            {SUPPORTED_TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </Select>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
          <CheckboxRow
            label="Higher-timeframe confirmation"
            checked={intent.higher_timeframe_confirmation}
            onChange={(v) =>
              onIntentChange({ ...intent, higher_timeframe_confirmation: v })
            }
          />
          <CheckboxRow
            label="Stop"
            checked={intent.has_stop}
            onChange={(v) => onIntentChange({ ...intent, has_stop: v })}
          />
          <CheckboxRow
            label="Target"
            checked={intent.has_target}
            onChange={(v) => onIntentChange({ ...intent, has_target: v })}
          />
          <CheckboxRow
            label="Multiple targets / scale-out"
            checked={intent.has_multiple_targets}
            onChange={(v) => onIntentChange({ ...intent, has_multiple_targets: v })}
          />
          <CheckboxRow
            label="Runner"
            checked={intent.has_runner}
            onChange={(v) => onIntentChange({ ...intent, has_runner: v })}
          />
          <CheckboxRow
            label="Logical exit"
            checked={intent.has_logical_exit}
            onChange={(v) => onIntentChange({ ...intent, has_logical_exit: v })}
          />
          <CheckboxRow
            label="Time-based exit"
            checked={intent.has_time_based_exit}
            onChange={(v) => onIntentChange({ ...intent, has_time_based_exit: v })}
          />
        </div>
      </fieldset>

      {conflicts.length > 0 ? (
        <div
          role="status"
          data-testid="wizard-conflicts"
          className="rounded border border-warning/40 bg-warning/10 p-3 text-[12px] text-warning"
        >
          <div className="font-semibold">Your prompt and intent disagree</div>
          <ul className="mt-1 space-y-1">
            {conflicts.map((c) => (
              <li key={c.field} className="flex items-center justify-between gap-2">
                <span>
                  Prompt suggests <strong>{prettyValue(c.field, c.prompt_value)}</strong>; intent is set to{" "}
                  <strong>{prettyValue(c.field, c.checkbox_value)}</strong>.
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleAdjustToPrompt(c.field, c.prompt_value)}
                  data-testid={`adjust-${c.field}`}
                >
                  Adjust to match prompt
                </Button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {generateError ? (
        <Banner severity="danger" title="Generate failed" message={generateError} />
      ) : null}

      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          size="md"
          disabled={!canGenerate}
          loading={generating}
          onClick={onGenerate}
          leftIcon={<Sparkles className="h-4 w-4" aria-hidden="true" />}
          data-testid="generate-with-ai-button"
        >
          Generate with AI
        </Button>
        <span className="text-[11px] text-fg-muted">
          The AI never fires while you type. Click to generate.
        </span>
      </div>
    </section>
  );
}

function prettyValue(field: WizardConflict["field"], value: string): string {
  if (field === "horizon") return HORIZON_LABEL[value as WizardIntent["horizon"]] ?? value;
  if (field === "direction") return DIRECTION_LABEL[value as WizardIntent["direction"]] ?? value;
  return value;
}

interface RadioGroupProps<T extends string> {
  label: string;
  value: T;
  options: ReadonlyArray<readonly [T, string]>;
  onChange: (next: T) => void;
  name: string;
}

function RadioGroup<T extends string>({
  label,
  value,
  options,
  onChange,
  name,
}: RadioGroupProps<T>): JSX.Element {
  return (
    <div>
      <span className="block text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
        {label}
      </span>
      <div className="mt-1 flex flex-wrap gap-1">
        {options.map(([val, lbl]) => (
          <label
            key={val}
            className={cn(
              "cursor-pointer rounded border px-2 py-1 text-[12px]",
              value === val
                ? "border-accent bg-accent/15 text-accent"
                : "border-border bg-bg-inset hover:bg-bg-inset/70",
            )}
            data-testid={`radio-${name}-${val}`}
          >
            <input
              type="radio"
              name={name}
              value={val}
              checked={value === val}
              onChange={() => onChange(val)}
              className="sr-only"
            />
            {lbl}
          </label>
        ))}
      </div>
    </div>
  );
}

interface CheckboxRowProps {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}

function CheckboxRow({ label, checked, onChange }: CheckboxRowProps): JSX.Element {
  return (
    <label className="flex cursor-pointer items-center gap-2 rounded border border-border bg-bg-inset px-2 py-1.5 text-[12px] hover:bg-bg-inset/70">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5"
      />
      <span>{label}</span>
    </label>
  );
}

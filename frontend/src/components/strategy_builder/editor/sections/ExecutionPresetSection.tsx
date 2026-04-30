import {
  ExecutionStylePresetRow,
  type ExecutionStylePresetValue,
} from "../../ExecutionStylePresetRow";
import type { ExecutionMode } from "@/api/schemas/strategyComposer";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * ExecutionPresetSection (#12) — wraps the existing ExecutionStylePresetRow
 * and delegates to its segmented selector + Customize disclosure. The
 * five operator-locked presets are the source of truth for the SignalPlan
 * shape — the frontend never composes a SignalPlan locally.
 *
 * Stop / Target / Runner sections (6, 7, 8) edit slices of this preset's
 * overrides directly so the operator can think about each leg
 * independently. Changes in those sections flow back through this
 * preset value via the host's onChange handler.
 *
 * Bracket Program T-2: this section also owns the operator-visible
 * `execution_mode` selector. Default is `post_fill_bracket`. Operators
 * can opt into `native_alpaca_bracket` per ExecutionPlan, with a clear
 * warning about the Alpaca constraint matrix.
 */
export interface ExecutionPresetSectionProps {
  preset: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
  executionMode: ExecutionMode;
  onExecutionModeChange: (next: ExecutionMode) => void;
  warnings?: CoherenceWarning[];
}

export function ExecutionPresetSection(props: ExecutionPresetSectionProps): JSX.Element {
  const { preset, onChange, executionMode, onExecutionModeChange, warnings } = props;

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";

  return (
    <SectionCard
      id="section-execution-preset"
      number={12}
      title="Execution preset"
      severity={sectionSeverity}
      subtitle="One of the five locked presets. Drives the SignalPlan shape (entry leg, stop, targets, runner)."
    >
      {warnings && warnings.length > 0 ? (
        <div className="mb-2 space-y-1">
          {warnings.filter((w) => !w.dismissed || w.severity === "error").map((w) => (
            <div key={w.id} className={cn("rounded px-2 py-1 text-[11px]", w.severity === "error" ? "text-danger bg-danger-subtle/30" : "text-warn bg-warn-subtle/30")}>
              {w.message}
            </div>
          ))}
        </div>
      ) : null}
      <ExecutionStylePresetRow value={preset} onChange={onChange} />
      <ExecutionModeRow value={executionMode} onChange={onExecutionModeChange} />
    </SectionCard>
  );
}

interface ExecutionModeRowProps {
  value: ExecutionMode;
  onChange: (next: ExecutionMode) => void;
}

const EXECUTION_MODE_LABELS: Record<ExecutionMode, { label: string; hint: string }> = {
  post_fill_bracket: {
    label: "Post-fill bracket (default)",
    hint: "Submit entry, wait for BrokerSync-confirmed fill, compute stop/target from the actual fill, submit OCO protective pair. Handles partial fills idempotently.",
  },
  native_alpaca_bracket: {
    label: "Native Alpaca bracket (optional)",
    hint: "Broker-native OrderClass.BRACKET. Whole-share, day/gtc, regular hours, ETB-if-short only. Pre-flight rejects fractional, notional, extended-hours.",
  },
};

function ExecutionModeRow({ value, onChange }: ExecutionModeRowProps): JSX.Element {
  return (
    <div className="mt-3 space-y-1.5">
      <label
        htmlFor="execution-mode-select"
        className="block text-[11px] font-medium uppercase tracking-wider text-muted"
      >
        Execution mode
      </label>
      <select
        id="execution-mode-select"
        value={value}
        onChange={(e) => onChange(e.target.value as ExecutionMode)}
        className="w-full rounded border border-default bg-surface px-2 py-1.5 text-sm"
      >
        {(Object.keys(EXECUTION_MODE_LABELS) as ExecutionMode[]).map((mode) => (
          <option key={mode} value={mode}>
            {EXECUTION_MODE_LABELS[mode].label}
          </option>
        ))}
      </select>
      <p className="text-[11px] text-muted">{EXECUTION_MODE_LABELS[value].hint}</p>
    </div>
  );
}

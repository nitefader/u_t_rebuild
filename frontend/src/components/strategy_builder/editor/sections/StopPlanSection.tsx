import type {
  BracketRunnerOverrides,
  BracketStopTargetOverrides,
  ExecutionStylePresetValue,
  MultiTargetScaleOutOverrides,
} from "../../ExecutionStylePresetRow";
import { Banner } from "@/components/ui/Banner";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * StopPlanSection (#6) — operator-facing knobs for the stop side of
 * the active execution preset. The preset itself lives in Section 12;
 * this section exposes only the stop-related overrides so the operator
 * thinks about risk per leg.
 */
export interface StopPlanSectionProps {
  preset: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
  warnings?: CoherenceWarning[];
}

export function StopPlanSection(props: StopPlanSectionProps): JSX.Element {
  const { preset, onChange, warnings } = props;

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";

  return (
    <SectionCard
      id="section-stop-plan"
      number={6}
      title="Stop plan"
      subtitle="Stop side of the active execution preset (% of entry, or none if the preset has no stop)."
      severity={sectionSeverity}
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
      <StopBody preset={preset} onChange={onChange} />
    </SectionCard>
  );
}

function StopBody({
  preset,
  onChange,
}: {
  preset: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
}): JSX.Element {
  if (preset.kind === "market_entry_market_exit") {
    return (
      <Banner
        severity="info"
        title="No stop"
        message="The Market Entry / Market Exit preset has no protective stop. If you want a stop, switch presets in Section 12."
      />
    );
  }
  if (preset.kind === "stop_entry_market_exit") {
    return (
      <Banner
        severity="info"
        title="Entry stop, not protective stop"
        message="Stop Entry / Market Exit uses a stop ORDER for entry. There is no separate protective stop — exits are signal-driven via Logical Exit."
      />
    );
  }
  if (preset.kind === "bracket_stop_target") {
    const o = preset.overrides as BracketStopTargetOverrides;
    return (
      <PercentKnob
        label="Stop %"
        value={o.stop_pct}
        onChange={(next) =>
          onChange({ kind: preset.kind, overrides: { ...o, stop_pct: next } })
        }
        testId="stop-pct"
      />
    );
  }
  if (preset.kind === "bracket_runner") {
    const o = preset.overrides as BracketRunnerOverrides;
    return (
      <Banner
        severity="info"
        title="Trailing stop"
        message={`Bracket + Runner uses a trailing stop at ${o.trail_pct}% rather than a fixed protective stop. Edit Trail % in the Runner plan section.`}
      />
    );
  }
  if (preset.kind === "multi_target_scale_out") {
    const o = preset.overrides as MultiTargetScaleOutOverrides;
    const stopOn = o.stop_pct !== null && o.stop_pct !== undefined;
    return (
      <div className="space-y-2 text-xs">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={stopOn}
            onChange={(e) =>
              onChange({
                kind: preset.kind,
                overrides: { ...o, stop_pct: e.target.checked ? 1.0 : null },
              })
            }
            data-testid="stop-pct-toggle"
          />
          <span>Enable protective stop</span>
        </label>
        {stopOn ? (
          <PercentKnob
            label="Stop %"
            value={o.stop_pct ?? 1}
            onChange={(next) =>
              onChange({ kind: preset.kind, overrides: { ...o, stop_pct: next } })
            }
            testId="stop-pct"
          />
        ) : (
          <p className="text-[11px] text-fg-muted">
            Multi-Target Scale-Out without a stop relies entirely on targets. Add a stop if any
            slice should fail closed.
          </p>
        )}
      </div>
    );
  }
  return <div />;
}

function PercentKnob({
  label,
  value,
  onChange,
  testId,
}: {
  label: string;
  value: number;
  onChange: (next: number) => void;
  testId: string;
}): JSX.Element {
  return (
    <label className="block max-w-xs text-xs">
      <span className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</span>
      <input
        type="number"
        min={0.01}
        step={0.1}
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => {
          const next = Number(e.target.value);
          onChange(Number.isFinite(next) ? next : 0);
        }}
        className="mt-0.5 block w-full rounded border border-border bg-bg-inset px-2 py-1 font-mono text-xs focus:border-accent focus:outline-none"
        data-testid={testId}
      />
    </label>
  );
}

import type {
  BracketRunnerOverrides,
  ExecutionStylePresetValue,
} from "../../ExecutionStylePresetRow";
import { Banner } from "@/components/ui/Banner";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * RunnerPlanSection (#8) — visible only when the active execution preset
 * is BRACKET_RUNNER. Edits the trail % knob; the first-target % and
 * first-slice live in Target plan because they belong to the bracket
 * leg, not the runner.
 */
export interface RunnerPlanSectionProps {
  preset: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
  warnings?: CoherenceWarning[];
}

export function RunnerPlanSection(props: RunnerPlanSectionProps): JSX.Element {
  const { preset, onChange, warnings } = props;

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";

  return (
    <SectionCard
      id="section-runner-plan"
      number={8}
      title="Runner plan"
      subtitle="The slice that stays in after the first target releases. Trails by ATR-style %."
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
      {preset.kind !== "bracket_runner" ? (
        <Banner
          severity="info"
          title="Not a runner preset"
          message="Runner plan is only used when the execution preset is Bracket + Runner. Switch presets in Section 12 to enable."
        />
      ) : (
        <RunnerBody preset={preset} onChange={onChange} />
      )}
    </SectionCard>
  );
}

function RunnerBody({
  preset,
  onChange,
}: {
  preset: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
}): JSX.Element {
  const o = preset.overrides as BracketRunnerOverrides;
  const runnerSlice = Math.max(0, 1 - (Number.isFinite(o.first_slice_pct) ? o.first_slice_pct : 0));

  return (
    <div className="space-y-3">
      <div className="grid max-w-md grid-cols-1 gap-2">
        <label className="block text-xs">
          <span className="text-[10px] uppercase tracking-wide text-fg-muted">Trail %</span>
          <input
            type="number"
            min={0.01}
            step={0.1}
            value={Number.isFinite(o.trail_pct) ? o.trail_pct : 0}
            onChange={(e) => {
              const next = Number(e.target.value);
              onChange({
                kind: preset.kind,
                overrides: { ...o, trail_pct: Number.isFinite(next) ? next : 0 },
              });
            }}
            className="mt-0.5 block w-full rounded border border-border bg-bg-inset px-2 py-1 font-mono text-xs focus:border-accent focus:outline-none"
            data-testid="trail-pct"
          />
        </label>
      </div>
      <p className="text-[11px] text-fg-muted">
        Runner holds {runnerSlice.toFixed(2)} of the position after the first target releases
        (1 − first slice = runner slice).
      </p>
    </div>
  );
}

import {
  ExecutionStylePresetRow,
  type ExecutionStylePresetValue,
} from "../../ExecutionStylePresetRow";
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
 */
export interface ExecutionPresetSectionProps {
  preset: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
  warnings?: CoherenceWarning[];
}

export function ExecutionPresetSection(props: ExecutionPresetSectionProps): JSX.Element {
  const { preset, onChange, warnings } = props;

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
    </SectionCard>
  );
}

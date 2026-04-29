import { Plus, Trash2 } from "lucide-react";
import type {
  BracketRunnerOverrides,
  BracketStopTargetOverrides,
  ExecutionStylePresetValue,
  MultiTargetScaleOutOverrides,
  MultiTargetTier,
} from "../../ExecutionStylePresetRow";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * TargetPlanSection (#7) — operator-facing knobs for the target side
 * of the active execution preset. The Multi-Target Scale-Out tier list
 * lives here; bracket presets show a single Target %.
 */
export interface TargetPlanSectionProps {
  preset: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
  warnings?: CoherenceWarning[];
}

export function TargetPlanSection(props: TargetPlanSectionProps): JSX.Element {
  const { preset, onChange, warnings } = props;

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";

  return (
    <SectionCard
      id="section-target-plan"
      number={7}
      title="Target plan"
      subtitle="Target / scale-out side of the active execution preset."
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
      <Body preset={preset} onChange={onChange} />
    </SectionCard>
  );
}

function Body({
  preset,
  onChange,
}: {
  preset: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
}): JSX.Element {
  if (preset.kind === "market_entry_market_exit" || preset.kind === "stop_entry_market_exit") {
    return (
      <Banner
        severity="info"
        title="No target"
        message="This preset exits via signal logic, not a fixed target. Switch presets in Section 12 to add a target."
      />
    );
  }
  if (preset.kind === "bracket_stop_target") {
    const o = preset.overrides as BracketStopTargetOverrides;
    return (
      <PercentKnob
        label="Target %"
        value={o.target_pct}
        onChange={(next) =>
          onChange({ kind: preset.kind, overrides: { ...o, target_pct: next } })
        }
        testId="target-pct"
      />
    );
  }
  if (preset.kind === "bracket_runner") {
    const o = preset.overrides as BracketRunnerOverrides;
    return (
      <div className="grid max-w-md grid-cols-2 gap-2">
        <PercentKnob
          label="First target %"
          value={o.first_target_pct}
          onChange={(next) =>
            onChange({ kind: preset.kind, overrides: { ...o, first_target_pct: next } })
          }
          testId="first-target-pct"
        />
        <FractionKnob
          label="First slice (0–1)"
          value={o.first_slice_pct}
          onChange={(next) =>
            onChange({ kind: preset.kind, overrides: { ...o, first_slice_pct: next } })
          }
          testId="first-slice-pct"
        />
      </div>
    );
  }
  if (preset.kind === "multi_target_scale_out") {
    const o = preset.overrides as MultiTargetScaleOutOverrides;
    return <MultiTargetTable value={o} onChange={(next) => onChange({ kind: preset.kind, overrides: next })} />;
  }
  return <div />;
}

function MultiTargetTable({
  value,
  onChange,
}: {
  value: MultiTargetScaleOutOverrides;
  onChange: (next: MultiTargetScaleOutOverrides) => void;
}): JSX.Element {
  function setTier(at: number, next: MultiTargetTier): void {
    onChange({ ...value, targets: value.targets.map((t, i) => (i === at ? next : t)) });
  }
  function removeTier(at: number): void {
    onChange({ ...value, targets: value.targets.filter((_, i) => i !== at) });
  }
  function addTier(): void {
    const last = value.targets[value.targets.length - 1];
    onChange({
      ...value,
      targets: [
        ...value.targets,
        { target_pct: last ? last.target_pct + 1 : 1, slice_pct: 0.1 },
      ],
    });
  }
  const total = value.targets.reduce(
    (acc, t) => acc + (Number.isFinite(t.slice_pct) ? t.slice_pct : 0),
    0,
  );

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-wide text-fg-muted">Targets</span>
        <span className="text-[10px] text-fg-muted">slice sum = {total.toFixed(2)} / 1.00</span>
      </div>
      <div className="space-y-1" data-testid="multi-target-tiers">
        {value.targets.map((tier, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2">
            <PercentKnob
              label={`#${i + 1} target %`}
              value={tier.target_pct}
              onChange={(next) => setTier(i, { ...tier, target_pct: next })}
              testId={`target-pct-${i}`}
            />
            <FractionKnob
              label="slice (0–1)"
              value={tier.slice_pct}
              onChange={(next) => setTier(i, { ...tier, slice_pct: next })}
              testId={`slice-pct-${i}`}
            />
            <button
              type="button"
              onClick={() => removeTier(i)}
              className="self-end rounded border border-border bg-bg-inset p-1 text-fg-muted hover:border-danger hover:text-danger"
              aria-label={`Remove target ${i + 1}`}
            >
              <Trash2 className="h-3 w-3" aria-hidden="true" />
            </button>
          </div>
        ))}
      </div>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        leftIcon={<Plus className="h-3 w-3" aria-hidden="true" />}
        onClick={addTier}
        data-testid="add-target-tier"
      >
        Add target
      </Button>
    </div>
  );
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
    <label className="block text-xs">
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

function FractionKnob({
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
    <label className="block text-xs">
      <span className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</span>
      <input
        type="number"
        min={0.01}
        max={1}
        step={0.05}
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

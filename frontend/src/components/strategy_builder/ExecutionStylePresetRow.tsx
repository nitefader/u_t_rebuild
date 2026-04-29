import { useMemo, useState } from "react";
import { ChevronDown, Plus, Trash2 } from "lucide-react";
import type { ExecutionStylePresetKind } from "@/api/schemas/strategyComposer";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/**
 * ExecutionStylePresetRow — segmented preset selector + per-preset
 * Customize disclosure for the focused-mode AI Composer.
 *
 * The 5 presets are operator-locked (see Strategies redesign plan). Each
 * preset emits a strict SignalPlan shape; the backend is the source of
 * truth for that mapping (`build_execution_style_version` +
 * `build_signal_plan_shape_preview`). This component is purely the UI:
 *
 *   - 5 segmented buttons (pick one)
 *   - inline "Customize" knobs panel
 *   - Tier-1 LOCAL validation of the knob shape (numeric ranges, slice
 *     sum constraints) — does NOT compute the SignalPlan itself
 *
 * The composer route owns the `value` and forwards it to the typed client
 * as `{ execution_style_preset, execution_style_overrides }`.
 */

export interface ExecutionStylePresetValue {
  kind: ExecutionStylePresetKind;
  overrides: ExecutionStyleOverrides;
}

export type ExecutionStyleOverrides =
  | Record<string, never>
  | StopEntryOverrides
  | BracketStopTargetOverrides
  | BracketRunnerOverrides
  | MultiTargetScaleOutOverrides;

export interface StopEntryOverrides {
  entry_stop_offset_bps: number;
}

export interface BracketStopTargetOverrides {
  stop_pct: number;
  target_pct: number;
}

export interface BracketRunnerOverrides {
  first_target_pct: number;
  first_slice_pct: number;
  trail_pct: number;
}

export interface MultiTargetTier {
  target_pct: number;
  slice_pct: number;
}

export interface MultiTargetScaleOutOverrides {
  targets: MultiTargetTier[];
  stop_pct: number | null;
}

export interface ExecutionStylePresetValidation {
  valid: boolean;
  errors: string[];
}

interface PresetMeta {
  kind: ExecutionStylePresetKind;
  label: string;
  summary: string;
}

const PRESETS: readonly PresetMeta[] = [
  {
    kind: "market_entry_market_exit",
    label: "Market Entry / Market Exit",
    summary: "Market order in on entry signal; market order out on exit signal.",
  },
  {
    kind: "stop_entry_market_exit",
    label: "Stop Entry / Market Exit",
    summary: "Stop order at signal-bar reference + offset; market out on exit signal.",
  },
  {
    kind: "bracket_stop_target",
    label: "Bracket: Stop + Target",
    summary: "Market in. OCO bracket: whichever of stop / target fills cancels the other.",
  },
  {
    kind: "bracket_runner",
    label: "Bracket + Runner",
    summary: "Market in. First target releases part of the position; runner trails.",
  },
  {
    kind: "multi_target_scale_out",
    label: "Multi-Target Scale-Out",
    summary: "Market in. N scaling targets each release a slice of the position.",
  },
] as const;

export function defaultPresetValue(kind: ExecutionStylePresetKind): ExecutionStylePresetValue {
  switch (kind) {
    case "market_entry_market_exit":
      return { kind, overrides: {} };
    case "stop_entry_market_exit":
      return { kind, overrides: { entry_stop_offset_bps: 10 } };
    case "bracket_stop_target":
      return { kind, overrides: { stop_pct: 1.0, target_pct: 2.0 } };
    case "bracket_runner":
      return { kind, overrides: { first_target_pct: 1.0, first_slice_pct: 0.5, trail_pct: 1.0 } };
    case "multi_target_scale_out":
      return {
        kind,
        overrides: {
          targets: [
            { target_pct: 1.0, slice_pct: 0.25 },
            { target_pct: 2.0, slice_pct: 0.25 },
            { target_pct: 3.0, slice_pct: 0.25 },
            { target_pct: 4.0, slice_pct: 0.25 },
          ],
          stop_pct: null,
        },
      };
  }
}

export function presetMeta(kind: ExecutionStylePresetKind): PresetMeta {
  return PRESETS.find((p) => p.kind === kind) ?? PRESETS[0];
}

export function validatePreset(value: ExecutionStylePresetValue): ExecutionStylePresetValidation {
  const errors: string[] = [];
  const { kind, overrides } = value;

  if (kind === "stop_entry_market_exit") {
    const v = (overrides as StopEntryOverrides).entry_stop_offset_bps;
    if (!(typeof v === "number" && Number.isFinite(v) && v >= 0)) {
      errors.push("entry_stop_offset_bps must be ≥ 0");
    }
  }
  if (kind === "bracket_stop_target") {
    const o = overrides as BracketStopTargetOverrides;
    if (!(o.stop_pct > 0)) errors.push("stop_pct must be > 0");
    if (!(o.target_pct > 0)) errors.push("target_pct must be > 0");
  }
  if (kind === "bracket_runner") {
    const o = overrides as BracketRunnerOverrides;
    if (!(o.first_target_pct > 0)) errors.push("first_target_pct must be > 0");
    if (!(o.first_slice_pct > 0 && o.first_slice_pct <= 1)) {
      errors.push("first_slice_pct must be in (0, 1]");
    }
    if (!(o.trail_pct > 0)) errors.push("trail_pct must be > 0");
  }
  if (kind === "multi_target_scale_out") {
    const o = overrides as MultiTargetScaleOutOverrides;
    if (!Array.isArray(o.targets) || o.targets.length === 0) {
      errors.push("at least one target is required");
    } else {
      let total = 0;
      o.targets.forEach((tier, i) => {
        if (!(tier.target_pct > 0)) errors.push(`targets[${i}].target_pct must be > 0`);
        if (!(tier.slice_pct > 0 && tier.slice_pct <= 1)) {
          errors.push(`targets[${i}].slice_pct must be in (0, 1]`);
        }
        total += Number.isFinite(tier.slice_pct) ? tier.slice_pct : 0;
      });
      if (total > 1.0001) {
        errors.push(`target slice_pct sum must be ≤ 1 (got ${total.toFixed(2)})`);
      }
    }
    if (o.stop_pct !== null && o.stop_pct !== undefined && !(o.stop_pct > 0)) {
      errors.push("stop_pct must be > 0 when set");
    }
  }

  return { valid: errors.length === 0, errors };
}

export interface ExecutionStylePresetRowProps {
  value: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
}

export function ExecutionStylePresetRow(props: ExecutionStylePresetRowProps): JSX.Element {
  const { value, onChange } = props;
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const validation = useMemo(() => validatePreset(value), [value]);
  const meta = presetMeta(value.kind);

  function selectPreset(kind: ExecutionStylePresetKind): void {
    if (kind === value.kind) return;
    onChange(defaultPresetValue(kind));
    setCustomizeOpen(false);
  }

  return (
    <section
      className="rounded border border-border bg-bg-subtle px-3 py-2"
      aria-label="Execution style preset"
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
          Execution style
        </span>
        <span className="text-[11px] text-fg-muted">·</span>
        <span className="text-[11px] text-fg-muted">{meta.summary}</span>
      </div>
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="Execution preset">
        {PRESETS.map((preset) => (
          <button
            key={preset.kind}
            type="button"
            role="radio"
            aria-checked={preset.kind === value.kind}
            onClick={() => selectPreset(preset.kind)}
            className={cn(
              "rounded border px-2 py-1 text-[11px]",
              preset.kind === value.kind
                ? "border-accent bg-accent/15 text-fg"
                : "border-border bg-bg-raised text-fg-muted hover:border-accent/60 hover:text-fg",
            )}
          >
            {preset.label}
          </button>
        ))}
      </div>

      {value.kind !== "market_entry_market_exit" ? (
        <button
          type="button"
          className="mt-2 flex items-center gap-1 text-[11px] text-fg-muted hover:text-fg"
          onClick={() => setCustomizeOpen((v) => !v)}
          aria-expanded={customizeOpen}
        >
          <ChevronDown
            className={cn("h-3 w-3 transition-transform", customizeOpen && "rotate-180")}
            aria-hidden="true"
          />
          Customize
        </button>
      ) : null}

      {customizeOpen && value.kind !== "market_entry_market_exit" ? (
        <div className="mt-2 rounded border border-border bg-bg-raised px-3 py-2">
          <CustomizePanel value={value} onChange={onChange} />
        </div>
      ) : null}

      {!validation.valid ? (
        <div className="mt-2 rounded border border-danger/40 bg-danger-subtle/40 px-2 py-1 text-[11px] text-danger">
          {validation.errors.slice(0, 3).join(" · ")}
        </div>
      ) : null}
    </section>
  );
}

function CustomizePanel({
  value,
  onChange,
}: {
  value: ExecutionStylePresetValue;
  onChange: (next: ExecutionStylePresetValue) => void;
}): JSX.Element {
  if (value.kind === "stop_entry_market_exit") {
    const o = value.overrides as StopEntryOverrides;
    return (
      <NumberKnob
        label="Entry stop offset (bps)"
        min={0}
        step={1}
        value={o.entry_stop_offset_bps}
        onChange={(next) =>
          onChange({ kind: value.kind, overrides: { entry_stop_offset_bps: next } })
        }
      />
    );
  }
  if (value.kind === "bracket_stop_target") {
    const o = value.overrides as BracketStopTargetOverrides;
    return (
      <div className="grid grid-cols-2 gap-2">
        <NumberKnob
          label="Stop %"
          min={0.01}
          step={0.1}
          value={o.stop_pct}
          onChange={(next) => onChange({ kind: value.kind, overrides: { ...o, stop_pct: next } })}
        />
        <NumberKnob
          label="Target %"
          min={0.01}
          step={0.1}
          value={o.target_pct}
          onChange={(next) => onChange({ kind: value.kind, overrides: { ...o, target_pct: next } })}
        />
      </div>
    );
  }
  if (value.kind === "bracket_runner") {
    const o = value.overrides as BracketRunnerOverrides;
    return (
      <div className="grid grid-cols-3 gap-2">
        <NumberKnob
          label="First target %"
          min={0.01}
          step={0.1}
          value={o.first_target_pct}
          onChange={(next) =>
            onChange({ kind: value.kind, overrides: { ...o, first_target_pct: next } })
          }
        />
        <NumberKnob
          label="First slice (0–1)"
          min={0.01}
          max={1}
          step={0.05}
          value={o.first_slice_pct}
          onChange={(next) =>
            onChange({ kind: value.kind, overrides: { ...o, first_slice_pct: next } })
          }
        />
        <NumberKnob
          label="Trail %"
          min={0.01}
          step={0.1}
          value={o.trail_pct}
          onChange={(next) => onChange({ kind: value.kind, overrides: { ...o, trail_pct: next } })}
        />
      </div>
    );
  }
  if (value.kind === "multi_target_scale_out") {
    const o = value.overrides as MultiTargetScaleOutOverrides;
    return (
      <MultiTargetEditor
        value={o}
        onChange={(next) => onChange({ kind: value.kind, overrides: next })}
      />
    );
  }
  return <div />;
}

function MultiTargetEditor({
  value,
  onChange,
}: {
  value: MultiTargetScaleOutOverrides;
  onChange: (next: MultiTargetScaleOutOverrides) => void;
}): JSX.Element {
  function setTier(index: number, next: MultiTargetTier): void {
    onChange({ ...value, targets: value.targets.map((t, i) => (i === index ? next : t)) });
  }
  function removeTier(index: number): void {
    onChange({ ...value, targets: value.targets.filter((_, i) => i !== index) });
  }
  function addTier(): void {
    const last = value.targets[value.targets.length - 1];
    onChange({
      ...value,
      targets: [
        ...value.targets,
        {
          target_pct: last ? last.target_pct + 1 : 1,
          slice_pct: 0.1,
        },
      ],
    });
  }
  function setStopPct(next: number | null): void {
    onChange({ ...value, stop_pct: next });
  }

  const total = value.targets.reduce((acc, t) => acc + (Number.isFinite(t.slice_pct) ? t.slice_pct : 0), 0);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-[10.5px] uppercase tracking-wide text-fg-muted">Targets</span>
        <span className="text-[10.5px] text-fg-muted">slice sum = {total.toFixed(2)} / 1.00</span>
      </div>
      <div className="space-y-1">
        {value.targets.map((tier, i) => (
          <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2">
            <NumberKnob
              label={`#${i + 1} target %`}
              min={0.01}
              step={0.1}
              value={tier.target_pct}
              onChange={(next) => setTier(i, { ...tier, target_pct: next })}
            />
            <NumberKnob
              label="slice (0–1)"
              min={0.01}
              max={1}
              step={0.05}
              value={tier.slice_pct}
              onChange={(next) => setTier(i, { ...tier, slice_pct: next })}
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
      <div className="flex items-center justify-between">
        <Button type="button" size="sm" variant="secondary" onClick={addTier} leftIcon={<Plus className="h-3 w-3" aria-hidden="true" />}>
          Add target
        </Button>
        <label className="flex items-center gap-1 text-[11px] text-fg-muted">
          <input
            type="checkbox"
            checked={value.stop_pct !== null && value.stop_pct !== undefined}
            onChange={(e) => setStopPct(e.target.checked ? 1.0 : null)}
          />
          Stop %
        </label>
        {value.stop_pct !== null && value.stop_pct !== undefined ? (
          <NumberKnob
            label=""
            min={0.01}
            step={0.1}
            value={value.stop_pct}
            onChange={(next) => setStopPct(next)}
          />
        ) : null}
      </div>
    </div>
  );
}

function NumberKnob({
  label,
  min,
  max,
  step,
  value,
  onChange,
}: {
  label: string;
  min?: number;
  max?: number;
  step?: number;
  value: number;
  onChange: (next: number) => void;
}): JSX.Element {
  return (
    <label className="block">
      {label ? (
        <span className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</span>
      ) : null}
      <input
        type="number"
        min={min}
        max={max}
        step={step ?? 0.01}
        value={Number.isFinite(value) ? value : 0}
        onChange={(e) => {
          const next = Number(e.target.value);
          onChange(Number.isFinite(next) ? next : 0);
        }}
        className="mt-0.5 block w-full rounded border border-border bg-bg-inset px-1.5 py-1 font-mono text-xs focus:border-accent focus:outline-none"
      />
    </label>
  );
}

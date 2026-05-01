/**
 * LegRow — single leg row in the Trade legs section.
 *
 * size_pct stored as 0..1; displayed as 0–100%.
 * target_type='feature' hides target_value (set to null).
 */

import type { StrategyLegV4Draft, LegKindV4, LegTargetTypeV4 } from "@/api/schemas/strategiesV4";
import { OnFillActionSubform } from "./OnFillActionSubform";
import { Select } from "@/components/ui/Select";

const TARGET_TYPE_LABELS: Record<LegTargetTypeV4, string> = {
  "%": "% of price",
  ATR: "ATR multiple",
  $: "Dollar amount",
  R: "R multiple",
  feature: "Feature (computed at runtime)",
  "trail-ATR": "Trailing — ATR",
  "trail-%": "Trailing — %",
  "trail-$": "Trailing — $",
};

export interface LegRowProps {
  leg: StrategyLegV4Draft;
  index: number;
  totalLegs: number;
  onChange: (leg: StrategyLegV4Draft) => void;
  onRemove: () => void;
}

export function LegRow({
  leg,
  index,
  totalLegs,
  onChange,
  onRemove,
}: LegRowProps): JSX.Element {
  const displayPct = parseFloat((leg.size_pct * 100).toFixed(4));

  function handleKindChange(kind: LegKindV4): void {
    onChange({ ...leg, kind });
  }

  function handleSizePctChange(raw: string): void {
    const parsed = parseFloat(raw);
    const asDecimal = isNaN(parsed) ? 0 : Math.min(Math.max(parsed / 100, 0.0001), 1.0);
    onChange({ ...leg, size_pct: asDecimal });
  }

  function handleTargetTypeChange(targetType: LegTargetTypeV4): void {
    const targetValue = targetType === "feature" ? null : (leg.target_value ?? 1.0);
    onChange({ ...leg, target_type: targetType, target_value: targetValue });
  }

  function handleTargetValueChange(raw: string): void {
    const parsed = parseFloat(raw);
    onChange({ ...leg, target_value: isNaN(parsed) ? null : parsed });
  }

  const isFeatureTarget = leg.target_type === "feature";
  const canRemove = totalLegs > 1;

  return (
    <div
      className="flex flex-col gap-2 rounded-lg border border-border bg-bg-subtle p-3"
      data-testid="leg-row"
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs font-mono text-fg-subtle shrink-0 w-5">
          {index + 1}
        </span>

        {/* Kind picker */}
        <Select
          label=""
          value={leg.kind}
          onChange={(e) => handleKindChange(e.target.value as LegKindV4)}
          aria-label={`Leg ${index + 1} kind`}
          className="text-xs"
        >
          <option value="target">Target</option>
          <option value="runner">Runner</option>
        </Select>

        {/* Size % */}
        <div className="flex items-center gap-1">
          <input
            type="number"
            step="0.01"
            min="0.01"
            max="100"
            aria-label={`Leg ${index + 1} size percent`}
            value={displayPct}
            onChange={(e) => handleSizePctChange(e.target.value)}
            className="w-20 rounded border border-border-strong bg-bg-subtle px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
          />
          <span className="text-xs text-fg-subtle">%</span>
        </div>

        {/* Target type */}
        <Select
          label=""
          value={leg.target_type}
          onChange={(e) => handleTargetTypeChange(e.target.value as LegTargetTypeV4)}
          aria-label={`Leg ${index + 1} target type`}
          className="text-xs"
        >
          {(Object.keys(TARGET_TYPE_LABELS) as LegTargetTypeV4[]).map((t) => (
            <option key={t} value={t}>
              {TARGET_TYPE_LABELS[t]}
            </option>
          ))}
        </Select>

        {/* Target value — hidden when feature */}
        {isFeatureTarget ? (
          <span className="text-xs text-fg-subtle italic">
            feature target — value computed at runtime
          </span>
        ) : (
          <input
            type="number"
            step="0.01"
            aria-label={`Leg ${index + 1} target value`}
            value={leg.target_value ?? ""}
            onChange={(e) => handleTargetValueChange(e.target.value)}
            className="w-20 rounded border border-border-strong bg-bg-subtle px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
          />
        )}

        {/* Remove button */}
        <button
          type="button"
          onClick={onRemove}
          disabled={!canRemove}
          aria-label={`Remove leg ${index + 1}`}
          className="ml-auto text-fg-subtle hover:text-danger text-xs px-2 py-1 rounded transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
        >
          Remove
        </button>
      </div>

      {/* On fill action subform */}
      <OnFillActionSubform
        value={leg.on_fill_action}
        onChange={(onFill) => onChange({ ...leg, on_fill_action: onFill })}
      />
    </div>
  );
}

/**
 * OnFillActionSubform — discriminated union editor for on_fill_action.
 *
 * Kinds that require offset_value: be_plus, be_minus, tighten_atr, tighten_pct.
 * Kinds that must have offset_value=null: be_exact, leave.
 * Switching kind always normalises offset_value.
 */

import type { OnFillActionV4Draft, OnFillActionKindV4 } from "@/api/schemas/strategiesV4";
import { Select } from "@/components/ui/Select";

const KINDS_NEEDING_OFFSET = new Set<OnFillActionKindV4>([
  "be_plus",
  "be_minus",
  "tighten_atr",
  "tighten_pct",
]);

const KIND_LABELS: Record<OnFillActionKindV4, string> = {
  be_exact: "Move stop to exact fill price",
  be_plus: "Move stop to fill + offset",
  be_minus: "Move stop to fill - offset",
  tighten_atr: "Tighten stop by ATR multiple",
  tighten_pct: "Tighten stop by %",
  leave: "Leave stop unchanged",
};

export interface OnFillActionSubformProps {
  value: OnFillActionV4Draft;
  onChange: (value: OnFillActionV4Draft) => void;
}

export function OnFillActionSubform({ value, onChange }: OnFillActionSubformProps): JSX.Element {
  function handleKindChange(newKind: OnFillActionKindV4): void {
    const needsOffset = KINDS_NEEDING_OFFSET.has(newKind);
    onChange({
      kind: newKind,
      offset_value: needsOffset ? (value.offset_value ?? 0.0) : null,
    });
  }

  function handleOffsetChange(raw: string): void {
    const parsed = parseFloat(raw);
    onChange({ ...value, offset_value: isNaN(parsed) ? 0.0 : parsed });
  }

  const showOffset = KINDS_NEEDING_OFFSET.has(value.kind);

  return (
    <div className="flex items-center gap-2 flex-wrap">
      <span className="text-[11px] text-fg-subtle shrink-0">On fill:</span>
      <Select
        label=""
        value={value.kind}
        onChange={(e) => handleKindChange(e.target.value as OnFillActionKindV4)}
        aria-label="On fill action kind"
        className="text-xs"
      >
        {(Object.keys(KIND_LABELS) as OnFillActionKindV4[]).map((k) => (
          <option key={k} value={k}>
            {KIND_LABELS[k]}
          </option>
        ))}
      </Select>
      {showOffset ? (
        <input
          type="number"
          step="0.01"
          aria-label="Offset value"
          value={value.offset_value ?? 0}
          onChange={(e) => handleOffsetChange(e.target.value)}
          className="w-20 rounded border border-border-strong bg-bg-subtle px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
        />
      ) : null}
    </div>
  );
}

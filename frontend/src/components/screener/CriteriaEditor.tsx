import { Plus, X } from "lucide-react";
import type {
  ScreenerCriterion,
  ScreenerCriterionOperator,
  ScreenerFieldValue,
  ScreenerMetric,
  ScreenerFieldDefinition,
} from "@/api/schemas/screener";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { metricLabel } from "./criterionFormat";

/**
 * CriteriaEditor — pill-row editor for ScreenerCriterion list.
 *
 * Layout per row: [Metric ▾] [Operator ▾] [Value] [Value max if BETWEEN] [✕]
 *
 * The metric vocabulary is fed by GET /api/v1/screeners/metrics so the
 * options always match what the backend service can compute. Operators
 * never type metric names — the picker is a select.
 */
export interface CriteriaEditorProps {
  value: ScreenerCriterion[];
  onChange: (next: ScreenerCriterion[]) => void;
  metrics: ScreenerFieldDefinition[];
  disabled?: boolean;
}

const OPERATOR_LABELS: { value: ScreenerCriterionOperator; label: string }[] = [
  { value: "gte", label: "≥" },
  { value: "gt", label: ">" },
  { value: "lte", label: "≤" },
  { value: "lt", label: "<" },
  { value: "eq", label: "=" },
  { value: "between", label: "between" },
];

export function CriteriaEditor(props: CriteriaEditorProps): JSX.Element {
  const { value, onChange, metrics, disabled } = props;

  function setRow(i: number, next: ScreenerCriterion): void {
    onChange(value.map((c, idx) => (idx === i ? next : c)));
  }
  function removeRow(i: number): void {
    onChange(value.filter((_, idx) => idx !== i));
  }
  function addRow(): void {
    const defaultMetric: ScreenerMetric =
      (metrics[0]?.key as ScreenerMetric | undefined) ?? "price";
    onChange([
      ...value,
      { metric: defaultMetric, operator: "gte", value: 0, value_max: null, label: null },
    ]);
  }

  return (
    <div className="space-y-2 rounded border border-border bg-bg-inset/40 p-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
          Criteria · {value.length} {value.length === 1 ? "rule" : "rules"}
        </span>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          leftIcon={<Plus className="h-3 w-3" aria-hidden="true" />}
          onClick={addRow}
        >
          Add criterion
        </Button>
      </div>
      {value.length === 0 ? (
        <div className="rounded border border-dashed border-border px-3 py-2 text-[11px] text-fg-muted">
          No criteria — Screener will return every symbol in the universe with its
          metrics computed. Add a criterion to filter.
        </div>
      ) : (
        <div className="space-y-1.5">
          {value.map((row, i) => (
            <CriterionRow
              key={i}
              row={row}
              metrics={metrics}
              onChange={(next) => setRow(i, next)}
              onDelete={() => removeRow(i)}
              disabled={disabled}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CriterionRow({
  row,
  metrics,
  onChange,
  onDelete,
  disabled,
}: {
  row: ScreenerCriterion;
  metrics: ScreenerFieldDefinition[];
  onChange: (next: ScreenerCriterion) => void;
  onDelete: () => void;
  disabled?: boolean;
}): JSX.Element {
  const isBetween = row.operator === "between";
  const field = metrics.find((m) => m.key === row.metric);
  const unit = field?.unit ?? "";
  const operators = field?.supported_operators?.length
    ? field.supported_operators
    : OPERATOR_LABELS.map((o) => o.value);

  function setMetric(metric: ScreenerMetric): void {
    const nextField = metrics.find((m) => m.key === metric);
    const nextOperator = (nextField?.supported_operators?.[0] as ScreenerCriterionOperator | undefined) ?? "gte";
    const nextValue =
      nextField?.value_type === "boolean" ? true : nextField?.value_type === "string" ? "" : 0;
    onChange({ ...row, metric, operator: nextOperator, value: nextValue, value_max: null });
  }
  function setOperator(operator: ScreenerCriterionOperator): void {
    if (operator === "between" && (row.value_max == null)) {
      const current = Number(row.value);
      onChange({ ...row, operator, value_max: Number.isFinite(current) ? current : null });
      return;
    }
    onChange({ ...row, operator, value_max: operator === "between" ? row.value_max : null });
  }
  function setValue(v: ScreenerFieldValue): void {
    if (field?.value_type === "number") {
      const num = Number(v);
      onChange({ ...row, value: Number.isFinite(num) ? num : 0 });
      return;
    }
    onChange({ ...row, value: v });
  }
  function setValueMax(v: string): void {
    if (v === "") {
      onChange({ ...row, value_max: null });
      return;
    }
    const num = Number(v);
    onChange({ ...row, value_max: Number.isFinite(num) ? num : null });
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded border border-border/60 bg-bg-raised px-2 py-1">
      <select
        disabled={disabled}
        value={row.metric}
        onChange={(e) => setMetric(e.target.value as ScreenerMetric)}
        className="rounded border border-border bg-bg-inset px-1.5 py-0.5 text-[11px] focus:border-accent focus:outline-none"
      >
        {metrics.map((m) => (
          <option key={m.key} value={m.key}>
            {metricLabel(m.key, m)}
          </option>
        ))}
      </select>
      <select
        disabled={disabled}
        value={row.operator}
        onChange={(e) => setOperator(e.target.value as ScreenerCriterionOperator)}
        className="rounded border border-border bg-bg-inset px-1.5 py-0.5 text-[11px] focus:border-accent focus:outline-none"
      >
        {OPERATOR_LABELS.filter((o) => operators.includes(o.value)).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      {field?.value_type === "boolean" ? (
        <select
          disabled={disabled}
          value={String(row.value)}
          onChange={(e) => setValue(e.target.value === "true")}
          className="rounded border border-border bg-bg-inset px-1.5 py-0.5 text-[11px] focus:border-accent focus:outline-none"
        >
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      ) : field?.value_type === "string" ? (
        <input
          type="text"
          value={String(row.value ?? "")}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          className="w-32 rounded border border-border bg-bg-inset px-1.5 py-0.5 text-[11px] focus:border-accent focus:outline-none"
          placeholder="NASDAQ"
        />
      ) : (
        <input
          type="number"
          step="any"
          inputMode="decimal"
          value={Number(row.value)}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          className="w-24 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-[11px] focus:border-accent focus:outline-none"
        />
      )}
      {isBetween ? (
        <>
          <span className="text-[11px] text-fg-muted">and</span>
          <input
            type="number"
            step="any"
            inputMode="decimal"
            value={row.value_max ?? ""}
            disabled={disabled}
            onChange={(e) => setValueMax(e.target.value)}
            className="w-24 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-[11px] focus:border-accent focus:outline-none"
          />
        </>
      ) : null}
      <span className="text-[10.5px] text-fg-subtle">{unit}</span>
      <button
        type="button"
        disabled={disabled}
        onClick={onDelete}
        className={cn(
          "ml-auto rounded p-1 text-fg-subtle hover:bg-bg-subtle hover:text-danger",
          disabled && "cursor-not-allowed",
        )}
        aria-label="Remove criterion"
      >
        <X className="h-3 w-3" aria-hidden="true" />
      </button>
    </div>
  );
}

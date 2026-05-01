/**
 * StopRow — single stop row in the Stops section.
 *
 * Mode toggle: simple | expression.
 * Switching mode clears the other side's fields.
 */

import type {
  StrategyStopV4Draft,
  StopModeV4,
  StopSimpleTypeV4,
} from "@/api/schemas/strategiesV4";
import { MonacoExpressionEditor } from "./MonacoExpressionEditor";
import type { ExpressionValidateResult } from "./MonacoExpressionEditor";
import { Select } from "@/components/ui/Select";

const SIMPLE_TYPE_LABELS: Record<StopSimpleTypeV4, string> = {
  "%": "% of price",
  ATR: "ATR multiple",
  $: "Dollar amount",
  R: "R multiple",
};

export interface StopRowProps {
  stop: StrategyStopV4Draft;
  legCount: number;
  onChange: (stop: StrategyStopV4Draft) => void;
  onRemove: () => void;
  variableNames?: string[];
  timeframeVariableNames?: string[];
}

export function StopRow({
  stop,
  legCount,
  onChange,
  onRemove,
  variableNames,
  timeframeVariableNames = [],
}: StopRowProps): JSX.Element {
  function handleModeChange(newMode: StopModeV4): void {
    if (newMode === "simple") {
      onChange({
        ...stop,
        mode: "simple",
        simple_type: stop.simple_type ?? "%",
        simple_value: stop.simple_value ?? 1.0,
        expression_text: null,
        feature_requirements: [],
      });
    } else {
      onChange({
        ...stop,
        mode: "expression",
        simple_type: null,
        simple_value: null,
        expression_text: stop.expression_text ?? "",
        feature_requirements: [],
      });
    }
  }

  function handleScopeChange(scope: string): void {
    onChange({ ...stop, scope });
  }

  function handleSimpleTypeChange(type: StopSimpleTypeV4): void {
    onChange({ ...stop, simple_type: type });
  }

  function handleSimpleValueChange(raw: string): void {
    const parsed = parseFloat(raw);
    onChange({ ...stop, simple_value: isNaN(parsed) ? 0 : parsed });
  }

  function handleExpressionChange(text: string): void {
    onChange({ ...stop, expression_text: text });
  }

  function handleValidationChange(result: ExpressionValidateResult): void {
    const reqs = result.feature_requirements.map((f) => f.key);
    onChange({ ...stop, feature_requirements: reqs.length > 0 ? reqs : undefined });
  }

  // Build scope options
  const scopeOptions: string[] = ["all"];
  for (let i = 1; i <= legCount; i++) {
    scopeOptions.push(`leg-${i}`);
  }

  return (
    <div
      className="flex flex-col gap-2 rounded-lg border border-border bg-bg-subtle p-3"
      data-testid="stop-row"
    >
      <div className="flex items-center gap-2 flex-wrap">
        {/* Mode toggle */}
        <div className="flex rounded overflow-hidden border border-border-strong shrink-0">
          <button
            type="button"
            onClick={() => handleModeChange("simple")}
            aria-pressed={stop.mode === "simple"}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              stop.mode === "simple"
                ? "bg-accent text-bg"
                : "bg-bg-subtle text-fg-muted hover:text-fg"
            }`}
          >
            Simple
          </button>
          <button
            type="button"
            onClick={() => handleModeChange("expression")}
            aria-pressed={stop.mode === "expression"}
            className={`px-3 py-1 text-xs font-medium transition-colors ${
              stop.mode === "expression"
                ? "bg-accent text-bg"
                : "bg-bg-subtle text-fg-muted hover:text-fg"
            }`}
          >
            Expression
          </button>
        </div>

        {/* Scope picker */}
        <Select
          label=""
          value={stop.scope ?? "all"}
          onChange={(e) => handleScopeChange(e.target.value)}
          aria-label="Stop scope"
          className="text-xs"
        >
          {scopeOptions.map((s) => (
            <option key={s} value={s}>
              {s === "all" ? "All legs" : `Leg ${s.replace("leg-", "")}`}
            </option>
          ))}
        </Select>

        {/* Simple mode fields */}
        {stop.mode === "simple" ? (
          <>
            <Select
              label=""
              value={stop.simple_type ?? "%"}
              onChange={(e) => handleSimpleTypeChange(e.target.value as StopSimpleTypeV4)}
              aria-label="Stop type"
              className="text-xs"
            >
              {(Object.keys(SIMPLE_TYPE_LABELS) as StopSimpleTypeV4[]).map((t) => (
                <option key={t} value={t}>
                  {SIMPLE_TYPE_LABELS[t]}
                </option>
              ))}
            </Select>
            <input
              type="number"
              step="0.01"
              min="0"
              aria-label="Stop value"
              value={stop.simple_value ?? ""}
              onChange={(e) => handleSimpleValueChange(e.target.value)}
              className="w-20 rounded border border-border-strong bg-bg-subtle px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
            />
          </>
        ) : null}

        {/* Remove button */}
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove stop"
          className="ml-auto text-fg-subtle hover:text-danger text-xs px-2 py-1 rounded transition-colors"
        >
          Remove
        </button>
      </div>

      {/* Expression mode editor */}
      {stop.mode === "expression" ? (
        <div className="h-24 rounded overflow-hidden border border-border">
          <MonacoExpressionEditor
            value={stop.expression_text ?? ""}
            onChange={handleExpressionChange}
            variableNames={variableNames}
            timeframeVariableNames={timeframeVariableNames}
            onValidationChange={handleValidationChange}
            height="96px"
          />
        </div>
      ) : null}
    </div>
  );
}

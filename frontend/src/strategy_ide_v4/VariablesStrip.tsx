/**
 * VariablesStrip — chip-row listing current variables with inline edit popover.
 */

import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import * as Popover from "@radix-ui/react-popover";
import { MonacoExpressionEditor } from "./MonacoExpressionEditor";
import type {
  StrategyVariableV4Draft,
  VariableKindV4,
} from "@/api/schemas/strategiesV4";
import { validateExpressionAbortable } from "@/api/strategiesV4";
import { Button } from "@/components/ui/Button";
import { CANONICAL_TIMEFRAMES } from "./canonicalTimeframes";

export interface VariablesStripProps {
  variables: StrategyVariableV4Draft[];
  onChange: (variables: StrategyVariableV4Draft[]) => void;
}

const VALID_NAME_RE = /^[a-z_][a-z0-9_]*$/;

function expressionNamesBefore(
  vars: StrategyVariableV4Draft[],
  beforeIndex: number,
): string[] {
  return vars
    .slice(0, beforeIndex)
    .filter((v) => (v.kind ?? "expression") === "expression")
    .map((v) => v.name);
}

function timeframeNamesBefore(vars: StrategyVariableV4Draft[], beforeIndex: number): string[] {
  return vars
    .slice(0, beforeIndex)
    .filter((v) => v.kind === "timeframe")
    .map((v) => v.name);
}

interface VariablePopoverFormProps {
  /** Names already taken by sibling variables (excludes row being edited) */
  otherUsedNames: string[];
  precedingExpr: string[];
  precedingTf: string[];
  initial: StrategyVariableV4Draft | null;
  onSave: (v: StrategyVariableV4Draft) => void;
  onCancel: () => void;
}

function VariablePopoverForm({
  otherUsedNames,
  precedingExpr,
  precedingTf,
  initial,
  onSave,
  onCancel,
}: VariablePopoverFormProps): JSX.Element {
  const initialKind = (initial?.kind ?? "expression") as VariableKindV4;
  const [name, setName] = useState(initial?.name ?? "");
  const [kind, setKind] = useState<VariableKindV4>(initialKind);
  const [expr, setExpr] = useState(initial?.expression_text ?? "");
  const [nameError, setNameError] = useState<string | null>(null);
  const [exprError, setExprError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  function validateName(val: string): string | null {
    if (!val.trim()) return "Name is required";
    if (!VALID_NAME_RE.test(val)) return "Must be lowercase snake_case (a-z, 0-9, _)";
    if (otherUsedNames.includes(val)) return "Name already in use";
    return null;
  }

  async function handleSave(): Promise<void> {
    const nErr = validateName(name.trim());
    if (nErr) {
      setNameError(nErr);
      return;
    }

    const trimmedName = name.trim();

    if (kind === "timeframe") {
      const tf = expr.trim();
      if (!CANONICAL_TIMEFRAMES.includes(tf as (typeof CANONICAL_TIMEFRAMES)[number])) {
        setExprError(`Choose a timeframe: ${CANONICAL_TIMEFRAMES.join(", ")}`);
        return;
      }
      setSaving(false);
      onSave({ name: trimmedName, expression_text: tf, kind: "timeframe" });
      return;
    }

    setSaving(true);
    try {
      const ctrl = new AbortController();
      const result = await validateExpressionAbortable(
        expr,
        precedingExpr,
        precedingTf,
        ctrl.signal,
      );
      if (!result.valid) {
        setExprError(result.errors[0]?.message ?? "Invalid expression");
        setSaving(false);
        return;
      }
    } catch {
      // Allow save even if validation request fails
    }
    setSaving(false);
    onSave({ name: trimmedName, expression_text: expr, kind: "expression" });
  }

  const canSaveExpression = name.trim() && expr.trim();
  const canSaveTimeframe = name.trim() && expr.trim() && kind === "timeframe";
  const canSave =
    kind === "timeframe" ? Boolean(canSaveTimeframe) : Boolean(canSaveExpression);

  return (
    <div className="flex flex-col gap-3 p-4 w-[480px]">
      <div>
        <label className="block text-xs font-medium text-fg-muted mb-1" htmlFor="var-name">
          Variable name
        </label>
        <input
          id="var-name"
          type="text"
          className="w-full rounded border border-border bg-bg-subtle px-2 py-1.5 text-sm text-fg focus:outline-none focus:border-accent"
          value={name}
          onChange={(e) => {
            setName(e.target.value);
            setNameError(null);
          }}
          placeholder="my_variable"
          autoFocus
          aria-describedby={nameError ? "var-name-error" : undefined}
        />
        {nameError ? (
          <p id="var-name-error" className="mt-1 text-xs text-danger">
            {nameError}
          </p>
        ) : null}
      </div>

      <div>
        <span className="block text-xs font-medium text-fg-muted mb-1">Kind</span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => {
              setKind("expression");
              setExprError(null);
            }}
            aria-pressed={kind === "expression"}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors border ${
              kind === "expression"
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-fg-muted hover:text-fg"
            }`}
          >
            Expression
          </button>
          <button
            type="button"
            onClick={() => {
              setKind("timeframe");
              const t = expr.trim();
              const next =
                CANONICAL_TIMEFRAMES.includes(t as (typeof CANONICAL_TIMEFRAMES)[number])
                  ? t
                  : (initial?.expression_text ?? "5m").trim();
              setExpr(
                CANONICAL_TIMEFRAMES.includes(next as (typeof CANONICAL_TIMEFRAMES)[number])
                  ? next
                  : "5m",
              );
              setExprError(null);
            }}
            aria-pressed={kind === "timeframe"}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors border ${
              kind === "timeframe"
                ? "border-accent bg-accent/10 text-accent"
                : "border-border text-fg-muted hover:text-fg"
            }`}
          >
            Timeframe
          </button>
        </div>
      </div>

      {kind === "timeframe" ? (
        <div>
          <label className="block text-xs font-medium text-fg-muted mb-1" htmlFor="var-tf">
            Timeframe value
          </label>
          <select
            id="var-tf"
            className="w-full rounded border border-border bg-bg-subtle px-2 py-1.5 text-sm text-fg focus:outline-none focus:border-accent"
            value={CANONICAL_TIMEFRAMES.includes(expr as never) ? expr : CANONICAL_TIMEFRAMES[0]}
            onChange={(e) => {
              setExpr(e.target.value);
              setExprError(null);
            }}
            aria-label="Timeframe"
          >
            {CANONICAL_TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-fg-subtle">
            Use like <span className="font-mono">{`{name}.ema(9)`}</span> in entry / stop /
            optimizer bindings.
          </p>
          {exprError ? (
            <p className="mt-1 text-xs text-danger">{exprError}</p>
          ) : null}
        </div>
      ) : (
        <div>
          <label className="block text-xs font-medium text-fg-muted mb-1">Expression</label>
          <div className="rounded border border-border overflow-hidden bg-bg-inset">
            <MonacoExpressionEditor
              value={expr}
              onChange={(v) => {
                setExpr(v);
                setExprError(null);
              }}
              variableNames={precedingExpr}
              timeframeVariableNames={precedingTf}
              height="120px"
              width="100%"
            />
          </div>
          {exprError ? (
            <p className="mt-1 text-xs text-danger">{exprError}</p>
          ) : null}
        </div>
      )}

      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="sm"
          variant="primary"
          loading={saving}
          onClick={() => void handleSave()}
          disabled={!canSave}
        >
          Save
        </Button>
      </div>
    </div>
  );
}

function VariableChip({
  variable,
  chipIndex,
  variables,
  onEdit,
  onDelete,
}: {
  variable: StrategyVariableV4Draft;
  chipIndex: number;
  variables: StrategyVariableV4Draft[];
  onEdit: (v: StrategyVariableV4Draft) => void;
  onDelete: () => void;
}): JSX.Element {
  const [open, setOpen] = useState(false);
  // RHS only — chip already renders name + TF badge to avoid repeating "short = short[Tf]=..."
  const rhsValue =
    variable.kind === "timeframe"
      ? variable.expression_text.trim()
      : variable.expression_text;
  const truncated =
    rhsValue.length > 32 ? `${rhsValue.slice(0, 32)}…` : rhsValue;

  const otherNamesUsed = variables
    .filter((_, i) => i !== chipIndex)
    .map((v) => v.name);

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <div className="flex items-center gap-0.5 rounded-full border border-border bg-bg-raised px-2 py-0.5 text-xs">
        <Popover.Trigger asChild>
          <button
            className="flex items-center gap-1 text-ai hover:text-ai/80 focus:outline-none"
            aria-label={`Edit variable ${variable.name}`}
          >
            <span className="font-mono font-semibold">{variable.name}</span>
            {variable.kind === "timeframe" ? (
              <span className="rounded bg-accent/15 px-1 text-[10px] font-semibold text-accent uppercase">
                tf
              </span>
            ) : null}
            <span className="text-fg-subtle"> = </span>
            <span className="font-mono text-fg-muted">{truncated}</span>
          </button>
        </Popover.Trigger>
        <button
          className="ml-1 text-fg-subtle hover:text-danger focus:outline-none"
          onClick={onDelete}
          aria-label={`Delete variable ${variable.name}`}
        >
          <Trash2 className="h-3 w-3" aria-hidden="true" />
        </button>
      </div>
      <Popover.Portal>
        <Popover.Content
          className="z-50 rounded-xl border border-border bg-bg-raised shadow-xl"
          sideOffset={8}
          align="start"
        >
          <VariablePopoverForm
            otherUsedNames={otherNamesUsed}
            precedingExpr={expressionNamesBefore(variables, chipIndex)}
            precedingTf={timeframeNamesBefore(variables, chipIndex)}
            initial={variable}
            onSave={(updated) => {
              setOpen(false);
              onEdit(updated);
            }}
            onCancel={() => setOpen(false)}
          />
          <Popover.Arrow className="fill-border" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

export function VariablesStrip({ variables, onChange }: VariablesStripProps): JSX.Element {
  const [addOpen, setAddOpen] = useState(false);

  function handleDelete(index: number): void {
    onChange(variables.filter((_, i) => i !== index));
  }

  function handleEdit(index: number, updated: StrategyVariableV4Draft): void {
    const next = [...variables];
    next[index] = updated;
    onChange(next);
  }

  function handleAdd(v: StrategyVariableV4Draft): void {
    setAddOpen(false);
    onChange([...variables, v]);
  }

  const addOtherNamesUsed = variables.map((v) => v.name);

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-t border-b border-border bg-bg-subtle px-3 py-1.5 min-h-[36px]">
      <span className="text-xs text-fg-subtle font-medium mr-1">Vars:</span>
      {variables.map((v, i) => (
        <VariableChip
          key={`${v.name}-${i}`}
          chipIndex={i}
          variables={variables}
          variable={v}
          onEdit={(updated) => handleEdit(i, updated)}
          onDelete={() => handleDelete(i)}
        />
      ))}
      <Popover.Root open={addOpen} onOpenChange={setAddOpen}>
        <Popover.Trigger asChild>
          <button
            className="flex items-center gap-1 rounded-full border border-dashed border-border-strong px-2 py-0.5 text-xs text-accent hover:border-accent focus:outline-none"
            aria-label="Add variable"
          >
            <Plus className="h-3 w-3" aria-hidden="true" />
            Add variable
          </button>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Content
            className="z-50 rounded-xl border border-border bg-bg-raised shadow-xl"
            sideOffset={8}
            align="start"
          >
            <VariablePopoverForm
              otherUsedNames={addOtherNamesUsed}
              precedingExpr={expressionNamesBefore(variables, variables.length)}
              precedingTf={timeframeNamesBefore(variables, variables.length)}
              initial={null}
              onSave={handleAdd}
              onCancel={() => setAddOpen(false)}
            />
            <Popover.Arrow className="fill-border" />
          </Popover.Content>
        </Popover.Portal>
      </Popover.Root>
    </div>
  );
}

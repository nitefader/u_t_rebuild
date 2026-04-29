import { Plus, X } from "lucide-react";
import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { FeatureRefField } from "./FeatureRefField";
import {
  CONDITION_OPERATORS,
  type ConditionExpression,
  type ConditionGroup,
  type ConditionNode,
  appendChild,
  asGroup,
  emptyCondition,
  emptyGroup,
  removeAt,
} from "./conditionUtils";

/**
 * ConditionPillBuilder — recursive visual builder for entry/exit
 * condition trees, modeled on the v2 mockup's pill-row UX.
 *
 * Top-level is always a `group` so the editor can render the AND/ANY
 * label consistently. Child positions are addressed by `path` (an
 * index trail through nested groups). Each leaf condition pill row
 * has [feature_ref ▾] [operator ▾] [feature_ref ▾ | value] [✕].
 *
 * Right-hand side is feature OR scalar value: operator picks via the
 * tab strip on each row (`feature` vs `value`). When `feature` is
 * selected `right_value` is null in the payload; when `value` is
 * selected `right_feature` is null. This mirrors the backend's
 * `ConditionNode` schema (right_feature OR right_value).
 *
 * Validation is rendered in `invalidFeatureRefs` — rows whose
 * left/right feature isn't in that set get a danger border.
 */
export interface ConditionPillBuilderProps {
  value: ConditionExpression | null | undefined;
  onChange: (next: ConditionExpression) => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs?: Set<string>;
  disabled?: boolean;
  consumer?: string;
  /** Hide the outer "Condition tree" framing (used inside other panels). */
  embedded?: boolean;
}

export function ConditionPillBuilder(props: ConditionPillBuilderProps): JSX.Element {
  const root = asGroup(props.value);

  function setRoot(next: ConditionGroup): void {
    // Keep the editor honest: always a group at the top. Downstream callers
    // can compactGroup() before serializing if they want a single-leaf form.
    props.onChange(next);
  }

  return (
    <div className={cn(props.embedded ? "" : "rounded border border-border bg-bg-inset/40 p-2")}>
      <GroupRows
        group={root}
        path={[]}
        onChange={(next) => setRoot(next)}
        catalog={props.catalog}
        invalidFeatureRefs={props.invalidFeatureRefs}
        disabled={props.disabled}
        consumer={props.consumer}
      />
    </div>
  );
}

interface GroupRowsProps {
  group: ConditionGroup;
  path: number[];
  onChange: (next: ConditionGroup) => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs?: Set<string>;
  disabled?: boolean;
  consumer?: string;
}

function GroupRows({
  group,
  onChange,
  catalog,
  invalidFeatureRefs,
  disabled,
  consumer,
}: GroupRowsProps): JSX.Element {
  function setOperator(op: "all" | "any"): void {
    onChange({ ...group, operator: op });
  }

  function setChild(index: number, next: ConditionExpression): void {
    onChange({
      ...group,
      children: group.children.map((c, i) => (i === index ? next : c)),
    });
  }

  function removeChild(index: number): void {
    const next = removeAt(group, [index]);
    onChange(next);
  }

  function addCondition(): void {
    onChange(appendChild(group, [], emptyCondition()));
  }

  function addOrGroup(): void {
    onChange(appendChild(group, [], emptyGroup("any")));
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
          {group.operator === "any" || group.operator === "or" ? "Match ANY of" : "Match ALL of"}
        </span>
        <div className="inline-flex overflow-hidden rounded border border-border text-[10px]">
          <button
            type="button"
            disabled={disabled}
            onClick={() => setOperator("all")}
            className={cn(
              "px-1.5 py-0.5",
              (group.operator === "all" || group.operator === "and")
                ? "bg-accent/20 text-accent"
                : "text-fg-muted hover:text-fg",
            )}
          >
            ALL (AND)
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() => setOperator("any")}
            className={cn(
              "px-1.5 py-0.5 border-l border-border",
              (group.operator === "any" || group.operator === "or")
                ? "bg-accent/20 text-accent"
                : "text-fg-muted hover:text-fg",
            )}
          >
            ANY (OR)
          </button>
        </div>
      </div>

      {group.children.map((child, index) => (
        <div key={index} className="flex items-start gap-2">
          {child.kind === "condition" ? (
            <ConditionRow
              node={child}
              onChange={(next) => setChild(index, next)}
              onDelete={() => removeChild(index)}
              catalog={catalog}
              invalidFeatureRefs={invalidFeatureRefs}
              disabled={disabled}
              consumer={consumer}
            />
          ) : (
            <div className="flex-1 rounded border border-border/70 bg-bg-subtle p-2">
              <GroupRows
                group={child}
                path={[]}
                onChange={(next) => setChild(index, next)}
                catalog={catalog}
                invalidFeatureRefs={invalidFeatureRefs}
                disabled={disabled}
                consumer={consumer}
              />
              <div className="mt-1 flex justify-end">
                <button
                  type="button"
                  disabled={disabled}
                  onClick={() => removeChild(index)}
                  className="text-[10px] text-fg-muted hover:text-danger"
                >
                  Remove group
                </button>
              </div>
            </div>
          )}
        </div>
      ))}

      <div className="flex flex-wrap gap-2 pt-0.5">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={addCondition}
          leftIcon={<Plus className="h-3 w-3" aria-hidden="true" />}
        >
          Add condition
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={addOrGroup}
          leftIcon={<Plus className="h-3 w-3" aria-hidden="true" />}
        >
          Add OR group
        </Button>
      </div>
    </div>
  );
}

interface ConditionRowProps {
  node: ConditionNode;
  onChange: (next: ConditionNode) => void;
  onDelete: () => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs?: Set<string>;
  disabled?: boolean;
  consumer?: string;
}

function ConditionRow({
  node,
  onChange,
  onDelete,
  catalog,
  invalidFeatureRefs,
  disabled,
  consumer,
}: ConditionRowProps): JSX.Element {
  const rightMode: "feature" | "value" = node.right_value !== null && node.right_value !== undefined && node.right_value !== ""
    ? "value"
    : "feature";

  function setLeft(v: string): void {
    onChange({ ...node, left_feature: v });
  }
  function setOperator(v: string): void {
    onChange({ ...node, operator: v as ConditionNode["operator"] });
  }
  function setRightFeature(v: string): void {
    onChange({ ...node, right_feature: v, right_value: null });
  }
  function setRightValue(v: string): void {
    const num = Number(v);
    onChange({
      ...node,
      right_feature: null,
      right_value: v === "" ? null : Number.isFinite(num) ? num : v,
    });
  }
  function switchRightMode(mode: "feature" | "value"): void {
    if (mode === "feature") onChange({ ...node, right_feature: node.right_feature ?? "", right_value: null });
    else onChange({ ...node, right_feature: null, right_value: typeof node.right_value === "number" ? node.right_value : 0 });
  }

  return (
    <div className="flex flex-1 flex-wrap items-center gap-1.5 rounded border border-border/60 bg-bg-raised px-2 py-1">
      <FeatureRefField
        value={node.left_feature}
        onChange={setLeft}
        catalog={catalog}
        consumer={consumer}
        invalid={node.left_feature !== "" && invalidFeatureRefs?.has(node.left_feature)}
        disabled={disabled}
        placeholder="left feature"
      />
      <select
        disabled={disabled}
        value={node.operator}
        onChange={(e) => setOperator(e.target.value)}
        className="rounded border border-border bg-bg-inset px-1.5 py-0.5 text-[11px] focus:border-accent focus:outline-none"
      >
        {CONDITION_OPERATORS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>

      <div className="inline-flex overflow-hidden rounded border border-border text-[10px]">
        <button
          type="button"
          disabled={disabled}
          onClick={() => switchRightMode("feature")}
          className={cn(
            "px-1.5 py-0.5",
            rightMode === "feature" ? "bg-accent/20 text-accent" : "text-fg-muted hover:text-fg",
          )}
        >
          feature
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => switchRightMode("value")}
          className={cn(
            "px-1.5 py-0.5 border-l border-border",
            rightMode === "value" ? "bg-accent/20 text-accent" : "text-fg-muted hover:text-fg",
          )}
        >
          value
        </button>
      </div>

      {rightMode === "feature" ? (
        <FeatureRefField
          value={node.right_feature ?? ""}
          onChange={setRightFeature}
          catalog={catalog}
          consumer={consumer}
          invalid={!!node.right_feature && invalidFeatureRefs?.has(node.right_feature)}
          disabled={disabled}
          placeholder="right feature"
        />
      ) : (
        <input
          type="text"
          inputMode="decimal"
          disabled={disabled}
          value={node.right_value ?? ""}
          onChange={(e) => setRightValue(e.target.value)}
          className="w-20 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-[11px] focus:border-accent focus:outline-none"
          placeholder="value"
        />
      )}

      <button
        type="button"
        disabled={disabled}
        onClick={onDelete}
        className="ml-auto rounded p-1 text-fg-subtle hover:bg-bg-subtle hover:text-danger"
        aria-label="Remove condition"
      >
        <X className="h-3 w-3" aria-hidden="true" />
      </button>
    </div>
  );
}

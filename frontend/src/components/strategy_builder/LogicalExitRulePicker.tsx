import { Plus, X } from "lucide-react";
import type {
  FeatureCatalogItem,
  LogicalExitRule,
  LogicalExitRuleKind,
} from "@/api/schemas/strategyComposer";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { ConditionPillBuilder } from "./ConditionPillBuilder";
import {
  LOGICAL_EXIT_KIND_LABELS,
  LOGICAL_EXIT_KIND_SHORT,
  SESSION_WINDOW_OPTIONS,
  emptyLogicalExitRule,
  type ConditionExpression,
} from "./conditionUtils";

/**
 * LogicalExitRulePicker — typed editor for the seven LogicalExitRule kinds:
 *
 *   feature_condition · bars_since_entry · time_in_position_seconds ·
 *   time_of_day_et · minutes_before_session_close · session_window · hybrid
 *
 * Doctrine guard (per memory feedback_logical_exit_is_the_only_exit_intent):
 * every exit shape lives under `logical_exit`. There is no top-level
 * `time_exit` / `bar_exit` / `session_exit` intent — this picker switches
 * the `kind` and re-parameterizes accordingly.
 *
 * Hybrid recursively composes child rules with operator = all | any.
 */
export interface LogicalExitRulePickerProps {
  value: LogicalExitRule | null | undefined;
  onChange: (next: LogicalExitRule | null) => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs?: Set<string>;
  consumer?: string;
  disabled?: boolean;
  /** When true, "remove rule" returns null. Default false (always present). */
  removable?: boolean;
}

const KIND_ORDER: LogicalExitRuleKind[] = [
  "bars_since_entry",
  "time_in_position_seconds",
  "time_of_day_et",
  "minutes_before_session_close",
  "session_window",
  "feature_condition",
  "hybrid",
];

export function LogicalExitRulePicker(props: LogicalExitRulePickerProps): JSX.Element {
  const rule = props.value ?? emptyLogicalExitRule("bars_since_entry");

  function setKind(kind: LogicalExitRuleKind): void {
    props.onChange(emptyLogicalExitRule(kind));
  }

  return (
    <div className="space-y-2 rounded border border-border bg-bg-inset/40 p-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">Exit kind</span>
        {KIND_ORDER.map((k) => (
          <button
            key={k}
            type="button"
            disabled={props.disabled}
            onClick={() => setKind(k)}
            className={cn(
              "rounded border px-2 py-0.5 text-[11px]",
              rule.kind === k
                ? "border-accent bg-accent/20 text-accent"
                : "border-border bg-bg-raised text-fg-muted hover:text-fg",
            )}
            title={LOGICAL_EXIT_KIND_LABELS[k]}
          >
            {LOGICAL_EXIT_KIND_SHORT[k]}
          </button>
        ))}
        {props.removable ? (
          <button
            type="button"
            disabled={props.disabled}
            onClick={() => props.onChange(null)}
            className="ml-auto rounded p-1 text-fg-subtle hover:bg-bg-subtle hover:text-danger"
            aria-label="Remove logical exit rule"
          >
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        ) : null}
      </div>

      <KindBody
        rule={rule}
        onChange={props.onChange}
        catalog={props.catalog}
        invalidFeatureRefs={props.invalidFeatureRefs}
        disabled={props.disabled}
        consumer={props.consumer}
      />
    </div>
  );
}

interface KindBodyProps {
  rule: LogicalExitRule;
  onChange: (next: LogicalExitRule) => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs?: Set<string>;
  consumer?: string;
  disabled?: boolean;
}

function KindBody({ rule, onChange, catalog, invalidFeatureRefs, disabled, consumer }: KindBodyProps): JSX.Element {
  const kind = rule.kind;

  if (kind === "bars_since_entry") {
    return (
      <NumericRow
        label="Exit after N bars in position"
        suffix="bars"
        value={rule.bars}
        onChange={(n) => onChange({ ...rule, bars: n })}
        disabled={disabled}
        min={1}
      />
    );
  }
  if (kind === "time_in_position_seconds") {
    const minutes = (rule.seconds ?? 0) / 60;
    return (
      <NumericRow
        label="Exit after N minutes in position"
        suffix="minutes"
        value={Number.isFinite(minutes) ? minutes : 0}
        onChange={(n) => onChange({ ...rule, seconds: Math.max(0, Math.round(n * 60)) })}
        disabled={disabled}
        min={1}
      />
    );
  }
  if (kind === "time_of_day_et") {
    return (
      <div className="flex items-center gap-2">
        <label className="text-[10px] uppercase tracking-wide text-fg-muted">Exit at (ET)</label>
        <input
          type="number"
          min={0}
          max={23}
          value={rule.hour ?? 0}
          disabled={disabled}
          onChange={(e) => onChange({ ...rule, hour: clampInt(e.target.value, 0, 23) })}
          className="w-14 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-xs focus:border-accent focus:outline-none"
        />
        <span className="text-fg-muted">:</span>
        <input
          type="number"
          min={0}
          max={59}
          value={rule.minute ?? 0}
          disabled={disabled}
          onChange={(e) => onChange({ ...rule, minute: clampInt(e.target.value, 0, 59) })}
          className="w-14 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-xs focus:border-accent focus:outline-none"
        />
        <span className="text-[11px] text-fg-subtle">America/New_York</span>
      </div>
    );
  }
  if (kind === "minutes_before_session_close") {
    return (
      <NumericRow
        label="Exit N minutes before regular session close"
        suffix="min before close"
        value={rule.minutes_before_close}
        onChange={(n) => onChange({ ...rule, minutes_before_close: n })}
        disabled={disabled}
        min={1}
      />
    );
  }
  if (kind === "session_window") {
    return (
      <div className="flex items-center gap-2">
        <label className="text-[10px] uppercase tracking-wide text-fg-muted">Exit during</label>
        <select
          disabled={disabled}
          value={rule.session ?? "regular"}
          onChange={(e) => onChange({ ...rule, session: e.target.value })}
          className="rounded border border-border bg-bg-inset px-1.5 py-0.5 text-xs focus:border-accent focus:outline-none"
        >
          {SESSION_WINDOW_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
    );
  }
  if (kind === "feature_condition") {
    return (
      <ConditionPillBuilder
        value={(rule.feature_condition as ConditionExpression | undefined) ?? null}
        onChange={(next) => onChange({ ...rule, feature_condition: next })}
        catalog={catalog}
        invalidFeatureRefs={invalidFeatureRefs}
        disabled={disabled}
        consumer={consumer}
        embedded
      />
    );
  }
  if (kind === "hybrid") {
    const operator: "all" | "any" = rule.operator === "any" ? "any" : "all";
    const children = (rule.children ?? []) as LogicalExitRule[];
    function setOperator(op: "all" | "any"): void {
      onChange({ ...rule, operator: op });
    }
    function setChild(index: number, child: LogicalExitRule | null): void {
      const next = children.slice();
      if (child === null) next.splice(index, 1);
      else next[index] = child;
      onChange({ ...rule, children: next });
    }
    function addChild(): void {
      onChange({ ...rule, children: [...children, emptyLogicalExitRule("bars_since_entry")] });
    }
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">Exit when</span>
          <div className="inline-flex overflow-hidden rounded border border-border text-[10px]">
            <button
              type="button"
              disabled={disabled}
              onClick={() => setOperator("all")}
              className={cn(
                "px-1.5 py-0.5",
                operator === "all" ? "bg-accent/20 text-accent" : "text-fg-muted hover:text-fg",
              )}
            >
              ALL of these
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => setOperator("any")}
              className={cn(
                "px-1.5 py-0.5 border-l border-border",
                operator === "any" ? "bg-accent/20 text-accent" : "text-fg-muted hover:text-fg",
              )}
            >
              ANY of these
            </button>
          </div>
        </div>
        {children.map((c, i) => (
          <div key={i}>
            <LogicalExitRulePicker
              value={c}
              onChange={(next) => setChild(i, next)}
              catalog={catalog}
              invalidFeatureRefs={invalidFeatureRefs}
              disabled={disabled}
              consumer={consumer}
              removable
            />
          </div>
        ))}
        <Button
          type="button"
          size="sm"
          variant="ghost"
          disabled={disabled}
          onClick={addChild}
          leftIcon={<Plus className="h-3 w-3" aria-hidden="true" />}
        >
          Add child rule
        </Button>
      </div>
    );
  }
  return <div className="text-xs text-fg-muted">Unknown kind {String(kind)}</div>;
}

function NumericRow({
  label,
  suffix,
  value,
  onChange,
  disabled,
  min,
}: {
  label: string;
  suffix: string;
  value: number | null | undefined;
  onChange: (n: number) => void;
  disabled?: boolean;
  min?: number;
}): JSX.Element {
  return (
    <div className="flex items-center gap-2">
      <label className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</label>
      <input
        type="number"
        min={min}
        value={value ?? 0}
        disabled={disabled}
        onChange={(e) => {
          const n = Number(e.target.value);
          onChange(Number.isFinite(n) ? n : 0);
        }}
        className="w-20 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-xs focus:border-accent focus:outline-none"
      />
      <span className="text-[11px] text-fg-subtle">{suffix}</span>
    </div>
  );
}

function clampInt(raw: string, min: number, max: number): number {
  const n = Math.round(Number(raw));
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}

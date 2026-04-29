import { useMemo } from "react";
import { Plus } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { StrategyComposerApi } from "@/api/strategyComposer";
import type {
  FeatureCatalogItem,
  FeaturePlanPreview,
  FeatureReferenceValidation,
} from "@/api/schemas/strategyComposer";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { FeaturePicker } from "./FeaturePicker";
import { SignalRuleEditor, type EditorRule } from "./SignalRuleEditor";
import { asGroup, compactGroup, emptyCondition, type ConditionExpression } from "./conditionUtils";

/**
 * BuilderPane — typed entry/exit rule editor used by the full-page
 * StrategyBuilder route and the AI Composer's edit-before-save pane.
 *
 * Composes:
 *   - Identity row (display name + tags + description)
 *   - Feature-plan strip backed by the catalog-driven FeaturePicker
 *   - Entry rules list (SignalRuleEditor with intent_type=entry)
 *   - Exit rules list (SignalRuleEditor with intent_type=exit; LogicalExitRule
 *     picker enabled)
 *
 * Validation runs against the live FeatureRegistry catalog +
 * /strategies/builder/features/validate + plan-preview endpoints, so
 * unsupported feature refs render a danger border on the pill the
 * moment the operator picks them.
 */
export interface BuilderFormValue {
  name: string;
  description: string | null;
  feature_refs: string[];
  entry_rules: EditorRule[];
  exit_rules: EditorRule[];
  tags: string[];
}

export function emptyBuilderFormValue(): BuilderFormValue {
  return {
    name: "",
    description: null,
    feature_refs: ["5m.close[0]", "5m.open[0]"],
    entry_rules: [
      {
        name: "close_above_open",
        side: "long",
        intent_type: "entry",
        condition: {
          kind: "condition",
          left_feature: "5m.close[0]",
          operator: "gt",
          right_feature: "5m.open[0]",
          right_value: null,
        },
      },
    ],
    exit_rules: [],
    tags: [],
  };
}

export interface BuilderPaneProps {
  value: BuilderFormValue;
  onChange: (next: BuilderFormValue) => void;
  consumer?: "backtest" | "chart_lab" | "runtime";
  /** Optional: hide the identity / tags row when embedded in the composer. */
  hideIdentity?: boolean;
  /** Optional render slot below feature refs (e.g. plan preview chip). */
  belowFeatureRefs?: React.ReactNode;
}

export function BuilderPane(props: BuilderPaneProps): JSX.Element {
  const { value, onChange, consumer = "backtest", hideIdentity, belowFeatureRefs } = props;

  // Catalog is stable for the session — refetch every 5min in case
  // the operator adds a new registry entry on the backend.
  const catalog = useQuery({
    queryKey: ["strategy-builder", "features"],
    queryFn: () => StrategyComposerApi.features(),
    staleTime: 5 * 60_000,
  });

  const allFeatureRefs = useMemo(
    () => collectAllFeatureRefs(value),
    [value],
  );
  // Debounced live validation: revalidate when the union of feature refs in
  // play changes. The endpoint is cheap and idempotent.
  const validation = useQuery({
    queryKey: ["strategy-builder", "validate", consumer, allFeatureRefs.join("\n")],
    queryFn: () =>
      StrategyComposerApi.validateFeatures({ feature_refs: allFeatureRefs, consumer }),
    enabled: allFeatureRefs.length > 0,
    staleTime: 30_000,
  });
  const plan = useQuery({
    queryKey: ["strategy-builder", "plan-preview", consumer, value.feature_refs.join("\n")],
    queryFn: () =>
      StrategyComposerApi.planPreview({ feature_refs: value.feature_refs, consumer }),
    enabled: value.feature_refs.length > 0,
    staleTime: 30_000,
  });

  const invalidFeatureRefs = useMemo(() => {
    const out = new Set<string>();
    for (const item of validation.data?.items ?? []) {
      if (!item.valid) out.add(item.input);
    }
    return out;
  }, [validation.data]);

  return (
    <div className="space-y-4">
      {!hideIdentity ? (
        <section className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <TextField
            label="Version display name"
            value={value.name}
            onChange={(e) => onChange({ ...value, name: e.target.value })}
            placeholder="Trend follower v1"
          />
          <TextField
            label="Tags / capabilities (comma or space separated)"
            value={value.tags.join(", ")}
            onChange={(e) =>
              onChange({
                ...value,
                tags: splitTags(e.target.value),
              })
            }
            placeholder="intraday, mean-reversion, equities"
          />
          <TextField
            label="Description (optional)"
            value={value.description ?? ""}
            onChange={(e) =>
              onChange({ ...value, description: e.target.value || null })
            }
            className="md:col-span-2"
          />
        </section>
      ) : null}

      <FeatureRefsStrip
        value={value.feature_refs}
        onChange={(next) => onChange({ ...value, feature_refs: next })}
        catalog={catalog.data ?? []}
        validation={validation.data}
        plan={plan.data}
        catalogLoading={catalog.isLoading}
        consumer={consumer}
      />
      {belowFeatureRefs}

      <RulesSection
        title="Entry rules"
        intent="entry"
        rules={value.entry_rules}
        onChange={(next) => onChange({ ...value, entry_rules: next })}
        catalog={catalog.data ?? []}
        invalidFeatureRefs={invalidFeatureRefs}
        consumer={consumer}
      />
      <RulesSection
        title="Exit rules"
        intent="exit"
        rules={value.exit_rules}
        onChange={(next) => onChange({ ...value, exit_rules: next })}
        catalog={catalog.data ?? []}
        invalidFeatureRefs={invalidFeatureRefs}
        consumer={consumer}
      />
    </div>
  );
}

function FeatureRefsStrip({
  value,
  onChange,
  catalog,
  validation,
  plan,
  catalogLoading,
  consumer,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  catalog: FeatureCatalogItem[];
  validation: FeatureReferenceValidation | undefined;
  plan: FeaturePlanPreview | undefined;
  catalogLoading: boolean;
  consumer: string;
}): JSX.Element {
  const validationByInput = useMemo(() => {
    const m = new Map<string, { valid: boolean; message?: string | null }>();
    for (const item of validation?.items ?? []) m.set(item.input, item);
    return m;
  }, [validation]);

  function add(ref: string): void {
    const v = ref.trim();
    if (!v || value.includes(v)) return;
    onChange([...value, v]);
  }

  function remove(ref: string): void {
    onChange(value.filter((v) => v !== ref));
  }

  return (
    <section className="rounded border border-border bg-bg-subtle px-3 py-3">
      <header className="mb-2 flex items-center gap-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">
          Feature plan
        </span>
        {plan ? (
          plan.valid ? (
            <StatusBadge tone="ok">{plan.feature_keys.length} feature keys</StatusBadge>
          ) : (
            <StatusBadge tone="danger">invalid plan</StatusBadge>
          )
        ) : null}
        {catalogLoading ? <StatusBadge tone="muted">catalog loading…</StatusBadge> : null}
        <span className="ml-auto text-[11px] text-fg-subtle">
          Pick features the registry actually executes for {consumer}.
        </span>
      </header>
      <div className="flex flex-wrap items-center gap-2">
        {value.map((ref) => {
          const v = validationByInput.get(ref);
          const invalid = v && !v.valid;
          return (
            <span
              key={ref}
              className={
                invalid
                  ? "inline-flex items-center gap-1 rounded-full border border-danger bg-danger-subtle/40 px-2.5 py-1 font-mono text-xs"
                  : "inline-flex items-center gap-1 rounded-full border border-border bg-bg-inset px-2.5 py-1 font-mono text-xs"
              }
              title={invalid ? (v?.message ?? "unsupported") : undefined}
            >
              {ref}
              <button
                type="button"
                onClick={() => remove(ref)}
                className="text-fg-subtle hover:text-danger"
                aria-label={`Remove ${ref}`}
              >
                ×
              </button>
            </span>
          );
        })}
        <FeaturePicker
          value=""
          onChange={(next) => add(next)}
          catalog={catalog}
          consumer={consumer}
          placeholder="+ add feature"
        />
      </div>
      {validation && !validation.valid && validation.errors.length > 0 ? (
        <div className="mt-2 rounded border border-danger/40 bg-danger-subtle/40 px-2 py-1 text-[11px] text-danger">
          {validation.errors.slice(0, 5).join(" · ")}
        </div>
      ) : null}
      {plan && !plan.valid && plan.errors.length > 0 ? (
        <div className="mt-2 rounded border border-danger/40 bg-danger-subtle/40 px-2 py-1 text-[11px] text-danger">
          {plan.errors.slice(0, 5).join(" · ")}
        </div>
      ) : null}
    </section>
  );
}

function RulesSection({
  title,
  intent,
  rules,
  onChange,
  catalog,
  invalidFeatureRefs,
  consumer,
}: {
  title: string;
  intent: "entry" | "exit";
  rules: EditorRule[];
  onChange: (next: EditorRule[]) => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs: Set<string>;
  consumer: string;
}): JSX.Element {
  function setRule(index: number, next: EditorRule): void {
    onChange(rules.map((r, i) => (i === index ? next : r)));
  }
  function removeRule(index: number): void {
    onChange(rules.filter((_, i) => i !== index));
  }
  function addRule(): void {
    const isExit = intent === "exit";
    onChange([
      ...rules,
      {
        name: isExit ? `exit_rule_${rules.length + 1}` : `entry_rule_${rules.length + 1}`,
        side: "long",
        intent_type: intent,
        condition: isExit ? null : { kind: "group", operator: "all", children: [emptyCondition()] },
        logical_exit_rule: null,
      },
    ]);
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-fg-muted">{title}</span>
          <StatusBadge tone="neutral">{rules.length}</StatusBadge>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={addRule}
          leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
        >
          Add {intent === "exit" ? "exit" : "entry"} rule
        </Button>
      </div>
      {rules.length === 0 ? (
        intent === "entry" ? (
          <Banner
            severity="warning"
            title="No entry rules"
            message="A Strategy version needs at least one entry or exit rule before it can be saved."
          />
        ) : (
          <div className="rounded border border-dashed border-border px-3 py-2 text-[11px] text-fg-muted">
            No exit rules. Add a logical_exit (time / bars / session / feature / hybrid) to control when the position closes.
          </div>
        )
      ) : (
        <div className="space-y-2">
          {rules.map((r, i) => (
            <SignalRuleEditor
              key={i}
              rule={r}
              index={i}
              onChange={(next) => setRule(i, next)}
              onDelete={() => removeRule(i)}
              catalog={catalog}
              invalidFeatureRefs={invalidFeatureRefs}
              consumer={consumer}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function collectAllFeatureRefs(form: BuilderFormValue): string[] {
  const out = new Set<string>();
  for (const r of form.feature_refs) if (r) out.add(r);
  function walkCondition(expr: ConditionExpression | null | undefined): void {
    if (!expr) return;
    if (expr.kind === "group") {
      expr.children.forEach(walkCondition);
      return;
    }
    if (expr.left_feature) out.add(expr.left_feature);
    if (expr.right_feature) out.add(expr.right_feature);
  }
  for (const rule of [...form.entry_rules, ...form.exit_rules]) {
    walkCondition(rule.condition ?? null);
    if (rule.stop_candidate_feature) out.add(rule.stop_candidate_feature);
    if (rule.target_candidate_feature) out.add(rule.target_candidate_feature);
    if (rule.logical_exit_rule?.kind === "feature_condition") {
      walkCondition(
        (rule.logical_exit_rule.feature_condition as ConditionExpression | undefined) ?? null,
      );
    }
  }
  return Array.from(out);
}

function splitTags(input: string): string[] {
  return input
    .split(/[,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Reduce the editor BuilderFormValue into the wire-shape that the
 * existing StrategyVersionPayload expects.
 */
export function builderToVersionPayload(args: {
  form: BuilderFormValue;
  strategyId: string;
  versionId: string;
  versionNumber: number;
  createdAt: string;
}): {
  id: string;
  strategy_id: string;
  version: number;
  name: string;
  description: string | null;
  feature_refs: string[];
  entry_rules: EditorRule[];
  exit_rules: EditorRule[];
  tags: string[];
  created_at: string;
} {
  const { form, strategyId, versionId, versionNumber, createdAt } = args;
  return {
    id: versionId,
    strategy_id: strategyId,
    version: versionNumber,
    name: form.name.trim(),
    description: form.description?.trim() || null,
    feature_refs: form.feature_refs.slice(),
    entry_rules: form.entry_rules.map((r) => ({
      ...r,
      condition: r.condition ? compactGroup(asGroup(r.condition)) : undefined,
    })),
    exit_rules: form.exit_rules.map((r) => ({
      ...r,
      condition: r.condition ? compactGroup(asGroup(r.condition)) : undefined,
    })),
    tags: form.tags.slice(),
    created_at: createdAt,
  };
}

/**
 * Inverse of `builderToVersionPayload`.
 */
export function builderFromVersionPayload(payload: unknown): BuilderFormValue {
  const obj = (payload ?? {}) as Record<string, unknown>;
  const entry = Array.isArray(obj.entry_rules) ? (obj.entry_rules as unknown[]) : [];
  const exit = Array.isArray(obj.exit_rules) ? (obj.exit_rules as unknown[]) : [];
  function toRule(raw: unknown, intent: "entry" | "exit"): EditorRule {
    const r = (raw ?? {}) as Record<string, unknown>;
    return {
      name: typeof r.name === "string" ? r.name : "",
      side: r.side === "short" ? "short" : "long",
      intent_type: r.intent_type === "exit" ? "exit" : intent,
      condition: r.condition as ConditionExpression | null | undefined,
      logical_exit_rule: (r.logical_exit_rule ?? null) as EditorRule["logical_exit_rule"],
      stop_candidate_feature: typeof r.stop_candidate_feature === "string" ? r.stop_candidate_feature : null,
      target_candidate_feature: typeof r.target_candidate_feature === "string" ? r.target_candidate_feature : null,
    };
  }
  return {
    name: typeof obj.name === "string" ? obj.name : "",
    description: typeof obj.description === "string" ? obj.description : null,
    feature_refs: Array.isArray(obj.feature_refs)
      ? (obj.feature_refs as unknown[]).filter((s): s is string => typeof s === "string")
      : [],
    entry_rules: entry.map((r) => toRule(r, "entry")),
    exit_rules: exit.map((r) => toRule(r, "exit")),
    tags: Array.isArray(obj.tags)
      ? (obj.tags as unknown[]).filter((s): s is string => typeof s === "string")
      : [],
  };
}

// React hook so other panes can render a tiny "X of Y features valid" strip
// without re-fetching the catalog.
export function useFeatureValidationSummary(refs: string[], consumer: string = "backtest") {
  return useQuery({
    queryKey: ["strategy-builder", "validate", consumer, refs.join("\n")],
    queryFn: () => StrategyComposerApi.validateFeatures({ feature_refs: refs, consumer }),
    enabled: refs.length > 0,
    staleTime: 30_000,
  });
}

// Side-effect free helper used by tests to keep the editor's tag-split
// logic deterministic. Exported so callers can invoke it explicitly.
export function _splitTagsForTest(input: string): string[] {
  return splitTags(input);
}

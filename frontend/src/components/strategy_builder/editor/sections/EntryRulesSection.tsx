import { useState } from "react";
import { Plus } from "lucide-react";
import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import type { StrategyVersionPayload } from "@/api/schemas/strategies";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { SignalRuleEditor, type EditorRule } from "../../SignalRuleEditor";
import { FeatureIndex } from "../../FeatureIndex";
import { emptyCondition } from "../../conditionUtils";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * EntryRulesSection (#3 / #4) — wraps SignalRuleEditor for one side.
 *
 * Two visible sections (Long, Short) map to the same backend
 * `StrategyVersion.entry_rules[]` array. The host filters by `side` and
 * passes the matching slice in. New rules added here force the right
 * side. The side dropdown inside SignalRuleEditor still exists so the
 * operator can move a rule between sections — when they do, the rule
 * physically migrates on the next render.
 */
export interface EntryRulesSectionProps {
  side: "long" | "short";
  number: number;
  strategy: StrategyVersionPayload;
  onChange: (next: StrategyVersionPayload) => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs?: Set<string>;
  /** When true, render a "deferred / engine-blocked" banner inside
   * the short side. Long is always editable. */
  shortGated?: boolean;
  warnings?: CoherenceWarning[];
}

export function EntryRulesSection(props: EntryRulesSectionProps): JSX.Element {
  const { side, number, strategy, onChange, catalog, invalidFeatureRefs, shortGated, warnings } = props;

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";
  const rules = strategy.entry_rules as EditorRule[];
  const indices: number[] = [];
  rules.forEach((rule, i) => {
    if (rule.side === side) indices.push(i);
  });

  function setRule(at: number, next: EditorRule): void {
    const nextRules = rules.slice();
    nextRules[at] = next;
    onChange({ ...strategy, entry_rules: nextRules as StrategyVersionPayload["entry_rules"] });
  }

  function removeRule(at: number): void {
    const nextRules = rules.filter((_, i) => i !== at);
    onChange({ ...strategy, entry_rules: nextRules as StrategyVersionPayload["entry_rules"] });
  }

  function addRule(): void {
    const nextRules: EditorRule[] = [
      ...rules,
      {
        name: `${side}_entry_${indices.length + 1}`,
        side,
        intent_type: "entry",
        condition: { kind: "group", operator: "all", children: [emptyCondition()] },
        logical_exit_rule: null,
      },
    ];
    onChange({ ...strategy, entry_rules: nextRules as StrategyVersionPayload["entry_rules"] });
  }

  // Insert-feature drawer state — opening it from this section appends
  // the picked ref to the strategy's feature_refs union so it shows up
  // in the FeaturePicker dropdowns inside ConditionPillBuilder.
  const [drawerOpen, setDrawerOpen] = useState(false);

  function handleInsert(ref: string): void {
    if (!ref) return;
    if ((strategy.feature_refs ?? []).includes(ref)) return;
    onChange({ ...strategy, feature_refs: [...(strategy.feature_refs ?? []), ref] });
  }

  const title = side === "long" ? "Long entry rules" : "Short entry rules";
  const id = side === "long" ? "section-entry-long" : "section-entry-short";

  return (
    <SectionCard
      id={id}
      number={number}
      title={title}
      severity={sectionSeverity}
      subtitle={
        side === "long"
          ? "Conditions under which the strategy emits a long-side SignalPlan."
          : "Conditions under which the strategy emits a short-side SignalPlan."
      }
      trailing={
        <div className="flex items-center gap-2">
          <StatusBadge tone="neutral">{indices.length}</StatusBadge>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setDrawerOpen(true)}
            data-testid={`${id}-insert-feature`}
          >
            Insert feature
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={addRule}
            data-testid={`${id}-add-rule`}
          >
            Add rule
          </Button>
        </div>
      }
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
      {shortGated && side === "short" ? (
        <Banner
          severity="warning"
          title="Short side engine-gated"
          message="Short rules persist but Backtest / Runtime currently short-circuit non-LONG entries — see the Strategy roadmap for the unblock slice."
          className="mb-2"
        />
      ) : null}
      {indices.length === 0 ? (
        <div className="rounded border border-dashed border-border px-3 py-4 text-center text-[11px] text-fg-muted">
          No {side} entry rules yet.
        </div>
      ) : (
        <div className="space-y-2">
          {indices.map((i, position) => (
            <SignalRuleEditor
              key={i}
              index={position}
              rule={rules[i]!}
              onChange={(next) => setRule(i, next)}
              onDelete={() => removeRule(i)}
              catalog={catalog}
              invalidFeatureRefs={invalidFeatureRefs}
            />
          ))}
        </div>
      )}
      <FeatureIndex
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        catalog={catalog}
        onInsert={handleInsert}
        slotLabel={`${title} feature pool`}
      />
    </SectionCard>
  );
}

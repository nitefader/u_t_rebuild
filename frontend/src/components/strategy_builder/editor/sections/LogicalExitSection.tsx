import { Plus } from "lucide-react";
import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import type { StrategyVersionPayload } from "@/api/schemas/strategies";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { SignalRuleEditor, type EditorRule } from "../../SignalRuleEditor";
import { emptyLogicalExitRule } from "../../conditionUtils";
import { bucketExitRules } from "../editorState";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * LogicalExitSection (#9) — feature-condition + hybrid exit rules.
 *
 * Doctrine (per `feedback_logical_exit_is_the_only_exit_intent`): every
 * exit shape — time / bars / session / feature / hybrid — serializes
 * to a single `LogicalExitRule`. This editor section is operator-facing
 * UX only: it shows the *feature-flavor* exits here and routes the
 * *time-flavor* exits to Section 10. Both share `strategy.exit_rules[]`.
 *
 * If the operator changes an exit rule's kind from feature_condition
 * to bars_since_entry (etc.), it migrates to Section 10 on next render.
 * That's expected — the bucketing happens at render time.
 */
export interface LogicalExitSectionProps {
  strategy: StrategyVersionPayload;
  onChange: (next: StrategyVersionPayload) => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs?: Set<string>;
  warnings?: CoherenceWarning[];
}

export function LogicalExitSection(props: LogicalExitSectionProps): JSX.Element {
  const { strategy, onChange, catalog, invalidFeatureRefs, warnings } = props;

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";
  const rules = strategy.exit_rules as EditorRule[];
  const buckets = bucketExitRules(rules);
  const visible = buckets.logical;

  function setRule(at: number, next: EditorRule): void {
    const nextRules = rules.slice();
    nextRules[at] = next;
    onChange({ ...strategy, exit_rules: nextRules as StrategyVersionPayload["exit_rules"] });
  }
  function removeRule(at: number): void {
    onChange({
      ...strategy,
      exit_rules: rules.filter((_, i) => i !== at) as StrategyVersionPayload["exit_rules"],
    });
  }
  function addFeatureExit(): void {
    const next: EditorRule = {
      name: `feature_exit_${rules.length + 1}`,
      side: "long",
      intent_type: "exit",
      condition: null,
      logical_exit_rule: emptyLogicalExitRule("feature_condition"),
    };
    onChange({
      ...strategy,
      exit_rules: [...rules, next] as StrategyVersionPayload["exit_rules"],
    });
  }
  function addHybridExit(): void {
    const next: EditorRule = {
      name: `hybrid_exit_${rules.length + 1}`,
      side: "long",
      intent_type: "exit",
      condition: null,
      logical_exit_rule: emptyLogicalExitRule("hybrid"),
    };
    onChange({
      ...strategy,
      exit_rules: [...rules, next] as StrategyVersionPayload["exit_rules"],
    });
  }

  return (
    <SectionCard
      id="section-logical-exit"
      number={9}
      title="Logical exit plan"
      severity={sectionSeverity}
      subtitle="Feature-condition and hybrid exits. Time-based exits live in the next section."
      trailing={
        <div className="flex items-center gap-2">
          <StatusBadge tone="neutral">{visible.length}</StatusBadge>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={addHybridExit}
            data-testid="add-hybrid-exit"
          >
            Add hybrid
          </Button>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={addFeatureExit}
            data-testid="add-feature-exit"
          >
            Add feature exit
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
      {visible.length === 0 ? (
        <div className="rounded border border-dashed border-border px-3 py-4 text-center text-[11px] text-fg-muted">
          No feature / hybrid exits. Add one or rely on Time-based exit + execution preset
          stop / target.
        </div>
      ) : (
        <div className="space-y-2">
          {visible.map(({ rule, index }) => (
            <SignalRuleEditor
              key={index}
              index={index}
              rule={rule}
              onChange={(next) => setRule(index, next)}
              onDelete={() => removeRule(index)}
              catalog={catalog}
              invalidFeatureRefs={invalidFeatureRefs}
            />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

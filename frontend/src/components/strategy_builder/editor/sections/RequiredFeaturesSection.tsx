import { useMemo } from "react";
import type { StrategyVersionPayload } from "@/api/schemas/strategies";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { collectAllFeatureRefs } from "../editorState";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * RequiredFeaturesSection (#2) — read-only badges of every feature this
 * strategy references.
 *
 * Doctrine: this is a *derived* view. The saved StrategyVersion's
 * feature_refs + entry/exit rule conditions are the source of truth for
 * Backtest, Sim Lab, Chart Lab, Walk-Forward, and Runtime. There is no
 * parallel UI selection that feeds research — editing happens inside
 * Long/Short Entry sections, the Logical Exit section, etc.; this
 * section simply reflects the union back to the operator so they can
 * audit at a glance.
 */
export interface RequiredFeaturesSectionProps {
  strategy: StrategyVersionPayload;
  warnings?: CoherenceWarning[];
}

export function RequiredFeaturesSection(props: RequiredFeaturesSectionProps): JSX.Element {
  const { strategy, warnings } = props;
  const refs = useMemo(() => collectAllFeatureRefs(strategy), [strategy]);

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";

  return (
    <SectionCard
      id="section-required-features"
      number={2}
      title="Required features"
      subtitle="Derived from the strategy's feature refs and entry/exit conditions. Insert a feature inside a section to add it."
      severity={sectionSeverity}
      trailing={<StatusBadge tone="muted">{refs.length}</StatusBadge>}
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
      {refs.length === 0 ? (
        <p className="text-[11px] text-fg-muted">
          No features referenced yet. Insert one inside Long entry or Logical exit.
        </p>
      ) : (
        <ul className="flex flex-wrap gap-1.5" data-testid="required-features-list">
          {refs.map((ref) => (
            <li
              key={ref}
              className="inline-flex items-center rounded-full border border-border bg-bg-inset px-2 py-0.5 font-mono text-[11px]"
            >
              {ref}
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

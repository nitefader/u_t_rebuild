import type { StrategyVersionPayload } from "@/api/schemas/strategies";
import { TextField } from "@/components/ui/TextField";
import { SectionCard } from "./SectionCard";

/**
 * SummarySection (#1) — name, description, tags. Maps directly to
 * StrategyVersion.{name, description, tags}. Page-2 starts prefilled
 * from the AI-generated draft; the operator edits in place.
 *
 * Doctrine: no symbol field, no risk/account fields. Strategy is
 * symbol-agnostic — Watchlist + Deployment bind symbols, Account
 * decides at runtime.
 */
export interface SummarySectionProps {
  strategy: StrategyVersionPayload;
  onChange: (next: StrategyVersionPayload) => void;
}

export function SummarySection(props: SummarySectionProps): JSX.Element {
  const { strategy, onChange } = props;

  return (
    <SectionCard id="section-summary" number={1} title="Strategy summary">
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <TextField
          label="Name"
          value={strategy.name}
          onChange={(e) => onChange({ ...strategy, name: e.target.value })}
          placeholder="Trend follower v1"
          data-testid="summary-name"
        />
        <TextField
          label="Tags / capabilities (comma-separated)"
          value={strategy.tags.join(", ")}
          onChange={(e) =>
            onChange({
              ...strategy,
              tags: e.target.value
                .split(/[,\s]+/)
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
          placeholder="intraday, mean-reversion"
          data-testid="summary-tags"
        />
        <TextField
          label="Description (optional)"
          value={strategy.description ?? ""}
          onChange={(e) => onChange({ ...strategy, description: e.target.value || null })}
          className="md:col-span-2"
          data-testid="summary-description"
        />
      </div>
      <p className="mt-2 text-[11px] text-fg-muted">
        Strategy is symbol-agnostic. Watchlist + Deployment bind symbols at runtime; this
        editor never asks for a symbol.
      </p>
    </SectionCard>
  );
}

import type { ExecutionStylePresetValue } from "../../ExecutionStylePresetRow";
import { presetMeta } from "../../ExecutionStylePresetRow";
import { SectionCard } from "./SectionCard";

/**
 * EntryPlanSection (#5) — derived summary of how the strategy enters
 * a position. The actual order shape is decided by the chosen Execution
 * Preset (#12); this section restates the entry leg in operator-friendly
 * language so they don't have to scroll back to the preset to confirm.
 *
 * Doctrine: SignalPlan-shape derivation is backend-only — the frontend
 * never computes a SignalPlan locally. We surface the preset's known
 * entry-leg copy here, that's all.
 */
export interface EntryPlanSectionProps {
  preset: ExecutionStylePresetValue;
}

const ENTRY_LEG_COPY: Record<string, string> = {
  market_entry_market_exit: "Market order in on entry signal.",
  stop_entry_market_exit: "Stop order at signal-bar reference + offset.",
  bracket_stop_target: "Market order in; OCO bracket arms on fill.",
  bracket_runner: "Market order in; first target releases part of position, runner trails.",
  multi_target_scale_out: "Market order in; N targets scale out the position.",
};

export function EntryPlanSection(props: EntryPlanSectionProps): JSX.Element {
  const { preset } = props;
  const meta = presetMeta(preset.kind);
  const copy = ENTRY_LEG_COPY[preset.kind] ?? meta.summary;

  return (
    <SectionCard
      id="section-entry-plan"
      number={5}
      title="Entry plan"
      subtitle="Driven by the chosen execution preset (Section 12). Edit there to change the entry leg."
    >
      <div className="space-y-2 text-[12px]">
        <div>
          <div className="text-[10px] uppercase tracking-wide text-fg-muted">Preset</div>
          <div className="font-medium">{meta.label}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wide text-fg-muted">Entry leg</div>
          <p className="text-fg-muted">{copy}</p>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wide text-fg-muted">SignalPlan placeholder</div>
          <div className="rounded border border-border bg-bg-inset px-2 py-1 font-mono text-[11px]">
            [symbol] · open · {presetEntryOrder(preset.kind)} · qty=full
          </div>
          <p className="mt-1 text-[10.5px] text-fg-muted">Bound at deployment via Watchlist.</p>
        </div>
      </div>
    </SectionCard>
  );
}

function presetEntryOrder(kind: string): string {
  if (kind === "stop_entry_market_exit") return "stop";
  return "market";
}

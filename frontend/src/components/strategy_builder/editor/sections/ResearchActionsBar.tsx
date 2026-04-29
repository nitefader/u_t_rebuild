import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { SectionCard } from "./SectionCard";

/**
 * ResearchActionsBar (#14) — post-save deep links into the research
 * surfaces.
 *
 * Doctrine: Backtest / Sim Lab / Chart Lab launchers live on the
 * StrategyDetail page (post-save), NOT inside Compose. This section is
 * a tease + escape hatch: it shows three disabled buttons until Save
 * succeeds, after which the operator is navigated to /strategies/:id
 * with the Verify-in-Backtest banner. We keep the buttons disabled
 * with a "Save first" tooltip so the operator knows what's coming.
 */
export interface ResearchActionsBarProps {
  savedStrategyId: string | null;
}

export function ResearchActionsBar(props: ResearchActionsBarProps): JSX.Element {
  const { savedStrategyId } = props;
  const enabled = Boolean(savedStrategyId);

  return (
    <SectionCard
      id="section-research-actions"
      number={14}
      title="Research actions"
      subtitle="Backtest / Sim Lab / Chart Lab launchers open after Save. Compose intentionally does not host them."
    >
      <div className="flex flex-wrap items-center gap-2">
        <ResearchLink
          enabled={enabled}
          href={enabled ? `/strategies/${savedStrategyId}?launch=backtest` : "#"}
          label="Verify in Backtest"
        />
        <ResearchLink
          enabled={enabled}
          href={enabled ? `/strategies/${savedStrategyId}?launch=sim_lab` : "#"}
          label="Open in Sim Lab"
        />
        <ResearchLink
          enabled={enabled}
          href={enabled ? `/strategies/${savedStrategyId}?launch=chart_lab` : "#"}
          label="Open in Chart Lab"
        />
        {!enabled ? (
          <span className="text-[11px] text-fg-muted">Save first to enable.</span>
        ) : null}
      </div>
    </SectionCard>
  );
}

function ResearchLink({
  enabled,
  href,
  label,
}: {
  enabled: boolean;
  href: string;
  label: string;
}): JSX.Element {
  if (!enabled) {
    return (
      <Button
        type="button"
        size="sm"
        variant="secondary"
        disabled
        leftIcon={<ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />}
        title="Save first"
      >
        {label}
      </Button>
    );
  }
  return (
    <Link to={href}>
      <Button
        type="button"
        size="sm"
        variant="secondary"
        leftIcon={<ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />}
      >
        {label}
      </Button>
    </Link>
  );
}

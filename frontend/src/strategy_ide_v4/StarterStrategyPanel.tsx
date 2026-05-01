/**
 * StarterStrategyPanel — right-rail slide-out of curated starter strategies.
 * Collapsible. Default open on fresh page; default collapsed when loading via ?id=.
 */

import { useState } from "react";
import { ChevronRight, ChevronDown, PanelRightClose } from "lucide-react";
import { STARTER_STRATEGIES } from "./starterStrategies";
import type { StarterStrategy } from "./starterStrategies";
import type { Horizon } from "./HorizonPicker";
import type { Direction } from "./DirectionToggle";
import type { StrategyVersionV4Draft } from "@/api/schemas/strategiesV4";
import { AIPromptTab } from "./AIPromptTab";

type PanelTab = "templates" | "ai";

export interface StarterStrategyPanelProps {
  /** Whether the panel is currently open (visible). */
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Current horizon filter from the HorizonPicker (null = All). */
  horizonFilter: Horizon | null;
  /** Current direction filter from DirectionToggle (null = All). */
  directionFilter: Direction | null;
  /** Called when the operator clicks Apply template on a starter. */
  onApply: (draft: StrategyVersionV4Draft) => void;
}

type SortKey = "name" | "recently_used" | "most_used";

const HORIZON_LABELS: Record<string, string> = {
  scalping: "Scalping",
  intraday: "Intraday",
  swing: "Swing",
  position: "Position",
};

const DIRECTION_LABELS: Record<string, string> = {
  long: "Long",
  short: "Short",
  both: "Both",
};

function DetailRow({ label, value, accent }: { label: string; value: string; accent?: string }): JSX.Element {
  return (
    <div>
      <dt className="font-semibold text-fg-subtle uppercase text-[9px] tracking-wider">{label}</dt>
      <dd className={`leading-tight ${accent ?? "text-fg-muted"}`}>{value}</dd>
    </div>
  );
}

function StarterCard({
  strategy,
  onApply,
}: {
  strategy: StarterStrategy;
  onApply: (draft: StrategyVersionV4Draft) => void;
}): JSX.Element {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg border border-border bg-bg-raised overflow-hidden" data-testid="starter-card">
      {/* Collapsed header */}
      <button
        type="button"
        className="flex w-full items-start gap-2 px-3 py-2.5 text-left focus:outline-none hover:bg-bg-subtle transition-colors"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        aria-label={`${strategy.name} — expand strategy details`}
      >
        <span className="mt-0.5 shrink-0 text-fg-subtle">
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold text-fg leading-tight">{strategy.name}</p>
          <p className="mt-0.5 text-[10px] text-fg-muted leading-tight line-clamp-2">
            {strategy.description}
          </p>
          {!expanded ? (
            <div className="mt-1 flex flex-wrap gap-1">
              <span className="rounded-full bg-bg-inset px-1.5 py-0.5 text-[9px] font-medium text-fg-subtle uppercase tracking-wide">
                {HORIZON_LABELS[strategy.tags.horizon] ?? strategy.tags.horizon}
              </span>
              <span className="rounded-full bg-bg-inset px-1.5 py-0.5 text-[9px] font-medium text-fg-subtle uppercase tracking-wide">
                {DIRECTION_LABELS[strategy.tags.direction] ?? strategy.tags.direction}
              </span>
              <span className="rounded-full bg-bg-inset px-1.5 py-0.5 text-[9px] font-medium text-fg-subtle uppercase tracking-wide">
                {strategy.tags.timeframe}
              </span>
            </div>
          ) : null}
        </div>
      </button>

      {/* Expanded details */}
      {expanded ? (
        <div className="border-t border-border bg-bg-subtle px-3 pb-3 pt-2">
          {/* Tag badges */}
          <div className="flex flex-wrap gap-1 mb-2">
            <span className="rounded-full bg-bg-inset px-1.5 py-0.5 text-[9px] font-medium text-fg-subtle uppercase tracking-wide">
              {HORIZON_LABELS[strategy.tags.horizon] ?? strategy.tags.horizon}
            </span>
            <span className="rounded-full bg-bg-inset px-1.5 py-0.5 text-[9px] font-medium text-fg-subtle uppercase tracking-wide">
              {DIRECTION_LABELS[strategy.tags.direction] ?? strategy.tags.direction}
            </span>
            <span className="rounded-full bg-bg-inset px-1.5 py-0.5 text-[9px] font-medium text-accent uppercase tracking-wide">
              {strategy.tags.timeframe}
            </span>
            <span className="rounded-full bg-bg-inset px-1.5 py-0.5 text-[9px] font-medium text-fg-subtle">
              {strategy.tags.hold}
            </span>
          </div>

          {/* About this strategy block */}
          <div className="mb-2 rounded border border-border/60 bg-bg-inset px-2 py-1.5">
            <p className="text-[9px] font-semibold uppercase tracking-wider text-fg-subtle mb-1">
              About this strategy
            </p>
            <p className="text-[10px] text-fg-muted leading-snug">
              <span className="font-medium text-fg">Edge:</span> {strategy.edge_type}
            </p>
            <p className="text-[10px] text-fg-muted leading-snug">
              <span className="font-medium text-fg">Best on:</span> {strategy.best_on}
            </p>
            <p className="mt-0.5 text-[10px] text-fg-muted leading-snug italic">
              {strategy.why_it_works}
            </p>
          </div>

          {/* 7-key details */}
          <dl className="flex flex-col gap-1.5 text-[11px]">
            <DetailRow label="Entry" value={strategy.details.entry} />
            <DetailRow label="Stop" value={strategy.details.stop} accent="text-danger" />
            <DetailRow label="Target" value={strategy.details.target} accent="text-ok" />
            <DetailRow label="Runner" value={strategy.details.runner} />
            <DetailRow label="Logical exit" value={strategy.details.logical_exit} />
            <DetailRow label="Time constraints" value={strategy.details.time_constraints} />
            <DetailRow label="Risk sizing" value={strategy.details.risk_sizing} />
          </dl>

          {/* Suggestions */}
          <div className="mt-2 space-y-1">
            <p className="text-[9px] text-fg-subtle">
              <span className="font-semibold uppercase tracking-wide">Controls:</span>{" "}
              {strategy.suggested_controls}
            </p>
            <p className="text-[9px] text-fg-subtle">
              <span className="font-semibold uppercase tracking-wide">Execution:</span>{" "}
              {strategy.suggested_execution_plan}
            </p>
          </div>

          <button
            type="button"
            className="mt-3 w-full rounded border border-accent bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent/20 transition-colors focus:outline-none"
            onClick={() => onApply(strategy.draft)}
            aria-label={`Apply ${strategy.name} template`}
          >
            Apply template
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function StarterStrategyPanel({
  open,
  onOpenChange,
  horizonFilter,
  directionFilter,
  onApply,
}: StarterStrategyPanelProps): JSX.Element {
  const [activeTab, setActiveTab] = useState<PanelTab>("templates");
  const [sort, setSort] = useState<SortKey>("name");
  const [localHorizon, setLocalHorizon] = useState<string>("all");
  const [localDirection, setLocalDirection] = useState<string>("all");

  function handleAIApply(draft: StrategyVersionV4Draft): void {
    onApply(draft);
    // Switch back to Templates tab so the AI panel doesn't overlay the editor
    setActiveTab("templates");
  }

  // Effective horizon filter: prop wins if set, else local
  const effectiveHorizon = horizonFilter ?? (localHorizon !== "all" ? localHorizon : null);
  const effectiveDirection =
    directionFilter ?? (localDirection !== "all" ? localDirection : null);

  const filtered = STARTER_STRATEGIES.filter((s) => {
    if (effectiveHorizon && s.tags.horizon !== effectiveHorizon) return false;
    if (effectiveDirection && s.tags.direction !== effectiveDirection) return false;
    return true;
  });

  const sorted = [...filtered].sort((a, b) => {
    if (sort === "name") return a.name.localeCompare(b.name);
    // recently_used and most_used are placeholders (no persistence in this slice)
    return a.name.localeCompare(b.name);
  });

  if (!open) {
    // Collapsed: show a 12px handle
    return (
      <div
        className="flex w-3 shrink-0 cursor-pointer flex-col items-center justify-start border-l border-border bg-bg-subtle pt-3 hover:bg-bg-raised transition-colors"
        role="button"
        tabIndex={0}
        aria-label="Open starter strategies panel"
        onClick={() => onOpenChange(true)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onOpenChange(true);
          }
        }}
      />
    );
  }

  return (
    <div className="flex w-[360px] shrink-0 flex-col overflow-hidden border-l border-border bg-bg-subtle">
      {/* Panel header */}
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2">
        <span className="flex-1 text-[10px] font-semibold uppercase tracking-widest text-fg-subtle">
          STARTER STRATEGIES
        </span>
        {activeTab === "templates" && (
          <span className="text-[10px] text-fg-subtle">
            10 curated &middot; {filtered.length} after filter
          </span>
        )}
        <button
          type="button"
          className="shrink-0 rounded p-1 text-fg-subtle hover:bg-bg-raised hover:text-fg focus:outline-none transition-colors"
          onClick={() => onOpenChange(false)}
          aria-label="Close starter strategies panel"
        >
          <PanelRightClose className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>

      {/* Tab strip */}
      <div className="flex shrink-0 border-b border-border" role="tablist" aria-label="Panel tabs">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "templates"}
          aria-controls="starter-panel-templates"
          id="starter-tab-templates"
          className={`flex-1 py-2 text-[11px] font-medium transition-colors focus:outline-none ${
            activeTab === "templates"
              ? "border-b-2 border-accent text-accent"
              : "text-fg-muted hover:text-fg"
          }`}
          onClick={() => setActiveTab("templates")}
          data-testid="tab-templates"
        >
          Templates
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "ai"}
          aria-controls="starter-panel-ai"
          id="starter-tab-ai"
          className={`flex-1 py-2 text-[11px] font-medium transition-colors focus:outline-none ${
            activeTab === "ai"
              ? "border-b-2 border-accent text-accent"
              : "text-fg-muted hover:text-fg"
          }`}
          onClick={() => setActiveTab("ai")}
          data-testid="tab-ai"
        >
          AI prompt
        </button>
      </div>

      {/* Templates tab */}
      {activeTab === "templates" && (
        <div
          id="starter-panel-templates"
          role="tabpanel"
          aria-labelledby="starter-tab-templates"
          className="flex flex-1 flex-col overflow-hidden"
        >
          {/* Filter row */}
          <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-3 py-2">
            <select
              value={localHorizon}
              onChange={(e) => setLocalHorizon(e.target.value)}
              aria-label="Horizon filter"
              className="rounded border border-border bg-bg-inset px-2 py-0.5 text-[11px] text-fg focus:border-accent focus:outline-none"
            >
              <option value="all">All horizons</option>
              <option value="scalping">Scalping</option>
              <option value="intraday">Intraday</option>
              <option value="swing">Swing</option>
              <option value="position">Position</option>
            </select>

            <select
              value={localDirection}
              onChange={(e) => setLocalDirection(e.target.value)}
              aria-label="Direction filter"
              className="rounded border border-border bg-bg-inset px-2 py-0.5 text-[11px] text-fg focus:border-accent focus:outline-none"
            >
              <option value="all">All directions</option>
              <option value="long">Long</option>
              <option value="short">Short</option>
              <option value="both">Both</option>
            </select>

            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}
              aria-label="Sort order"
              className="rounded border border-border bg-bg-inset px-2 py-0.5 text-[11px] text-fg focus:border-accent focus:outline-none"
            >
              <option value="recently_used">Recently used</option>
              <option value="name">Name</option>
              <option value="most_used">Most used</option>
            </select>
          </div>

          {/* Strategy list */}
          <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-2">
            {sorted.length === 0 ? (
              <p className="py-6 text-center text-xs text-fg-subtle">No strategies match the current filter.</p>
            ) : (
              sorted.map((strategy) => (
                <StarterCard key={strategy.id} strategy={strategy} onApply={onApply} />
              ))
            )}
          </div>
        </div>
      )}

      {/* AI prompt tab */}
      {activeTab === "ai" && (
        <div
          id="starter-panel-ai"
          role="tabpanel"
          aria-labelledby="starter-tab-ai"
          className="flex-1 overflow-y-auto"
        >
          <AIPromptTab onApplyTemplate={handleAIApply} currentDraft={undefined} />
        </div>
      )}
    </div>
  );
}

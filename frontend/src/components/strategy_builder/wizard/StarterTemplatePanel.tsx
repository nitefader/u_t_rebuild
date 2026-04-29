import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Lock } from "lucide-react";
import type { WizardIntent } from "@/api/schemas/strategyComposer";
import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import { cn } from "@/lib/cn";
import {
  STARTER_TEMPLATES,
  type StarterTemplate,
  type TemplateRegime,
} from "./templates";
import {
  extractIntent,
  scoreTemplate,
  type IntentSignal,
} from "./intentExtraction";

const RECENTLY_USED_KEY = "compose:wizard:recently-used-templates";
const SORT_KEY = "compose:wizard:sort";
const FILTER_KEY = "compose:wizard:filter";

type HorizonFilter = "all" | WizardIntent["horizon"];
type DirectionFilter = "all" | WizardIntent["direction"];
type SortOrder = "default" | "recently_used";

type FilterState = {
  horizon: HorizonFilter;
  direction: DirectionFilter;
};

const DEFAULT_FILTER: FilterState = { horizon: "all", direction: "all" };
const DEFAULT_SORT: SortOrder = "default";

const REGIME_LABEL: Record<TemplateRegime, string> = {
  ranging: "Ranging regime",
  trending: "Trending regime",
  high_vol: "High-volatility regime",
  regime_agnostic: "Regime-agnostic",
};

export interface StarterTemplatePanelProps {
  prompt: string;
  onApplyTemplate: (template: StarterTemplate) => void;
}

function readRecentlyUsed(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(RECENTLY_USED_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v) => typeof v === "string") : [];
  } catch {
    return [];
  }
}

function writeRecentlyUsed(list: string[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(RECENTLY_USED_KEY, JSON.stringify(list.slice(0, 12)));
  } catch {
    // localStorage unavailable — silent. Sort gracefully degrades to default.
  }
}

function readPersistedSort(): SortOrder {
  if (typeof window === "undefined") return DEFAULT_SORT;
  const raw = window.localStorage.getItem(SORT_KEY);
  return raw === "recently_used" || raw === "default" ? raw : DEFAULT_SORT;
}

function readPersistedFilter(): FilterState {
  if (typeof window === "undefined") return DEFAULT_FILTER;
  try {
    const raw = window.localStorage.getItem(FILTER_KEY);
    if (!raw) return DEFAULT_FILTER;
    const parsed = JSON.parse(raw) as Partial<FilterState>;
    return {
      horizon:
        parsed.horizon === "scalping" ||
        parsed.horizon === "intraday" ||
        parsed.horizon === "swing" ||
        parsed.horizon === "position"
          ? parsed.horizon
          : "all",
      direction:
        parsed.direction === "long" || parsed.direction === "short" || parsed.direction === "both"
          ? parsed.direction
          : "all",
    };
  } catch {
    return DEFAULT_FILTER;
  }
}

export function StarterTemplatePanel({
  prompt,
  onApplyTemplate,
}: StarterTemplatePanelProps): JSX.Element {
  const [filter, setFilter] = useState<FilterState>(readPersistedFilter);
  const [sort, setSort] = useState<SortOrder>(readPersistedSort);
  const [recentlyUsed, setRecentlyUsed] = useState<string[]>(readRecentlyUsed);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(FILTER_KEY, JSON.stringify(filter));
  }, [filter]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SORT_KEY, sort);
  }, [sort]);

  const intentSignals: IntentSignal[] = useMemo(() => extractIntent(prompt), [prompt]);

  const scoredTopThree = useMemo(() => {
    if (intentSignals.length === 0) return new Set<string>();
    const ranked = STARTER_TEMPLATES.map((t) => ({
      id: t.id,
      score: scoreTemplate(t, intentSignals),
    }))
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
      .map((r) => r.id);
    return new Set(ranked);
  }, [intentSignals]);

  function applyFilters(list: readonly StarterTemplate[]): StarterTemplate[] {
    return list.filter((t) => {
      if (filter.horizon !== "all" && t.intended_horizon !== filter.horizon) return false;
      if (filter.direction !== "all" && t.default_direction !== filter.direction) return false;
      return true;
    });
  }

  function applySort(list: StarterTemplate[]): StarterTemplate[] {
    if (sort === "recently_used" && recentlyUsed.length > 0) {
      const indexOf = (id: string): number => {
        const idx = recentlyUsed.indexOf(id);
        return idx === -1 ? Number.POSITIVE_INFINITY : idx;
      };
      return [...list].sort((a, b) => indexOf(a.id) - indexOf(b.id));
    }
    return list; // default = curated order from STARTER_TEMPLATES
  }

  const ready = applySort(applyFilters(STARTER_TEMPLATES.filter((t) => !t.requires_session_execution)));
  const deferred = applyFilters(
    STARTER_TEMPLATES.filter((t) => t.requires_session_execution),
  );

  function handleApply(template: StarterTemplate): void {
    if (template.requires_session_execution) return;
    const next = [template.id, ...recentlyUsed.filter((id) => id !== template.id)].slice(0, 12);
    setRecentlyUsed(next);
    writeRecentlyUsed(next);
    onApplyTemplate(template);
  }

  return (
    <aside
      className="flex h-full flex-col gap-3 overflow-y-auto border-l border-border bg-bg-subtle p-3"
      aria-label="Starter strategies"
      data-testid="starter-template-panel"
    >
      <header className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
            Starter strategies
          </h2>
          <span className="text-[10.5px] text-fg-subtle">
            {STARTER_TEMPLATES.length} curated · {ready.length + deferred.length} after filter
          </span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Select
            label="Horizon"
            value={filter.horizon}
            onChange={(e) =>
              setFilter((prev) => ({ ...prev, horizon: e.target.value as HorizonFilter }))
            }
          >
            <option value="all">All</option>
            <option value="scalping">Scalping</option>
            <option value="intraday">Intraday</option>
            <option value="swing">Swing</option>
            <option value="position">Position</option>
          </Select>
          <Select
            label="Direction"
            value={filter.direction}
            onChange={(e) =>
              setFilter((prev) => ({ ...prev, direction: e.target.value as DirectionFilter }))
            }
          >
            <option value="all">All</option>
            <option value="long">Long</option>
            <option value="short">Short</option>
            <option value="both">Both</option>
          </Select>
        </div>
        <Select
          label="Sort"
          value={sort}
          onChange={(e) => setSort(e.target.value as SortOrder)}
        >
          <option value="default">Default (curated)</option>
          <option value="recently_used">Recently used</option>
        </Select>
      </header>

      <section aria-label="Available templates" className="flex flex-col gap-2">
        <h3 className="text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
          Available
        </h3>
        {ready.length === 0 ? (
          <div className="rounded border border-border bg-bg-inset p-3 text-xs text-fg-muted">
            No templates match the current filter. Reset to see all 9 ready starters.
          </div>
        ) : (
          ready.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              expanded={expandedId === t.id}
              onToggle={() => setExpandedId((prev) => (prev === t.id ? null : t.id))}
              onApply={() => handleApply(t)}
              suggestedByPrompt={scoredTopThree.has(t.id)}
            />
          ))
        )}
      </section>

      {deferred.length > 0 ? (
        <section aria-label="Deferred templates" className="flex flex-col gap-2">
          <h3 className="text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
            Awaiting backend update (Slice 6a-ii)
          </h3>
          {deferred.map((t) => (
            <TemplateCard
              key={t.id}
              template={t}
              expanded={expandedId === t.id}
              onToggle={() => setExpandedId((prev) => (prev === t.id ? null : t.id))}
              onApply={() => handleApply(t)}
              suggestedByPrompt={scoredTopThree.has(t.id)}
            />
          ))}
        </section>
      ) : null}
    </aside>
  );
}

interface TemplateCardProps {
  template: StarterTemplate;
  expanded: boolean;
  onToggle: () => void;
  onApply: () => void;
  suggestedByPrompt: boolean;
}

function TemplateCard({
  template,
  expanded,
  onToggle,
  onApply,
  suggestedByPrompt,
}: TemplateCardProps): JSX.Element {
  const blocked = template.requires_session_execution;
  return (
    <article
      data-testid={`template-card-${template.id}`}
      data-template-id={template.id}
      data-blocked={blocked || undefined}
      data-suggested={suggestedByPrompt || undefined}
      className={cn(
        "rounded border bg-bg",
        blocked ? "border-border/60 bg-bg-inset/40 opacity-80" : "border-border",
        suggestedByPrompt && !blocked && "border-accent shadow-sm shadow-accent/30",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-start gap-2 px-3 py-2 text-left hover:bg-bg-inset/40"
      >
        <span className="mt-0.5 text-fg-muted">
          {expanded ? (
            <ChevronDown className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">{template.display_name}</span>
            {blocked ? (
              <span
                className="inline-flex items-center gap-1 rounded bg-fg-muted/15 px-1.5 py-0.5 text-[10px] font-medium text-fg-muted"
                title={template.deferred_reason ?? undefined}
              >
                <Lock className="h-3 w-3" aria-hidden="true" /> Blocked
              </span>
            ) : null}
            {suggestedByPrompt && !blocked ? (
              <span className="rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                Matches prompt
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-[11px] text-fg-muted">{template.short_description}</p>
          <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-fg-subtle">
            <span className="rounded border border-border px-1.5 py-0.5">
              {template.intended_horizon}
            </span>
            <span className="rounded border border-border px-1.5 py-0.5">
              {template.default_direction}
            </span>
            <span className="rounded border border-border px-1.5 py-0.5">
              {template.default_base_timeframe}
            </span>
            <span className="rounded border border-border px-1.5 py-0.5">
              {REGIME_LABEL[template.regime_assumption]}
            </span>
            <span className="rounded border border-border px-1.5 py-0.5">
              hold ~{template.expected_hold_time}
            </span>
            {template.indicative_only_disclaimer ? (
              <span
                className="rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-warning"
                title="Indicative only — backtest before live deployment."
              >
                Indicative
              </span>
            ) : null}
          </div>
        </div>
      </button>
      {expanded ? (
        <div className="space-y-2 border-t border-border bg-bg-inset/40 px-3 py-2 text-[12px] text-fg">
          <p>{template.long_description}</p>
          <Section label="Entry">{template.entry_logic_plain_english}</Section>
          <Section label="Stop">{template.stop_logic_plain_english}</Section>
          <Section label="Target">{template.target_logic_plain_english}</Section>
          <Section label="Logical exit">
            {template.logical_exit_logic_plain_english}
          </Section>
          <Section label="Known behavior">{template.known_behavior}</Section>
          <Section label="Caveats">{template.caveats}</Section>
          {blocked ? (
            <div className="rounded border border-warning/40 bg-warning/10 p-2 text-[11px] text-warning">
              {template.deferred_reason}
            </div>
          ) : null}
          <div className="pt-1">
            <Button
              size="sm"
              variant={blocked ? "ghost" : "primary"}
              disabled={blocked}
              onClick={onApply}
              data-testid={`apply-template-${template.id}`}
            >
              {blocked ? "Generate disabled" : "Apply template"}
            </Button>
          </div>
        </div>
      ) : null}
    </article>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }): JSX.Element {
  return (
    <div>
      <div className="text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
        {label}
      </div>
      <div className="text-[12px]">{children}</div>
    </div>
  );
}

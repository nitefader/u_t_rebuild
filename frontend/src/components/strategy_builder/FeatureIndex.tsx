import { useMemo, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Search, X } from "lucide-react";
import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

/**
 * FeatureIndex — Slice 6c drawer/popover refactor.
 *
 * Page-2 editor sections open this drawer to insert ONE feature_ref into
 * a specific slot (the right side of a condition row, the stop_candidate
 * field, etc.). The drawer no longer owns a `value: string[]` aggregate —
 * it emits a single `onInsert(ref)` event and lets the caller decide
 * where the ref lands.
 *
 * Doctrine guards baked in:
 *   - This is an *assistive editor tool*. The saved StrategyVersion's
 *     `feature_refs` + entry/exit rule conditions are the source of
 *     truth; downstream surfaces (Backtest, Sim Lab, Chart Lab,
 *     Walk-Forward, Runtime) derive features from there, never from
 *     a parallel UI selection.
 *   - PORTFOLIO-scope features are out of scope for Strategy Compose
 *     (filtered out — they belong to the runtime portfolio governor).
 *
 * Structure:
 *   1. Sticky search input
 *   2. Results grouped by namespace (Price / Technical / Session)
 *      — each row exposes a stack of timeframe pills; clicking a pill
 *      emits a normalized feature_ref at that timeframe and closes
 *      the drawer.
 *   3. "Advanced — paste a raw expression" disclosure
 *
 * The component is controlled (`open` / `onOpenChange`). Callers render
 * their own trigger button or invoke programmatically.
 */

const PILL_TIMEFRAMES = ["1m", "5m", "15m", "1h", "1d"] as const;

const NAMESPACE_ORDER = ["price", "technical", "session"] as const;
const NAMESPACE_LABEL: Record<string, string> = {
  price: "Price",
  technical: "Technical",
  session: "Session",
  other: "Other",
};

export interface FeatureIndexProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  catalog: FeatureCatalogItem[];
  onInsert: (ref: string) => void;
  consumer?: string;
  /** Optional title shown in the drawer header — describes the slot. */
  slotLabel?: string;
}

export function FeatureIndex(props: FeatureIndexProps): JSX.Element {
  const { open, onOpenChange, catalog, onInsert, consumer = "backtest", slotLabel } = props;
  const [query, setQuery] = useState("");
  const [advancedRaw, setAdvancedRaw] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return catalog.filter((c) => {
      // PORTFOLIO scope is filtered out at the Strategy-author surface —
      // those features belong to the runtime portfolio governor.
      const scope = (c.scope ?? "symbol").toLowerCase();
      if (scope === "portfolio") return false;
      if (c.supported_consumers?.length && !c.supported_consumers.includes(consumer)) {
        return false;
      }
      if (!q) return true;
      const hay = [c.kind, c.display_name ?? "", c.description ?? "", c.namespace ?? ""]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [catalog, consumer, query]);

  const grouped = useMemo(() => groupByNamespace(filtered), [filtered]);

  function emit(ref: string): void {
    const trimmed = ref.trim();
    if (!trimmed) return;
    onInsert(trimmed);
    setAdvancedRaw("");
    onOpenChange(false);
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/45" />
        <Dialog.Content
          aria-label="Feature index"
          data-testid="feature-index-drawer"
          className={cn(
            "fixed right-0 top-0 z-50 flex h-full w-full max-w-[420px] flex-col",
            "border-l border-border bg-bg-raised shadow-raised animate-ut-slide-in-right",
            "focus:outline-none",
          )}
        >
          <header className="flex items-start justify-between gap-3 border-b border-border px-3 py-2">
            <div>
              <Dialog.Title className="text-sm font-semibold">Insert feature</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-[11px] text-fg-muted">
                {slotLabel
                  ? `Insert into ${slotLabel}.`
                  : "Pick a feature, then a timeframe pill, to insert at that timeframe."}
              </Dialog.Description>
            </div>
            <Dialog.Close
              aria-label="Close drawer"
              className="rounded p-1 text-fg-muted hover:bg-bg-subtle hover:text-fg"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Dialog.Close>
          </header>

          <div className="border-b border-border/70 px-3 py-2">
            <div className="flex items-center gap-2 rounded border border-border bg-bg-inset px-2 py-1">
              <Search className="h-3.5 w-3.5 text-fg-muted" aria-hidden="true" />
              <input
                type="text"
                autoFocus
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search features… ema, rsi, vwap, opening range"
                className="flex-1 bg-transparent text-xs outline-none"
                aria-label="Search features"
              />
              {query ? (
                <button
                  type="button"
                  onClick={() => setQuery("")}
                  className="text-fg-muted hover:text-fg"
                  aria-label="Clear search"
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              ) : null}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {grouped.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-fg-muted">
                Nothing matches &ldquo;{query}&rdquo;. Try a shorter term, or paste a raw expression
                below.
              </div>
            ) : (
              grouped.map(([namespace, items]) => (
                <div key={namespace} className="py-1">
                  <div className="sticky top-0 z-[1] bg-bg-raised px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                    {NAMESPACE_LABEL[namespace] ?? namespace}
                  </div>
                  {items.map((item) => (
                    <FeatureRow key={item.kind} item={item} onInsert={emit} />
                  ))}
                </div>
              ))
            )}
          </div>

          <div className="border-t border-border/70 bg-bg-subtle px-3 py-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
              Advanced — paste a raw expression
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={advancedRaw}
                onChange={(e) => setAdvancedRaw(e.target.value)}
                placeholder="5m.sma:length=20[0]"
                className="flex-1 rounded border border-border bg-bg-inset px-2 py-1 font-mono text-[11px] focus:border-accent focus:outline-none"
              />
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={!advancedRaw.trim()}
                onClick={() => emit(advancedRaw)}
              >
                Insert
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function FeatureRow({
  item,
  onInsert,
}: {
  item: FeatureCatalogItem;
  onInsert: (ref: string) => void;
}): JSX.Element {
  const supportedTfs = item.supported_timeframes?.length ? item.supported_timeframes : ["5m"];
  const offered = PILL_TIMEFRAMES.filter((tf) => supportedTfs.includes(tf));
  const pills = offered.length > 0 ? offered : (supportedTfs.slice(0, 3) as readonly string[]);

  function handlePill(timeframe: string): void {
    onInsert(buildDefaultExpression(item, timeframe));
  }

  return (
    <div className="flex items-start justify-between gap-2 px-3 py-1.5 hover:bg-bg-inset/50">
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="font-mono text-[12px] text-fg">{item.kind}</span>
          {item.display_name && item.display_name.toLowerCase() !== item.kind.toLowerCase() ? (
            <span className="text-[11px] text-fg-muted">· {item.display_name}</span>
          ) : null}
        </div>
        {item.description ? (
          <div className="truncate text-[10.5px] text-fg-subtle">{item.description}</div>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-1">
        {pills.map((tf) => (
          <button
            key={tf}
            type="button"
            onClick={() => handlePill(tf)}
            className="rounded-full border border-border bg-bg-raised px-1.5 py-0.5 font-mono text-[10px] hover:border-accent hover:text-fg"
            title={`Insert ${item.kind} at ${tf}`}
            aria-label={`Insert ${item.kind} at ${tf}`}
          >
            {tf}
          </button>
        ))}
      </div>
    </div>
  );
}

function buildDefaultExpression(item: FeatureCatalogItem, timeframe: string): string {
  const params: string[] = [];
  for (const key of (item.allowed_params ?? []).slice().sort()) {
    const dv = (item.default_params ?? {})[key];
    if (dv === undefined || dv === null || dv === "") continue;
    params.push(`${key}=${String(dv)}`);
  }
  const paramsPart = params.length > 0 ? `:${params.join(",")}` : "";
  return `${timeframe}.${item.kind}${paramsPart}[0]`;
}

function groupByNamespace(items: FeatureCatalogItem[]): [string, FeatureCatalogItem[]][] {
  const map = new Map<string, FeatureCatalogItem[]>();
  for (const item of items) {
    const ns = (item.namespace ?? "other").toLowerCase();
    const arr = map.get(ns) ?? [];
    arr.push(item);
    map.set(ns, arr);
  }
  const ordered: [string, FeatureCatalogItem[]][] = [];
  for (const ns of NAMESPACE_ORDER) {
    const list = map.get(ns);
    if (list) {
      ordered.push([ns, list.slice().sort((a, b) => a.kind.localeCompare(b.kind))]);
      map.delete(ns);
    }
  }
  for (const [ns, arr] of map) {
    ordered.push([ns, arr.slice().sort((a, b) => a.kind.localeCompare(b.kind))]);
  }
  return ordered;
}

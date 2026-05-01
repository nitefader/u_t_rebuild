/**
 * FeaturePalette — categorized left rail of expression features + exit block templates.
 * Feature entries are draggable to the Monaco editor (text/plain).
 * Exit block entries are draggable to ExitColumn (EXIT_DRAG_MIME).
 */

import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { listExpressionFeatures } from "@/api/strategiesV4";
import type { CatalogEntry } from "@/api/strategiesV4";
import { EXIT_TEMPLATES } from "./exitTemplates";
import { EXIT_DRAG_MIME, serializeExitDrag } from "./exitDragPayload";

export interface FeaturePaletteProps {
  /** Called when user drags a feature entry. Payload is the text to insert. */
  onDragStart?: (insertText: string) => void;
  /** Called when user clicks a feature entry (alternative to drag). */
  onInsert?: (insertText: string) => void;
}

type PaletteTab = "features" | "exits";

const CATEGORY_LABELS: Record<string, string> = {
  trend: "Trend",
  momentum: "Momentum",
  volatility: "Volatility",
  volume: "Volume",
  bb: "Bollinger",
  time: "Time / Session",
  bar: "Bar / Price",
  other: "Other",
};

function buildInsertText(entry: CatalogEntry): string {
  if (entry.arity === 0) {
    return entry.timeframe_bound ? `5m.${entry.name}` : entry.name;
  }
  const params = entry.arg_names.map((a, i) => entry.arg_defaults[i] ?? a).join(", ");
  if (entry.timeframe_bound) {
    return `5m.${entry.name}(${params})`;
  }
  return `${entry.name}(${params})`;
}

function PaletteEntry({
  entry,
  onDragStart,
  onClick,
}: {
  entry: CatalogEntry;
  onDragStart?: (text: string) => void;
  onClick?: (text: string) => void;
}): JSX.Element {
  const insertText = buildInsertText(entry);

  return (
    <div
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData("text/plain", insertText);
        e.dataTransfer.effectAllowed = "copy";
        onDragStart?.(insertText);
      }}
      onClick={() => onClick?.(insertText)}
      title={entry.description}
      className="group flex cursor-grab items-center gap-2 rounded px-2 py-1 hover:bg-bg-raised active:cursor-grabbing"
      role="option"
      aria-label={`${entry.name}: ${entry.description}`}
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick?.(insertText);
        }
      }}
    >
      <span className="min-w-0 truncate font-mono text-xs text-ai group-hover:text-ai/80">
        {entry.name}
      </span>
      <span className="ml-auto shrink-0 text-[10px] text-fg-subtle">{entry.return_type}</span>
    </div>
  );
}

export function FeaturePalette({ onDragStart, onInsert }: FeaturePaletteProps): JSX.Element {
  const [features, setFeatures] = useState<CatalogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set(Object.keys(CATEGORY_LABELS)));
  const [activeTab, setActiveTab] = useState<PaletteTab>("features");

  useEffect(() => {
    listExpressionFeatures()
      .then((data) => {
        setFeatures(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return features;
    return features.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        f.namespace.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q),
    );
  }, [features, query]);

  const byCategory = useMemo(() => {
    const map = new Map<string, CatalogEntry[]>();
    for (const entry of filtered) {
      const cat = entry.category;
      if (!map.has(cat)) map.set(cat, []);
      map.get(cat)!.push(entry);
    }
    return map;
  }, [filtered]);

  function toggleCategory(cat: string): void {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  }

  if (loading) {
    return (
      <div className="flex h-full flex-col gap-1 p-3">
        {[...Array<null>(6)].map((_, i) => (
          <div key={i} className="h-5 animate-pulse rounded bg-bg-raised" />
        ))}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Tab strip */}
      <div className="flex shrink-0 gap-1 border-b border-border px-3 pt-2 pb-0">
        <button
          type="button"
          onClick={() => setActiveTab("features")}
          className={`rounded-t px-3 py-1.5 text-xs font-semibold focus:outline-none ${
            activeTab === "features"
              ? "border border-b-0 border-border bg-bg text-accent"
              : "text-fg-subtle hover:text-fg-muted"
          }`}
          aria-pressed={activeTab === "features"}
        >
          Features
        </button>
        <button
          type="button"
          onClick={() => setActiveTab("exits")}
          className={`rounded-t px-3 py-1.5 text-xs font-semibold focus:outline-none ${
            activeTab === "exits"
              ? "border border-b-0 border-border bg-bg text-accent"
              : "text-fg-subtle hover:text-fg-muted"
          }`}
          aria-pressed={activeTab === "exits"}
          data-testid="exit-blocks-tab"
        >
          Exit blocks
        </button>
      </div>

      {activeTab === "features" ? (
        <>
          <div className="flex-shrink-0 px-3 pt-3 pb-2">
            <div className="flex items-center gap-2 rounded border border-border bg-bg-inset px-2 py-1.5">
              <Search className="h-3.5 w-3.5 shrink-0 text-fg-subtle" aria-hidden="true" />
              <input
                type="search"
                placeholder="Search features…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="min-w-0 flex-1 bg-transparent text-xs text-fg placeholder-fg-subtle focus:outline-none"
                aria-label="Search features"
              />
            </div>
          </div>
          <div
            className="flex-1 overflow-y-auto px-1 pb-4"
            role="listbox"
            aria-label="Feature palette"
          >
            {byCategory.size === 0 ? (
              <p className="px-3 py-4 text-xs text-fg-subtle">No features match.</p>
            ) : (
              Array.from(byCategory.entries()).map(([cat, entries]) => (
                <div key={cat} className="mb-1">
                  <button
                    className="flex w-full items-center justify-between px-2 py-1 text-left text-xs font-semibold uppercase tracking-wider text-fg-subtle hover:text-fg-muted focus:outline-none"
                    onClick={() => toggleCategory(cat)}
                    aria-expanded={expanded.has(cat)}
                  >
                    <span>{CATEGORY_LABELS[cat] ?? cat}</span>
                    <span className="text-[10px]">{expanded.has(cat) ? "▲" : "▼"}</span>
                  </button>
                  {expanded.has(cat)
                    ? entries.map((entry) => (
                        <PaletteEntry
                          key={entry.key}
                          entry={entry}
                          onDragStart={onDragStart}
                          onClick={onInsert}
                        />
                      ))
                    : null}
                </div>
              ))
            )}
          </div>
        </>
      ) : (
        <div
          className="flex-1 overflow-y-auto px-2 py-3 flex flex-col gap-2"
          role="list"
          aria-label="Exit blocks palette"
        >
          <p className="px-1 pb-1 text-[10px] uppercase tracking-wider text-fg-subtle font-semibold">
            Logical exit blocks
          </p>
          {EXIT_TEMPLATES.map((tpl) => (
            <div
              key={tpl.id}
              draggable
              role="listitem"
              data-testid={`exit-palette-item-${tpl.id}`}
              onDragStart={(e) => {
                e.dataTransfer.setData(EXIT_DRAG_MIME, serializeExitDrag(tpl.id));
                e.dataTransfer.effectAllowed = "copy";
              }}
              className="flex cursor-grab items-start gap-2 rounded-lg border border-border-strong bg-bg-subtle px-3 py-2 hover:border-accent/60 hover:bg-bg-raised active:cursor-grabbing"
              title={tpl.description}
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-xs font-semibold text-accent">{tpl.label}</p>
                <p className="mt-0.5 text-[10px] text-fg-subtle leading-tight line-clamp-2">
                  {tpl.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

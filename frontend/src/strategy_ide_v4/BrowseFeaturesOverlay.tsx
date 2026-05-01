/**
 * BrowseFeaturesOverlay — full-screen searchable feature list.
 * Triggered by Ctrl+Space; click inserts into editor and closes.
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Search, X } from "lucide-react";
import { listExpressionFeatures } from "@/api/strategiesV4";
import type { CatalogEntry } from "@/api/strategiesV4";

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

export interface BrowseFeaturesOverlayProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onInsert: (text: string) => void;
}

export function BrowseFeaturesOverlay({
  open,
  onOpenChange,
  onInsert,
}: BrowseFeaturesOverlayProps): JSX.Element {
  const [features, setFeatures] = useState<CatalogEntry[]>([]);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActiveIndex(0);
      listExpressionFeatures()
        .then(setFeatures)
        .catch(() => undefined);
      // Focus search input after animation frame
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return features;
    return features.filter(
      (f) =>
        f.name.toLowerCase().includes(q) ||
        f.namespace.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q) ||
        f.description.toLowerCase().includes(q),
    );
  }, [features, query]);

  function handleKeyDown(e: React.KeyboardEvent): void {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const entry = filtered[activeIndex];
      if (entry) {
        onInsert(buildInsertText(entry));
        onOpenChange(false);
      }
    } else if (e.key === "Escape") {
      onOpenChange(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Dialog.Content
          className="fixed left-1/2 top-16 z-50 w-full max-w-2xl -translate-x-1/2 rounded-2xl border border-border bg-bg-subtle shadow-2xl outline-none"
          onKeyDown={handleKeyDown}
          aria-label="Browse features"
        >
          <Dialog.Title className="sr-only">Browse Expression Features</Dialog.Title>
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <Search className="h-4 w-4 shrink-0 text-fg-subtle" aria-hidden="true" />
            <input
              ref={searchRef}
              type="search"
              placeholder="Search features — press Enter to insert, Esc to close"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActiveIndex(0);
              }}
              className="flex-1 bg-transparent text-sm text-fg placeholder-fg-subtle focus:outline-none"
              aria-label="Filter features"
            />
            <Dialog.Close asChild>
              <button
                className="shrink-0 rounded p-1 text-fg-subtle hover:bg-bg-raised hover:text-fg focus:outline-none"
                aria-label="Close feature browser"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </Dialog.Close>
          </div>

          <div
            className="max-h-[60vh] overflow-y-auto py-2"
            role="listbox"
            aria-label="Feature list"
          >
            {filtered.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-fg-subtle">No features match.</p>
            ) : (
              filtered.map((entry, i) => (
                <button
                  key={entry.key}
                  role="option"
                  aria-selected={i === activeIndex}
                  className={`flex w-full items-start gap-3 px-4 py-2 text-left transition-colors focus:outline-none ${
                    i === activeIndex ? "bg-bg-raised" : "hover:bg-bg-raised/60"
                  }`}
                  onClick={() => {
                    onInsert(buildInsertText(entry));
                    onOpenChange(false);
                  }}
                  onMouseEnter={() => setActiveIndex(i)}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-semibold text-ai">
                        {entry.name}
                      </span>
                      <span className="text-xs text-fg-subtle">
                        {CATEGORY_LABELS[entry.category] ?? entry.category}
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-xs text-fg-muted">{entry.description}</p>
                  </div>
                  <span className="shrink-0 font-mono text-xs text-accent">
                    {entry.return_type}
                  </span>
                </button>
              ))
            )}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

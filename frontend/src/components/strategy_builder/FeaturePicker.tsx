import { useEffect, useMemo, useState } from "react";
import * as Popover from "@radix-ui/react-popover";
import { ChevronDown, Search, X } from "lucide-react";
import type { FeatureCatalogItem } from "@/api/schemas/strategyComposer";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { cn } from "@/lib/cn";

/**
 * FeaturePicker — catalog-driven combobox + parameter form.
 *
 * Replaces the bare text field that used to demand operators type
 * `5m.sma:length=20[0]` from memory. Workflow:
 *
 *   1. Click the field → popover opens with a search box and the
 *      registry catalog grouped by namespace (Price / Technical /
 *      Session / Portfolio).
 *   2. Pick a kind → an inline param form renders with the right
 *      controls per allowed_param (length → number, source/session →
 *      enum dropdown, lookback → number).
 *   3. The picker emits a canonical feature ref string
 *      (`5m.sma:length=20[0]`) so the rest of the builder + backend
 *      validator stay on the same wire format.
 *
 * Operators may still paste a hand-typed expression — the popover
 * keeps a "Use raw expression" escape hatch so power users aren't
 * gated by the dropdowns.
 */
export interface FeaturePickerProps {
  value: string;
  onChange: (next: string) => void;
  catalog: FeatureCatalogItem[];
  consumer?: string;
  invalid?: boolean;
  invalidMessage?: string | null;
  disabled?: boolean;
  placeholder?: string;
  /** Render compact (pill-sized) — used inside ConditionRow. */
  compact?: boolean;
  /** Optional id passed to the trigger so labels can associate. */
  id?: string;
}

const PARAM_ENUMS: Record<string, string[]> = {
  source: ["close", "open", "high", "low", "hlc", "hlcv"],
  session: ["regular", "premarket", "afterhours", "extended"],
};

const NAMESPACE_ORDER = ["price", "technical", "session", "portfolio"] as const;
const NAMESPACE_LABEL: Record<string, string> = {
  price: "Price",
  technical: "Technical",
  session: "Session",
  portfolio: "Portfolio",
};

export function FeaturePicker(props: FeaturePickerProps): JSX.Element {
  const {
    value,
    onChange,
    catalog,
    consumer = "backtest",
    invalid,
    invalidMessage,
    disabled,
    placeholder,
    compact,
    id,
  } = props;

  const [open, setOpen] = useState(false);

  return (
    <Popover.Root open={open && !disabled} onOpenChange={(next) => !disabled && setOpen(next)}>
      <Popover.Trigger asChild>
        <button
          type="button"
          id={id}
          disabled={disabled}
          className={cn(
            "inline-flex items-center gap-1 rounded-full border font-mono",
            compact ? "px-2 py-0.5 text-[11px]" : "px-2.5 py-1 text-xs",
            invalid
              ? "border-danger bg-danger-subtle/40"
              : value
                ? "border-border bg-bg-inset hover:border-accent/60"
                : "border-dashed border-border/70 bg-bg-inset/40 text-fg-muted hover:border-accent/60",
            disabled ? "cursor-not-allowed opacity-60" : "cursor-pointer",
          )}
          title={invalid ? invalidMessage ?? "Invalid feature reference" : value || placeholder}
        >
          <span className={cn("truncate", compact ? "max-w-[24ch]" : "max-w-[36ch]")}>
            {value || placeholder || "pick feature"}
          </span>
          <ChevronDown className={cn(compact ? "h-3 w-3" : "h-3.5 w-3.5")} aria-hidden="true" />
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={6}
          className="z-50 w-[420px] rounded-md border border-border bg-bg-raised p-0 shadow-raised focus:outline-none"
        >
          <FeaturePickerBody
            value={value}
            onChange={(next) => {
              onChange(next);
              setOpen(false);
            }}
            catalog={catalog}
            consumer={consumer}
          />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

interface BodyProps {
  value: string;
  onChange: (next: string) => void;
  catalog: FeatureCatalogItem[];
  consumer: string;
}

function FeaturePickerBody(props: BodyProps): JSX.Element {
  const { value, onChange, catalog, consumer } = props;
  const [query, setQuery] = useState("");
  const [picked, setPicked] = useState<FeatureCatalogItem | null>(null);
  const [draftRaw, setDraftRaw] = useState(value);

  // When the popover reopens for a different value, refresh the local raw
  // expression so the "Use raw expression" tab matches what the field shows.
  useEffect(() => {
    setDraftRaw(value);
  }, [value]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return catalog.filter((c) => {
      if (!c.supported_consumers?.length || c.supported_consumers.includes(consumer)) {
        if (!q) return true;
        const hay = [c.kind, c.display_name ?? "", c.description ?? "", c.namespace ?? ""].join(" ").toLowerCase();
        return hay.includes(q);
      }
      return false;
    });
  }, [catalog, consumer, query]);

  const grouped = useMemo(() => groupByNamespace(filtered), [filtered]);

  return (
    <div className="flex max-h-[460px] w-full flex-col">
      <div className="border-b border-border/70 p-2">
        <div className="flex items-center gap-2 rounded border border-border bg-bg-inset px-2 py-1">
          <Search className="h-3.5 w-3.5 text-fg-muted" aria-hidden="true" />
          <input
            type="text"
            autoFocus
            placeholder="Search features (e.g. ema, rsi, vwap, opening range)…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="flex-1 bg-transparent text-xs outline-none"
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
      {picked ? (
        <FeatureParamForm
          item={picked}
          onCancel={() => setPicked(null)}
          onApply={(ref) => onChange(ref)}
        />
      ) : (
        <>
          <div className="flex-1 overflow-y-auto py-1">
            {grouped.length === 0 ? (
              <div className="px-3 py-6 text-center text-xs text-fg-muted">
                No features match &ldquo;{query}&rdquo;. Try a shorter term or use the raw expression below.
              </div>
            ) : (
              grouped.map(([namespace, items]) => (
                <div key={namespace} className="py-1">
                  <div className="sticky top-0 z-[1] bg-bg-raised px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                    {NAMESPACE_LABEL[namespace] ?? namespace}
                  </div>
                  {items.map((c) => (
                    <button
                      key={c.kind}
                      type="button"
                      onClick={() => setPicked(c)}
                      className="flex w-full items-start justify-between gap-2 px-3 py-1.5 text-left text-xs hover:bg-bg-subtle"
                    >
                      <span className="min-w-0">
                        <span className="font-mono text-[12px] text-fg">{c.kind}</span>
                        {c.display_name && c.display_name.toLowerCase() !== c.kind.toLowerCase() ? (
                          <span className="ml-1 text-fg-muted">· {c.display_name}</span>
                        ) : null}
                        {c.description ? (
                          <span className="block truncate text-[10px] text-fg-subtle">{c.description}</span>
                        ) : null}
                      </span>
                    </button>
                  ))}
                </div>
              ))
            )}
          </div>
          <div className="border-t border-border/70 p-2">
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
              Or paste a raw expression
            </div>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={draftRaw}
                onChange={(e) => setDraftRaw(e.target.value)}
                placeholder="5m.sma:length=20[0]"
                className="flex-1 rounded border border-border bg-bg-inset px-2 py-1 font-mono text-[11px] focus:border-accent focus:outline-none"
              />
              <Button
                type="button"
                size="sm"
                variant="secondary"
                disabled={!draftRaw.trim()}
                onClick={() => onChange(draftRaw.trim())}
              >
                Use
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

interface FeatureParamFormProps {
  item: FeatureCatalogItem;
  onCancel: () => void;
  onApply: (ref: string) => void;
}

function FeatureParamForm({ item, onCancel, onApply }: FeatureParamFormProps): JSX.Element {
  const supportedTimeframes = item.supported_timeframes?.length ? item.supported_timeframes : ["5m"];
  const [timeframe, setTimeframe] = useState<string>(
    supportedTimeframes.includes("5m") ? "5m" : supportedTimeframes[0]!,
  );
  const [params, setParams] = useState<Record<string, string>>(() => {
    const out: Record<string, string> = {};
    for (const p of item.allowed_params ?? []) {
      const dv = (item.default_params ?? {})[p];
      out[p] = dv === undefined || dv === null ? "" : String(dv);
    }
    return out;
  });
  const [lookback, setLookback] = useState<string>("0");

  const expression = useMemo(
    () => buildExpression(item.kind, timeframe, params, lookback),
    [item.kind, timeframe, params, lookback],
  );

  return (
    <div className="space-y-3 p-3 text-xs">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="font-mono text-[12px]">{item.kind}</span>
            {item.display_name && item.display_name.toLowerCase() !== item.kind.toLowerCase() ? (
              <span className="text-fg-muted">· {item.display_name}</span>
            ) : null}
          </div>
          {item.description ? (
            <div className="mt-0.5 text-[10px] text-fg-subtle">{item.description}</div>
          ) : null}
          <div className="mt-1 flex flex-wrap items-center gap-1">
            <StatusBadge tone="muted">{item.namespace}</StatusBadge>
            <StatusBadge tone="muted">{item.scope}</StatusBadge>
          </div>
        </div>
        <button
          type="button"
          onClick={onCancel}
          className="rounded p-1 text-fg-muted hover:bg-bg-subtle hover:text-fg"
          aria-label="Back to feature list"
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-fg-muted">Timeframe</span>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="mt-0.5 block w-full rounded border border-border bg-bg-inset px-1.5 py-1 text-xs focus:border-accent focus:outline-none"
          >
            {supportedTimeframes.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[10px] uppercase tracking-wide text-fg-muted">Lookback (bars)</span>
          <input
            type="number"
            min={0}
            value={lookback}
            onChange={(e) => setLookback(e.target.value.replace(/[^0-9]/g, ""))}
            className="mt-0.5 block w-full rounded border border-border bg-bg-inset px-1.5 py-1 font-mono text-xs focus:border-accent focus:outline-none"
          />
        </label>
        {(item.allowed_params ?? []).map((p) => (
          <label key={p} className="block">
            <span className="text-[10px] uppercase tracking-wide text-fg-muted">{p}</span>
            {PARAM_ENUMS[p] ? (
              <select
                value={params[p] ?? ""}
                onChange={(e) => setParams((prev) => ({ ...prev, [p]: e.target.value }))}
                className="mt-0.5 block w-full rounded border border-border bg-bg-inset px-1.5 py-1 text-xs focus:border-accent focus:outline-none"
              >
                {PARAM_ENUMS[p]!.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={params[p] ?? ""}
                onChange={(e) => setParams((prev) => ({ ...prev, [p]: e.target.value }))}
                placeholder={String((item.default_params ?? {})[p] ?? "")}
                className="mt-0.5 block w-full rounded border border-border bg-bg-inset px-1.5 py-1 font-mono text-xs focus:border-accent focus:outline-none"
              />
            )}
          </label>
        ))}
      </div>

      <div>
        <div className="text-[10px] uppercase tracking-wide text-fg-muted">Canonical expression</div>
        <div className="mt-0.5 rounded border border-border bg-bg-inset px-2 py-1 font-mono text-[11px]">
          {expression}
        </div>
      </div>

      <div className="flex items-center justify-end gap-2">
        <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          type="button"
          size="sm"
          variant="primary"
          disabled={!expression}
          onClick={() => onApply(expression)}
        >
          Use feature
        </Button>
      </div>
    </div>
  );
}

function buildExpression(
  kind: string,
  timeframe: string,
  params: Record<string, string>,
  lookback: string,
): string {
  const tf = timeframe.trim() || "5m";
  const paramSegments: string[] = [];
  for (const key of Object.keys(params).sort()) {
    const raw = params[key]?.trim();
    if (!raw) continue;
    paramSegments.push(`${key}=${raw}`);
  }
  const paramsPart = paramSegments.length ? `:${paramSegments.join(",")}` : "";
  const lookbackPart = `[${lookback.trim() || "0"}]`;
  return `${tf}.${kind}${paramsPart}${lookbackPart}`;
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
    const items = map.get(ns);
    if (items) {
      ordered.push([ns, items.slice().sort((a, b) => a.kind.localeCompare(b.kind))]);
      map.delete(ns);
    }
  }
  for (const [ns, arr] of map) {
    ordered.push([ns, arr.slice().sort((a, b) => a.kind.localeCompare(b.kind))]);
  }
  return ordered;
}

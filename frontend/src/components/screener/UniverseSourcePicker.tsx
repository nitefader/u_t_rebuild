import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ScreenerApi } from "@/api/screener";
import { WatchlistsApi } from "@/api/watchlists";
import type {
  ScreenerUniverseSource,
  ScreenerUniverseSourceKind,
} from "@/api/schemas/screener";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";

/**
 * UniverseSourcePicker — pick where the Screener pulls candidate symbols
 * from before filtering. Three kinds:
 *
 *   - explicit: operator-typed comma-separated symbol list
 *   - preset: built-in named lists (Liquid Large Caps, Magnificent Seven…)
 *   - watchlist: pulls from an existing Watchlist by name (operator-readable
 *     picker; never asks for the UUID directly per the Human-Readable
 *     Frontend Data Rule)
 */
export interface UniverseSourcePickerProps {
  value: ScreenerUniverseSource;
  onChange: (next: ScreenerUniverseSource) => void;
}

export function UniverseSourcePicker(props: UniverseSourcePickerProps): JSX.Element {
  const { value, onChange } = props;
  const presets = useQuery({
    queryKey: ["screener", "presets"],
    queryFn: () => ScreenerApi.presets(),
    staleTime: 5 * 60_000,
  });
  const watchlists = useQuery({
    queryKey: ["watchlists", "list"],
    queryFn: () => WatchlistsApi.list(),
    staleTime: 60_000,
  });
  const marketLists = useQuery({
    queryKey: ["screener", "market-lists"],
    queryFn: () => ScreenerApi.marketLists(),
    staleTime: 5 * 60_000,
  });

  function setKind(kind: ScreenerUniverseSourceKind): void {
    if (kind === "explicit") onChange({ kind, symbols: value.symbols ?? [] });
    if (kind === "preset") {
      const firstPreset = presets.data?.presets[0]?.key ?? "liquid_large_caps";
      onChange({ kind, symbols: [], preset: firstPreset });
    }
    if (kind === "watchlist") {
      const firstId = watchlists.data?.watchlists[0]?.watchlist_id ?? null;
      onChange({ kind, symbols: [], watchlist_id: firstId });
    }
    if (kind === "market_list") {
      const firstKey = marketLists.data?.market_lists[0]?.key ?? "day_gainers";
      onChange({ kind, symbols: [], market_list_key: firstKey });
    }
  }

  const explicitValue = useMemo(
    () => (value.kind === "explicit" ? (value.symbols ?? []).join(", ") : ""),
    [value.kind, value.symbols],
  );
  const [explicitDraft, setExplicitDraft] = useState<string>(explicitValue);

  useEffect(() => {
    setExplicitDraft(explicitValue);
  }, [explicitValue]);

  function commitExplicit(text: string): void {
    setExplicitDraft(text);
    const symbols = text
      .split(/[,\s]+/)
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
    onChange({ kind: "explicit", symbols });
  }

  return (
    <div className="space-y-2 rounded border border-border bg-bg-inset/40 p-2">
      <div className="flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
          Universe source
        </span>
        <KindButton kind="explicit" current={value.kind} onClick={setKind} label="Explicit" />
        <KindButton kind="market_list" current={value.kind} onClick={setKind} label="Market List" />
        <KindButton kind="preset" current={value.kind} onClick={setKind} label="Preset" />
        <KindButton kind="watchlist" current={value.kind} onClick={setKind} label="Watchlist" />
      </div>
      {value.kind === "explicit" ? (
        <TextField
          label="Symbols (comma or space separated)"
          value={explicitDraft}
          onChange={(e) => commitExplicit(e.target.value)}
          placeholder="AAPL, MSFT, NVDA, TSLA"
          hint={`${(value.symbols ?? []).length} symbols`}
        />
      ) : null}
      {value.kind === "preset" ? (
        <div className="space-y-1">
          <Select
            label="Preset"
            value={value.preset ?? ""}
            onChange={(e) => onChange({ ...value, preset: e.target.value })}
          >
            {(presets.data?.presets ?? []).map((p) => (
              <option key={p.key} value={p.key}>
                {p.label} · {p.symbol_count} symbols
              </option>
            ))}
          </Select>
          {(() => {
            const sample = presets.data?.presets.find((p) => p.key === value.preset)?.sample_symbols ?? [];
            if (sample.length === 0) return null;
            return (
              <div className="flex flex-wrap gap-1 text-[10.5px]">
                <span className="text-fg-subtle">Sample:</span>
                {sample.map((s) => (
                  <StatusBadge key={s} tone="neutral">
                    {s}
                  </StatusBadge>
                ))}
              </div>
            );
          })()}
        </div>
      ) : null}
      {value.kind === "market_list" ? (
        <div className="space-y-1">
          <Select
            label="Alpaca Market List"
            value={value.market_list_key ?? ""}
            onChange={(e) => onChange({ ...value, market_list_key: e.target.value })}
          >
            {(marketLists.data?.market_lists ?? []).map((m) => (
              <option key={m.key} value={m.key}>
                {m.label} - {m.category}
              </option>
            ))}
          </Select>
          <div className="text-[10.5px] text-fg-subtle">
            Alpaca provider pack only. Runs create discovery evidence; they do not submit orders.
          </div>
        </div>
      ) : null}
      {value.kind === "watchlist" ? (
        watchlists.data && watchlists.data.watchlists.length > 0 ? (
          <Select
            label="Watchlist"
            value={value.watchlist_id ?? ""}
            onChange={(e) => onChange({ ...value, watchlist_id: e.target.value || null })}
          >
            {watchlists.data.watchlists.map((w) => (
              <option key={w.watchlist_id} value={w.watchlist_id}>
                {w.name} · {(w.static_symbols ?? []).length} symbols
              </option>
            ))}
          </Select>
        ) : (
          <div className="rounded border border-dashed border-border px-3 py-2 text-[11px] text-fg-muted">
            No Watchlists yet. Create one on the Watchlists page first.
          </div>
        )
      ) : null}
    </div>
  );
}

function KindButton({
  kind,
  current,
  onClick,
  label,
}: {
  kind: ScreenerUniverseSourceKind;
  current: ScreenerUniverseSourceKind;
  onClick: (k: ScreenerUniverseSourceKind) => void;
  label: string;
}): JSX.Element {
  const active = current === kind;
  return (
    <button
      type="button"
      onClick={() => onClick(kind)}
      className={
        active
          ? "rounded border border-accent bg-accent/20 px-2 py-0.5 text-[11px] text-accent"
          : "rounded border border-border bg-bg-raised px-2 py-0.5 text-[11px] text-fg-muted hover:text-fg"
      }
    >
      {label}
    </button>
  );
}

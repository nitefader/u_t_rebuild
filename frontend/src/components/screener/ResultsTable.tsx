import { useMemo, useState } from "react";
import type {
  ScreenerMetric,
  ScreenerMetricDefinition,
  ScreenerResultRow,
} from "@/api/schemas/screener";
import { StatusBadge, type StatusTone } from "@/components/badges/StatusBadge";
import { Sparkline } from "./Sparkline";
import { cn } from "@/lib/cn";
import { formatFieldValue } from "./criterionFormat";

/**
 * ResultsTable: chart-first Screener result grid.
 *
 * The grid handles both numeric feature fields and broker capability fields.
 * Screener rows are discovery evidence only; no table action submits orders.
 */
export interface ResultsTableProps {
  results: ScreenerResultRow[];
  metrics: ScreenerMetricDefinition[];
  /** Optional metric subset to render. Defaults to "shown if any row has a value". */
  shownMetrics?: ScreenerMetric[];
}

export function ResultsTable(props: ResultsTableProps): JSX.Element {
  const { results, metrics } = props;
  const [metricPreset, setMetricPreset] = useState<"trader" | "audit" | "all">("trader");
  const [matchedOnly, setMatchedOnly] = useState(false);

  const visibleMetricKeys: ScreenerMetric[] = useMemo(() => {
    if (props.shownMetrics?.length) return props.shownMetrics;
    const seen = new Set<ScreenerMetric>();
    for (const row of results) {
      for (const k of Object.keys(row.metrics)) {
        if (row.metrics[k] !== null && row.metrics[k] !== undefined) {
          seen.add(k as ScreenerMetric);
        }
      }
    }
    const allVisible = metrics
      .map((m) => m.key as ScreenerMetric)
      .filter((k) => seen.has(k));
    if (metricPreset === "all") return allVisible;
    const preset = metricPreset === "audit" ? AUDIT_METRICS : TRADER_METRICS;
    return preset.filter((key) => allVisible.includes(key));
  }, [props.shownMetrics, results, metrics, metricPreset]);

  const [sortColumn, setSortColumn] = useState<"symbol" | "matched" | ScreenerMetric>("matched");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const displayedResults = useMemo(
    () => (matchedOnly ? results.filter((row) => row.matched) : results),
    [matchedOnly, results],
  );
  const matchedCount = useMemo(() => results.filter((row) => row.matched).length, [results]);

  const sorted = useMemo(() => {
    const arr = [...displayedResults];
    arr.sort((a, b) => {
      const aV = sortValue(a, sortColumn);
      const bV = sortValue(b, sortColumn);
      const cmp = compare(aV, bV);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [displayedResults, sortColumn, sortDir]);

  function header(key: typeof sortColumn, label: string, align: "left" | "right" = "left"): JSX.Element {
    const active = sortColumn === key;
    return (
      <th
        key={String(key)}
        scope="col"
        className={cn(
          "cursor-pointer select-none px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-fg-muted",
          align === "right" ? "text-right" : "text-left",
        )}
        onClick={() => {
          if (active) setSortDir(sortDir === "asc" ? "desc" : "asc");
          else {
            setSortColumn(key);
            setSortDir(key === "symbol" ? "asc" : "desc");
          }
        }}
      >
        {label} {active ? (sortDir === "asc" ? "^" : "v") : null}
      </th>
    );
  }

  if (results.length === 0) {
    return (
      <div className="rounded border border-dashed border-border px-3 py-2 text-[11px] text-fg-muted">
        No results. Run the screener to populate this table.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
        <div className="flex flex-wrap items-center gap-1">
          <span className="text-fg-muted">Columns</span>
          {(["trader", "audit", "all"] as const).map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => setMetricPreset(preset)}
              className={
                metricPreset === preset
                  ? "rounded border border-accent bg-accent/20 px-2 py-0.5 text-accent"
                  : "rounded border border-border bg-bg-raised px-2 py-0.5 text-fg-muted hover:text-fg"
              }
            >
              {preset === "trader" ? "Trader" : preset === "audit" ? "Audit" : "All"}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-fg-muted">
            Showing {displayedResults.length} of {results.length}; {matchedCount} matched
          </span>
          <button
            type="button"
            onClick={() => setMatchedOnly((current) => !current)}
            className={
              matchedOnly
                ? "rounded border border-accent bg-accent/20 px-2 py-0.5 text-accent"
                : "rounded border border-border bg-bg-raised px-2 py-0.5 text-fg-muted hover:text-fg"
            }
          >
            {matchedOnly ? "Show all rows" : "Show matches only"}
          </button>
        </div>
      </div>
      <div className="overflow-x-auto rounded border border-border">
        <table className="ut-table">
          <thead>
            <tr>
              {header("matched", "Match")}
              {header("symbol", "Symbol")}
              <th className="px-2 py-1 text-left text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                Company / capability
              </th>
              <th className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                30-bar trail
              </th>
              {visibleMetricKeys.map((k) => {
                const def = metrics.find((m) => m.key === k);
                return header(k, def?.label ?? k, "right");
              })}
              <th className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
                Decision reason
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.symbol} className={row.matched ? "" : "opacity-60"}>
                <td className="px-2 py-1">
                  {row.matched ? (
                    <StatusBadge tone="ok">match</StatusBadge>
                  ) : (
                    <StatusBadge tone="muted">no</StatusBadge>
                  )}
                </td>
                <td className="px-2 py-1 font-medium">{row.symbol}</td>
                <td className="px-2 py-1 text-[11px]">
                  <div className="max-w-48 truncate text-fg">
                    {typeof row.metrics["broker.name"] === "string" && row.metrics["broker.name"]
                      ? row.metrics["broker.name"]
                      : "-"}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-1">
                    {capabilityBadges(row).map((badge) => (
                      <StatusBadge key={badge.label} tone={badge.tone} size="sm">
                        {badge.label}
                      </StatusBadge>
                    ))}
                  </div>
                </td>
                <td className="px-2 py-1">
                  <Sparkline values={row.sparkline ?? []} />
                </td>
                {visibleMetricKeys.map((k) => {
                  const value = row.metrics[k] ?? null;
                  const unit = metrics.find((m) => m.key === k)?.unit ?? "";
                  return (
                    <td key={k} className="px-2 py-1 text-right font-mono text-[11px]">
                      {value === null ? "-" : formatValue(value, unit)}
                    </td>
                  );
                })}
                <td className="px-2 py-1 text-[11px] text-fg-muted">{decisionReason(row)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

const TRADER_METRICS: ScreenerMetric[] = [
  "price",
  "change_pct",
  "gap_pct",
  "relative_volume",
  "avg_volume_20d",
  "rsi_14",
  "atr_14_pct",
];

const AUDIT_METRICS: ScreenerMetric[] = [
  "price",
  "relative_volume",
  "broker.tradable",
  "broker.fractionable",
  "broker.shortable",
  "broker.easy_to_borrow",
  "broker.active",
  "broker.exchange",
  "broker.asset_class",
];

function sortValue(row: ScreenerResultRow, col: "symbol" | "matched" | ScreenerMetric): number | string {
  if (col === "symbol") return row.symbol;
  if (col === "matched") return row.matched ? 1 : 0;
  const value = row.metrics[col];
  if (typeof value === "number") return value;
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? 1 : 0;
  return Number.NEGATIVE_INFINITY;
}

function compare(a: number | string, b: number | string): number {
  if (typeof a === "string" && typeof b === "string") return a.localeCompare(b);
  if (a === b) return 0;
  return a > b ? 1 : -1;
}

function formatValue(value: number | string | boolean, unit: string): string {
  const formatted = formatFieldValue(value, unit);
  if (typeof value === "number" && unit === "%" && value > 0) return `+${formatted}`;
  return formatted;
}

function capabilityBadges(row: ScreenerResultRow): { label: string; tone: StatusTone }[] {
  const badges: { label: string; tone: StatusTone }[] = [];
  const capabilityEvidence = row.evidence?.asset_capability;
  if (
    capabilityEvidence &&
    typeof capabilityEvidence === "object" &&
    "unavailable_reason" in capabilityEvidence &&
    capabilityEvidence.unavailable_reason
  ) {
    badges.push({ label: "capability unavailable", tone: "warn" });
  }
  const pairs: [key: string, label: string][] = [
    ["broker.tradable", "tradable"],
    ["broker.fractionable", "fractionable"],
    ["broker.shortable", "shortable"],
    ["broker.easy_to_borrow", "easy borrow"],
    ["broker.active", "active"],
  ];
  for (const [key, label] of pairs) {
    const value = row.metrics[key];
    if (typeof value !== "boolean") continue;
    badges.push({ label, tone: value ? "ok" : "muted" });
  }
  const exchange = row.metrics["broker.exchange"];
  if (typeof exchange === "string" && exchange) {
    badges.push({ label: exchange, tone: "neutral" });
  }
  const assetClass = row.metrics["broker.asset_class"];
  if (typeof assetClass === "string" && assetClass) {
    badges.push({ label: assetClass, tone: "info" });
  }
  return badges.slice(0, 6);
}

function decisionReason(row: ScreenerResultRow): string {
  const reasons = [
    ...evidenceWarnings(row),
    ...row.blocked_reasons,
    ...row.failed_criteria,
  ].filter(Boolean);
  if (reasons.length > 0) return reasons.slice(0, 3).join(" / ");
  if (row.matched && row.passed_criteria.length > 0) {
    return `Passed: ${row.passed_criteria.slice(0, 2).join(" / ")}`;
  }
  return "-";
}

function evidenceWarnings(row: ScreenerResultRow): string[] {
  const warnings: string[] = [];
  const capabilityEvidence = row.evidence?.asset_capability;
  if (
    capabilityEvidence &&
    typeof capabilityEvidence === "object" &&
    "unavailable_reason" in capabilityEvidence &&
    capabilityEvidence.unavailable_reason
  ) {
    warnings.push(`Alpaca capability unavailable: ${String(capabilityEvidence.unavailable_reason)}`);
  }
  const barError = row.evidence?.error;
  if (typeof barError === "string" && barError.trim()) {
    warnings.push(barError);
  }
  return warnings;
}

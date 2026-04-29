import { Card, CardBody, CardHeader, CardTitle, KpiCard } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import type { MonteCarloResult } from "@/api/schemas/researchRuns";

/**
 * MonteCarloCard — percentile bands + final-equity histogram.
 *
 * Backtest doctrine: the ledger drilldown is a table; the *primary* MC view
 * is a chart. We render the percentile bands as stacked KPIs and the final
 * equity histogram as a sparkline-style bar row. A future polish slice can
 * upgrade to a fan chart if operator wants.
 */
export function MonteCarloCard({ result }: { result: MonteCarloResult }): JSX.Element {
  const histogramMax =
    result.final_equity_histogram.reduce((max, bin) => Math.max(max, bin.count), 0) || 1;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Monte Carlo</CardTitle>
        <span className="text-xs text-fg-muted">
          method: <StatusBadge tone="info">{result.method}</StatusBadge> · {result.replications}{" "}
          replications · seed {result.seed}
        </span>
      </CardHeader>
      <CardBody className="space-y-4">
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <PercentileBand label="Terminal equity" band={result.terminal_equity} formatter={fmtMoney} />
          <PercentileBand label="Sharpe" band={result.sharpe} formatter={fmtNum} />
          <PercentileBand label="Max drawdown" band={result.max_drawdown} formatter={fmtPct} />
        </div>

        <div>
          <div className="mb-1 text-xs text-fg-muted">Final equity distribution</div>
          {result.final_equity_histogram.length === 0 ? (
            <div className="text-xs text-fg-subtle">no histogram bins reported.</div>
          ) : (
            <div className="flex h-24 items-end gap-1">
              {result.final_equity_histogram.map((bin, i) => {
                const heightPct = (bin.count / histogramMax) * 100;
                return (
                  <div
                    key={`${bin.bin_start}-${i}`}
                    className="flex-1 rounded-sm bg-accent/40"
                    style={{ height: `${heightPct}%` }}
                    title={`[${fmtMoney(bin.bin_start)} – ${fmtMoney(bin.bin_end)}] · count ${bin.count}`}
                  />
                );
              })}
            </div>
          )}
          {result.final_equity_histogram.length > 0 ? (
            <div className="mt-1 flex justify-between text-[10px] text-fg-subtle">
              <span>{fmtMoney(result.final_equity_histogram[0].bin_start)}</span>
              <span>
                {fmtMoney(
                  result.final_equity_histogram[result.final_equity_histogram.length - 1].bin_end,
                )}
              </span>
            </div>
          ) : null}
        </div>
      </CardBody>
    </Card>
  );
}

function PercentileBand({
  label,
  band,
  formatter,
}: {
  label: string;
  band: { p05?: number; p25?: number; p50?: number; p75?: number; p95?: number };
  formatter: (n: number | undefined) => string;
}): JSX.Element {
  return (
    <KpiCard
      label={label}
      value={formatter(band.p50)}
      sublabel={
        <span className="space-x-1 tabular text-[10px] text-fg-subtle">
          <span>p05 {formatter(band.p05)}</span>
          <span>·</span>
          <span>p25 {formatter(band.p25)}</span>
          <span>·</span>
          <span>p75 {formatter(band.p75)}</span>
          <span>·</span>
          <span>p95 {formatter(band.p95)}</span>
        </span>
      }
    />
  );
}

function fmtMoney(n: number | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

function fmtNum(n: number | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(3);
}

function fmtPct(n: number | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return `${pct.toFixed(2)}%`;
}

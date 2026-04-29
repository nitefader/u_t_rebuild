import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import type { OptimizationCandidate } from "@/api/schemas/researchRuns";

/**
 * CandidateTable — every parameter combination evaluated, sortable by score.
 *
 * The recommended row is tone-badged. Every row exposes `metrics` (the 11
 * standard backtest metrics) so operators can compare candidates beyond the
 * single-criterion score.
 */
export function CandidateTable({
  candidates,
  title = "Candidate landscape",
}: {
  candidates: OptimizationCandidate[];
  title?: string;
}): JSX.Element | null {
  if (!candidates.length) return null;
  const sorted = [...candidates].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <StatusBadge>{candidates.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        <table className="ut-table">
          <thead>
            <tr>
              <th>Parameters</th>
              <th>Score</th>
              <th>Sharpe</th>
              <th>Sortino</th>
              <th>Calmar</th>
              <th>Max-DD</th>
              <th>Hit rate</th>
              <th>Trades</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => {
              const m = (row.metrics ?? {}) as Record<string, unknown>;
              return (
                <tr key={`${formatParameters(row.parameters)}-${i}`}>
                  <td className="font-mono text-[11px]">{formatParameters(row.parameters)}</td>
                  <td className="tabular font-semibold">{fmtNum(row.score)}</td>
                  <td className="tabular">{fmtNum(m.sharpe as number)}</td>
                  <td className="tabular">{fmtNum(m.sortino as number)}</td>
                  <td className="tabular">{fmtNum(m.calmar as number)}</td>
                  <td className="tabular">{fmtPct(m.max_drawdown as number)}</td>
                  <td className="tabular">{fmtPct(m.hit_rate as number)}</td>
                  <td className="tabular text-fg-muted">{row.trade_count ?? 0}</td>
                  <td>
                    {row.recommended ? <StatusBadge tone="ok">winner</StatusBadge> : null}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

function formatParameters(params: Record<string, unknown>): string {
  const entries = Object.entries(params);
  if (!entries.length) return "—";
  return entries.map(([k, v]) => `${k}=${v}`).join(" · ");
}

function fmtNum(n: number | undefined | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(3);
}

function fmtPct(n: number | undefined | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  const pct = Math.abs(n) <= 1 ? n * 100 : n;
  return `${pct.toFixed(2)}%`;
}

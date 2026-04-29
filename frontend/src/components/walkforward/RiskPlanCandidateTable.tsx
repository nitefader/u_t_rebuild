import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import type { WalkForwardCandidateRow } from "@/api/schemas/researchRuns";

/**
 * RiskPlanCandidateTable.
 *
 * Full sweep landscape: every parameter combination with OOS Sharpe / max-DD /
 * stability / picked-in-folds count, sortable by score. The recommended row is
 * tone-badged and pinned to the top.
 */
export function RiskPlanCandidateTable({
  candidates,
  foldCount,
}: {
  candidates: WalkForwardCandidateRow[];
  foldCount: number;
}): JSX.Element | null {
  if (!candidates.length) {
    return null;
  }
  const sorted = [...candidates].sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Risk-plan candidate landscape</CardTitle>
        <StatusBadge>{candidates.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        <table className="ut-table">
          <thead>
            <tr>
              <th>Parameters</th>
              <th>Score</th>
              <th>OOS Sharpe</th>
              <th>OOS return</th>
              <th>OOS max-DD</th>
              <th>OOS hit rate</th>
              <th>Stability</th>
              <th>Picked</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row, i) => (
              <tr key={`${formatParameters(row.parameters)}-${i}`}>
                <td className="font-mono text-[11px]">{formatParameters(row.parameters)}</td>
                <td className="tabular font-semibold">{fmtNum(row.score)}</td>
                <td className="tabular">{fmtNum(row.oos_sharpe)}</td>
                <td className="tabular">{fmtPct(row.oos_return)}</td>
                <td className="tabular">{fmtPct(row.oos_max_dd)}</td>
                <td className="tabular">{fmtPct(row.oos_hit_rate)}</td>
                <td className="tabular">{fmtNum(row.stability)}</td>
                <td className="tabular text-fg-muted">
                  {row.picked_in_folds ?? 0} / {foldCount || 0}
                </td>
                <td>
                  {row.recommended ? <StatusBadge tone="ok">recommended</StatusBadge> : null}
                </td>
              </tr>
            ))}
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

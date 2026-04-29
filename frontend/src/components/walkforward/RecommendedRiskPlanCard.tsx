import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import type { WalkForwardRiskPlanRecommendation } from "@/api/schemas/researchRuns";
import { SaveAsRiskPlanButton } from "@/components/risk_plans/SaveAsRiskPlanButton";
import { recommendationToFormPrefill } from "@/components/risk_plans/recommendationPrefill";

/**
 * RecommendedRiskPlanCard.
 *
 * Surfaces the OOS-stable winner from the WF risk-plan parameter sweep, plus
 * the explanation of why this candidate beat the others. Operator clicks
 * "Save as Risk Plan" to mint a draft Risk Plan with
 * source=walk_forward_recommended.
 */
export function RecommendedRiskPlanCard({
  recommended,
  recommendation,
  strategyName,
}: {
  recommended: WalkForwardRiskPlanRecommendation | null | undefined;
  recommendation: string | null | undefined;
  strategyName?: string | null;
}): JSX.Element | null {
  if (!recommended) {
    return null;
  }
  const tone = decisionTone(recommendation ?? "needs_more_data");
  const oos = recommended.out_of_sample_metrics ?? {};
  const stab = recommended.stability_metrics ?? {};
  const dd = recommended.drawdown_metrics ?? {};
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recommended risk plan</CardTitle>
        <div className="flex items-center gap-2">
          <StatusBadge tone={tone}>{(recommendation ?? "needs_more_data").replace(/_/g, " ")}</StatusBadge>
          <SaveAsRiskPlanButton
            source="walk_forward_recommended"
            prefill={recommendationToFormPrefill(recommended, {
              namePrefix: "WF",
              strategyName: strategyName ?? null,
              tier: "balanced",
            })}
            aiSummary={
              recommended.explanation ?? "Walk-Forward recommended based on aggregated OOS metrics."
            }
            disabled={recommendation === "do_not_ship"}
            label="Save as Risk Plan"
          />
        </div>
      </CardHeader>
      <CardBody className="space-y-3 text-xs">
        <div>
          <div className="text-fg-muted">Parameters</div>
          <div className="mt-1 font-mono text-sm">{formatParameters(recommended.parameters)}</div>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Metric label="Score" value={fmtNum(recommended.score)} />
          <Metric label="OOS Sharpe (avg)" value={fmtNum(oos.oos_sharpe_avg as number | undefined)} />
          <Metric label="OOS return (avg)" value={fmtPct(oos.oos_return_avg as number | undefined)} />
          <Metric label="OOS hit rate (avg)" value={fmtPct(oos.oos_hit_rate_avg as number | undefined)} />
          <Metric label="OOS max-DD" value={fmtPct(dd.oos_max_dd as number | undefined)} />
          <Metric label="Stability" value={fmtNum(stab.stability as number | undefined)} />
          <Metric
            label="Picked in folds"
            value={`${stab.picked_in_folds ?? 0} of ${stab.fold_count ?? 0}`}
          />
        </div>
        {recommended.explanation ? (
          <div>
            <div className="text-fg-muted">Explanation</div>
            <p className="mt-1 leading-relaxed">{recommended.explanation}</p>
          </div>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Metric({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div>
      <div className="text-fg-muted">{label}</div>
      <div className="mt-0.5 tabular text-sm font-semibold">{value}</div>
    </div>
  );
}

function formatParameters(params: Record<string, unknown>): string {
  const entries = Object.entries(params);
  if (!entries.length) return "—";
  return entries.map(([k, v]) => `${k}=${v}`).join("  ·  ");
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

function decisionTone(decision: string): "ok" | "warn" | "danger" | "info" | "muted" {
  switch (decision) {
    case "ship_recommended":
      return "ok";
    case "do_not_ship":
      return "danger";
    case "needs_more_data":
      return "warn";
    default:
      return "muted";
  }
}

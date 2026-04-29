import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { PageHeader } from "./PageHeader";

/**
 * Components catalog — what the platform offers Strategies to compose
 * with. V1 ships an operator-readable list pulled from the backend
 * domain shapes; the in-app rules editor lands in a follow-up slice.
 */

interface ConditionItem {
  operator: string;
  description: string;
}

const CONDITION_OPERATORS: ConditionItem[] = [
  { operator: "gt / greater_than", description: "left > right" },
  { operator: "gte", description: "left ≥ right" },
  { operator: "lt / less_than", description: "left < right" },
  { operator: "lte", description: "left ≤ right" },
  { operator: "eq", description: "left == right" },
  { operator: "cross_above", description: "left crosses above right this bar" },
  { operator: "cross_below", description: "left crosses below right this bar" },
];

const SIGNAL_PLAN_INTENTS: { intent: string; doc: string }[] = [
  { intent: "open", doc: "Open a new position." },
  { intent: "close", doc: "Close 100% of the position." },
  { intent: "reduce", doc: "Reduce position by an explicit quantity / percent." },
  { intent: "target", doc: "Take profit at a target." },
  { intent: "stop", doc: "Exit on protective stop." },
  { intent: "trail", doc: "Trail the protective stop." },
  { intent: "breakeven", doc: "Move stop to breakeven." },
  { intent: "runner", doc: "Manage residual size after partials." },
  { intent: "logical_exit", doc: "Strategy-defined exit rule." },
];

const PARTICIPATION_DECISIONS: { decision: string; doc: string }[] = [
  { decision: "participate", doc: "Account accepts the SignalPlan and resolves quantity." },
  { decision: "ignore", doc: "Account silently ignores (e.g. symbol blocklist)." },
  { decision: "reject", doc: "Account explicitly rejects with operator-readable reason." },
  { decision: "defer", doc: "Account is paused or pending sync; defer for retry." },
  { decision: "requires_operator", doc: "Account flags the plan for operator review." },
];

export function Components(): JSX.Element {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Components"
        subtitle="Catalog of building blocks the platform provides to Strategies and the Account decision pipeline."
        explainSlug="components"
      />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Condition operators</CardTitle>
            <StatusBadge tone="info">Strategy authoring</StatusBadge>
          </CardHeader>
          <CardBody className="p-0">
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Operator</th>
                  <th>Meaning</th>
                </tr>
              </thead>
              <tbody>
                {CONDITION_OPERATORS.map((c) => (
                  <tr key={c.operator}>
                    <td className="font-mono">{c.operator}</td>
                    <td className="text-fg-muted">{c.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>SignalPlan intents</CardTitle>
            <StatusBadge tone="info">Lifecycle</StatusBadge>
          </CardHeader>
          <CardBody className="p-0">
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Intent</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {SIGNAL_PLAN_INTENTS.map((i) => (
                  <tr key={i.intent}>
                    <td className="font-mono">{i.intent}</td>
                    <td className="text-fg-muted">{i.doc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Account participation decisions</CardTitle>
            <StatusBadge tone="info">Account evaluator</StatusBadge>
          </CardHeader>
          <CardBody className="p-0">
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Decision</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {PARTICIPATION_DECISIONS.map((p) => (
                  <tr key={p.decision}>
                    <td className="font-mono">{p.decision}</td>
                    <td className="text-fg-muted">{p.doc}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Pipeline ownership</CardTitle>
            <StatusBadge tone="ai">Doctrine</StatusBadge>
          </CardHeader>
          <CardBody className="space-y-2 text-sm leading-relaxed text-fg/90">
            <p>
              Strategy → Deployment → SignalPlan → Account Evaluation → RiskResolver → Governor →
              OrderManager → BrokerAdapter → BrokerSync → Position.
            </p>
            <p className="text-xs text-fg-muted">
              SignalPlans are neutral. Final Account quantity begins at the RiskResolver. Governor
              is the final gate before BrokerAdapter. Only BrokerSync writes broker truth. AI is
              advisory only.
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

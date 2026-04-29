import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, ListChecks, ShieldAlert } from "lucide-react";
import { TimelinesApi } from "@/api/timelines";
import type {
  AccountSignalPlanEvaluation,
  GovernorDecisionTrace,
  SignalPlan,
} from "@/api/schemas/timelines";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { AwaitingApiOrError } from "@/components/empty/AwaitingApi";
import { EmptyState } from "@/components/empty/EmptyState";
import { relativeTime } from "@/lib/format";

/**
 * OperationsTimelines — three Operation Center timelines:
 *   - SignalPlans (what each Deployment published)
 *   - Account evaluations (how each Account decided)
 *   - Governor decisions (final approval gate)
 *
 * All three routes are pending Operation Turtle Shell. Each timeline
 * gracefully reports its awaiting state and goes live the moment the
 * matching route is registered.
 */
export function OperationsTimelines(): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
            Decision timelines
          </span>
        </CardTitle>
        <StatusBadge tone="info">SignalPlan → Account → Governor</StatusBadge>
      </CardHeader>
      <CardBody>
        <Tabs defaultValue="signal-plans">
          <TabsList>
            <TabsTrigger value="signal-plans">
              <ListChecks className="h-3.5 w-3.5" aria-hidden="true" />
              SignalPlans
            </TabsTrigger>
            <TabsTrigger value="evaluations">
              <Brain className="h-3.5 w-3.5" aria-hidden="true" />
              Account decisions
            </TabsTrigger>
            <TabsTrigger value="governor">
              <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />
              Governor decisions
            </TabsTrigger>
          </TabsList>
          <TabsContent value="signal-plans">
            <SignalPlanTimeline />
          </TabsContent>
          <TabsContent value="evaluations">
            <EvaluationTimeline />
          </TabsContent>
          <TabsContent value="governor">
            <GovernorTimeline />
          </TabsContent>
        </Tabs>
      </CardBody>
    </Card>
  );
}

function SignalPlanTimeline(): JSX.Element {
  const q = useQuery({
    queryKey: ["operations", "signal-plans"],
    queryFn: () => TimelinesApi.signalPlans({ limit: 50 }),
    refetchInterval: 5_000,
    retry: false,
  });

  if (q.isLoading) return <LoadingState title="Loading SignalPlans" />;
  if (q.isError)
    return (
      <AwaitingApiOrError
        title="SignalPlan timeline"
        endpoint="GET /api/v1/operations/signal-plans"
        awaitingMessage="The SignalPlan persistence + read-model is in Operation Turtle Shell's queue. The timeline lights up the moment the route is registered."
        error={q.error}
        onRetry={() => q.refetch()}
      />
    );
  const items = q.data?.signal_plans ?? [];
  if (items.length === 0)
    return <EmptyState title="No SignalPlans yet" message="Active Deployments emit SignalPlans here." />;

  return (
    <table className="ut-table">
      <thead>
        <tr>
          <th>When</th>
          <th>Symbol</th>
          <th>Side</th>
          <th>Intent</th>
          <th>Status</th>
          <th>Reason</th>
        </tr>
      </thead>
      <tbody>
        {items.map((sp) => (
          <SignalPlanRow key={sp.signal_plan_id} sp={sp} />
        ))}
      </tbody>
    </table>
  );
}

function SignalPlanRow({ sp }: { sp: SignalPlan }): JSX.Element {
  return (
    <tr>
      <td className="text-fg-muted">{relativeTime(sp.published_at ?? sp.created_at)}</td>
      <td className="font-medium">{sp.symbol}</td>
      <td>
        <StatusBadge tone={sp.side === "long" ? "ok" : sp.side === "short" ? "danger" : "muted"}>
          {sp.side}
        </StatusBadge>
      </td>
      <td>
        <StatusBadge tone="info">{sp.intent}</StatusBadge>
      </td>
      <td>
        <StatusBadge tone={signalPlanStatusTone(sp.status)}>{sp.status}</StatusBadge>
      </td>
      <td className="text-fg-muted">{sp.reason}</td>
    </tr>
  );
}

function signalPlanStatusTone(
  status: SignalPlan["status"],
): "ok" | "warn" | "danger" | "info" | "muted" | "neutral" {
  switch (status) {
    case "executed":
      return "ok";
    case "partially_executed":
      return "info";
    case "failed":
      return "danger";
    case "expired":
    case "canceled":
    case "superseded":
      return "muted";
    default:
      return "info";
  }
}

function EvaluationTimeline(): JSX.Element {
  const q = useQuery({
    queryKey: ["operations", "evaluations"],
    queryFn: () => TimelinesApi.evaluations({ limit: 50 }),
    refetchInterval: 5_000,
    retry: false,
  });

  if (q.isLoading) return <LoadingState title="Loading Account evaluations" />;
  if (q.isError)
    return (
      <AwaitingApiOrError
        title="Account evaluation timeline"
        endpoint="GET /api/v1/operations/evaluations"
        awaitingMessage="The AccountSignalPlanEvaluation read-model is in Operation Turtle Shell's queue."
        error={q.error}
        onRetry={() => q.refetch()}
      />
    );
  const items = q.data?.evaluations ?? [];
  if (items.length === 0)
    return (
      <EmptyState
        title="No Account evaluations yet"
        message="Each subscribed Account decides independently as SignalPlans publish."
      />
    );

  return (
    <table className="ut-table">
      <thead>
        <tr>
          <th>When</th>
          <th>Account</th>
          <th>Decision</th>
          <th>Status</th>
          <th>Rejection reasons</th>
        </tr>
      </thead>
      <tbody>
        {items.map((ev) => (
          <EvaluationRow key={ev.evaluation_id} ev={ev} />
        ))}
      </tbody>
    </table>
  );
}

function EvaluationRow({ ev }: { ev: AccountSignalPlanEvaluation }): JSX.Element {
  return (
    <tr>
      <td className="text-fg-muted">{relativeTime(ev.evaluated_at ?? ev.created_at)}</td>
      <td className="font-mono text-xs">{ev.account_id.slice(0, 8)}</td>
      <td>
        <StatusBadge tone={participationTone(ev.participation_decision)}>
          {ev.participation_decision}
        </StatusBadge>
      </td>
      <td>
        <StatusBadge tone={evaluationStatusTone(ev.status)}>{ev.status}</StatusBadge>
      </td>
      <td className="text-fg-muted">
        {ev.rejection_reasons.length === 0 ? "" : ev.rejection_reasons.join("; ")}
      </td>
    </tr>
  );
}

function participationTone(
  decision: AccountSignalPlanEvaluation["participation_decision"],
): "ok" | "warn" | "danger" | "info" | "muted" | "neutral" {
  switch (decision) {
    case "participate":
      return "ok";
    case "reject":
      return "danger";
    case "ignore":
      return "muted";
    case "defer":
      return "warn";
    case "requires_operator":
      return "warn";
    default:
      return "neutral";
  }
}

function evaluationStatusTone(
  status: AccountSignalPlanEvaluation["status"],
): "ok" | "warn" | "danger" | "info" | "muted" | "neutral" {
  switch (status) {
    case "accepted":
      return "ok";
    case "rejected":
    case "blocked":
      return "danger";
    case "deferred":
    case "needs_operator_attention":
    case "stale":
      return "warn";
    default:
      return "info";
  }
}

function GovernorTimeline(): JSX.Element {
  const q = useQuery({
    queryKey: ["operations", "governor-decisions"],
    queryFn: () => TimelinesApi.governorDecisions({ limit: 50 }),
    refetchInterval: 5_000,
    retry: false,
  });

  if (q.isLoading) return <LoadingState title="Loading Governor decisions" />;
  if (q.isError)
    return (
      <AwaitingApiOrError
        title="Governor decision timeline"
        endpoint="GET /api/v1/operations/governor-decisions"
        awaitingMessage="GovernorDecisionTrace persistence + read-model is in Operation Turtle Shell's queue."
        error={q.error}
        onRetry={() => q.refetch()}
      />
    );
  const items = q.data?.governor_decisions ?? [];
  if (items.length === 0)
    return (
      <EmptyState
        title="No Governor decisions yet"
        message="Every Account-evaluated SignalPlan that reaches the Governor records its decision here."
      />
    );

  return (
    <table className="ut-table">
      <thead>
        <tr>
          <th>When</th>
          <th>Account</th>
          <th>Status</th>
          <th>Reasons</th>
          <th>Violations</th>
        </tr>
      </thead>
      <tbody>
        {items.map((g) => (
          <GovernorRow key={g.governor_decision_id} g={g} />
        ))}
      </tbody>
    </table>
  );
}

function GovernorRow({ g }: { g: GovernorDecisionTrace }): JSX.Element {
  return (
    <tr>
      <td className="text-fg-muted">{relativeTime(g.evaluated_at)}</td>
      <td className="font-mono text-xs">{g.account_id.slice(0, 8)}</td>
      <td>
        <StatusBadge tone={g.approved ? "ok" : "danger"}>{g.status}</StatusBadge>
      </td>
      <td className="text-fg-muted">{g.reasons.join("; ")}</td>
      <td className="text-warn">{g.violations.join("; ")}</td>
    </tr>
  );
}

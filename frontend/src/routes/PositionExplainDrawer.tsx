import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Copy } from "lucide-react";
import { PositionsApi } from "@/api/positions";
import type {
  AiExplainPositionResponse,
  PositionExplanationContext,
} from "@/api/schemas/positions";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { AwaitingApiOrError, isAwaiting } from "@/components/empty/AwaitingApi";
import { formatCurrency, formatTimestamp } from "@/lib/format";

/**
 * PositionExplainDrawer — operator-visible explanation of a single
 * Account-owned position.
 *
 * Reads the canonical `PositionExplanationContext` from the backend
 * (currently awaiting `/api/v1/broker-accounts/{id}/positions/{lineage}/explain`).
 * The AI advisory tab consumes that context via
 * `/api/v1/ai/explain-position` (also awaiting). Both gracefully
 * surface their awaiting state until Operation Turtle Shell's
 * PositionLineage service ships.
 *
 * AI is advisory only. The drawer never offers an action that mutates
 * broker, order, trade, or position truth.
 */
export interface PositionExplainDrawerProps {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  accountId: string | null;
  positionLineageId: string | null;
  /** Optional pre-known symbol used in the drawer title. */
  symbolHint?: string;
}

export function PositionExplainDrawer({
  open,
  onOpenChange,
  accountId,
  positionLineageId,
  symbolHint,
}: PositionExplainDrawerProps): JSX.Element {
  const ready = open && accountId != null && positionLineageId != null;
  const explain = useQuery({
    queryKey: ["positions", "explain", accountId, positionLineageId],
    queryFn: () => PositionsApi.explain(accountId!, positionLineageId!),
    enabled: ready,
    refetchInterval: ready ? 10_000 : false,
    retry: false,
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-w-2xl">
        <DrawerHeader>
          <DrawerTitle>
            Explain position{symbolHint ? ` · ${symbolHint}` : ""}
          </DrawerTitle>
          <DrawerDescription>
            Operator inspection of the lineage that owns this position. AI advisory is opt-in
            and never mutates broker truth.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {!ready ? (
            <LoadingState title="No position selected" message="Open a position row to explain it." />
          ) : explain.isLoading ? (
            <LoadingState title="Loading position lineage" />
          ) : explain.isError ? (
            <AwaitingApiOrError
              title="Position lineage"
              endpoint={`GET /api/v1/broker-accounts/${accountId}/positions/${positionLineageId}/explain`}
              awaitingMessage="Operation Turtle Shell is wiring the PositionLineage service and explanation builder. The drawer goes live the moment the route is registered — no further code change."
              error={explain.error}
              onRetry={() => explain.refetch()}
            />
          ) : explain.data ? (
            <ExplanationContent context={explain.data} />
          ) : null}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

function ExplanationContent({ context }: { context: PositionExplanationContext }): JSX.Element {
  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Lineage</CardTitle>
          <StatusBadge tone={context.side === "long" ? "ok" : context.side === "short" ? "danger" : "muted"}>
            {context.side}
          </StatusBadge>
        </CardHeader>
        <CardBody className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
          <KV label="Symbol" value={context.symbol} />
          <KV label="Quantity" value={String(context.current_quantity)} />
          <KV label="Avg entry" value={formatCurrency(context.average_entry ?? null)} />
          <KV label="Market value" value={formatCurrency(context.current_market_value ?? null)} />
          <KV label="Unrealized P&L" value={formatCurrency(context.unrealized_pnl ?? null)} />
          <KV label="Generated" value={formatTimestamp(context.explanation_generated_at)} />
          <KV label="Account" value={context.account_id.slice(0, 8)} />
          <KV label="Deployment" value={context.deployment_id.slice(0, 8)} />
          <KV label="Strategy" value={context.strategy_id.slice(0, 8)} />
          <KV label="Opening SignalPlan" value={context.opening_signal_plan_id.slice(0, 8)} />
          <KV
            label="Related SignalPlans"
            value={String(context.current_signal_plan_ids.length)}
          />
          <KV
            label="Account evaluations"
            value={String(context.account_evaluation_ids.length)}
          />
          <KV
            label="Governor decisions"
            value={String(context.governor_decision_ids.length)}
          />
          <KV label="Orders" value={String(context.order_ids.length)} />
          <KV label="Fills" value={String(context.fill_ids.length)} />
        </CardBody>
      </Card>

      {context.unresolved_risks.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Unresolved risks</CardTitle>
            <StatusBadge tone="warn">{context.unresolved_risks.length}</StatusBadge>
          </CardHeader>
          <CardBody className="space-y-1 text-xs">
            {context.unresolved_risks.map((risk) => (
              <div key={risk} className="text-warn">
                · {risk}
              </div>
            ))}
          </CardBody>
        </Card>
      ) : null}

      <AiAdvisoryPanel context={context} />
    </>
  );
}

function AiAdvisoryPanel({ context }: { context: PositionExplanationContext }): JSX.Element {
  const qc = useQueryClient();
  const [advisory, setAdvisory] = useState<AiExplainPositionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = useMutation({
    mutationFn: () => PositionsApi.aiExplain(context),
    onSuccess: (data) => {
      setAdvisory(data);
      setError(null);
    },
    onError: (e) => {
      setAdvisory(null);
      if (isAwaiting(e)) {
        setError("awaiting:/api/v1/ai/explain-position");
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
  });

  function handleCopy(): void {
    if (!advisory) return;
    void navigator.clipboard.writeText(advisory.copy_context);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Brain className="h-4 w-4 text-ai" aria-hidden="true" />
            AI advisory
          </span>
        </CardTitle>
        <StatusBadge tone="ai">Advisory Only</StatusBadge>
      </CardHeader>
      <CardBody className="space-y-2 text-sm">
        <div className="text-xs text-fg-muted">
          AI may explain. AI may not approve, reject, size, submit, cancel, or mutate broker
          truth.
        </div>
        {advisory ? (
          <>
            <div className="rounded border border-border bg-bg-inset px-3 py-2 leading-relaxed">
              {advisory.summary}
            </div>
            {advisory.advisories.length > 0 ? (
              <ul className="space-y-1 text-xs">
                {advisory.advisories.map((a, i) => (
                  <li key={i} className="text-fg-muted">
                    · {a}
                  </li>
                ))}
              </ul>
            ) : null}
            <div className="flex items-center justify-between text-xs text-fg-subtle">
              <span>Generated {formatTimestamp(advisory.generated_at)}</span>
              <Button
                size="sm"
                variant="ghost"
                leftIcon={<Copy className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={handleCopy}
              >
                Copy context
              </Button>
            </div>
          </>
        ) : null}
        {error?.startsWith("awaiting:") ? (
          <div className="rounded border border-info/40 bg-info-subtle px-3 py-2 text-xs">
            <div className="font-medium text-info">AI advisory route awaiting backend</div>
            <div className="mt-1 text-fg-muted">
              The button will become live the moment Operation Turtle Shell ships{" "}
              <span className="font-mono">{error.slice("awaiting:".length)}</span>.
            </div>
          </div>
        ) : error ? (
          <div className="rounded border border-danger/40 bg-danger-subtle px-3 py-2 text-xs text-danger">
            {error}
          </div>
        ) : null}
      </CardBody>
      <div className="flex justify-end border-t border-border/70 px-4 py-2">
        <Button
          size="sm"
          variant="primary"
          leftIcon={<Brain className="h-3.5 w-3.5" aria-hidden="true" />}
          loading={ask.isPending}
          onClick={() => {
            qc.invalidateQueries({ queryKey: ["ai", "explain-position"] }).catch(() => {});
            ask.mutate();
          }}
        >
          Ask AI
        </Button>
      </div>
    </Card>
  );
}

function KV({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-fg-subtle">{label}</span>
      <span className="tabular text-fg">{value}</span>
    </div>
  );
}

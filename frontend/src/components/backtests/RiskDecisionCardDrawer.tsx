import { useQuery } from "@tanstack/react-query";
import { RiskDecisionsApi } from "@/api/riskDecisions";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { Banner } from "@/components/ui/Banner";
import { LoadingState } from "@/components/empty/LoadingState";
import { StatusBadge } from "@/components/badges/StatusBadge";
import type { RiskDecisionCard } from "@/api/schemas/riskDecisions";

/**
 * RiskDecisionCardDrawer — drill into a single sized SignalPlan.
 *
 * Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §9.6:
 * - Decision summary (APPROVED / REJECTED / REDUCED / CAPPED + human_summary)
 * - Inputs (equity, cash, buying_power, price, stop, stop_distance)
 * - Step-by-step calculation_steps formula trace
 * - Constraints applied / Warnings / Violations
 * - Lineage (FeatureSnapshot, CandidateTradeIntent, SignalPlan, RiskPlan version, RiskResolver version)
 *
 * RiskPlan belongs to the Account or selected research run. SignalPlan describes
 * the proposed lifecycle action. RiskResolver combines the SignalPlan, RiskPlan,
 * and current account or simulated account state to produce a RiskDecisionCard.
 * No simulated or real order may be created without that RiskDecisionCard.
 */
export function RiskDecisionCardDrawer({
  open,
  onOpenChange,
  riskDecisionId,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  riskDecisionId: string | null;
}): JSX.Element {
  const card = useQuery({
    queryKey: ["risk-decisions", riskDecisionId],
    queryFn: () => RiskDecisionsApi.get(riskDecisionId as string),
    enabled: open && Boolean(riskDecisionId),
    retry: false,
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Risk decision card</DrawerTitle>
        </DrawerHeader>
        <DrawerBody className="space-y-4">
          {!riskDecisionId ? (
            <Banner
              severity="info"
              title="No card linked"
              message="This trade was created before the SignalPlan + RiskDecisionCard wiring landed; older runs do not have a card to drill into."
            />
          ) : null}
          {card.isLoading ? <LoadingState title="Loading risk decision" /> : null}
          {card.isError ? (
            <Banner
              severity="danger"
              title="Could not load risk decision"
              message={(card.error as Error)?.message}
            />
          ) : null}
          {card.data ? <CardBody data={card.data} /> : null}
        </DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

function CardBody({ data }: { data: RiskDecisionCard }): JSX.Element {
  return (
    <div className="space-y-4 text-xs">
      <div>
        <div className="mb-1 flex items-center gap-2">
          <StatusBadge tone={decisionTone(data.decision)}>{data.decision.toUpperCase()}</StatusBadge>
          <StatusBadge tone="info">{data.mode}</StatusBadge>
          <span className="text-fg-muted">
            {data.symbol} · {data.side} · {data.lifecycle_intent}
          </span>
        </div>
        <p className="text-sm">{data.human_summary}</p>
      </div>

      <Section title="Decision inputs">
        <Field label="Account equity" value={fmtMoney(data.account_equity)} />
        <Field label="Cash" value={fmtMoney(data.account_cash)} />
        <Field label="Buying power" value={fmtMoney(data.buying_power)} />
        <Field label="Current price" value={fmtMoney(data.current_price)} />
        <Field label="Stop price" value={data.stop_price != null ? fmtMoney(data.stop_price) : "—"} />
        <Field
          label="Stop distance"
          value={data.stop_distance != null ? fmtMoney(data.stop_distance) : "—"}
        />
        <Field
          label="Existing position qty"
          value={fmtNumber(data.existing_position_quantity)}
        />
        <Field label="Open orders" value={fmtNumber(data.existing_open_orders_count)} />
      </Section>

      <Section title="Sizing">
        <Field label="Sizing method" value={data.sizing_method} />
        <Field label="Formula" value={data.formula_used} />
        <Field label="Raw quantity" value={fmtNumber(data.raw_quantity)} />
        <Field label="Final quantity" value={fmtNumber(data.final_quantity)} />
        <Field label="Final notional" value={fmtMoney(data.final_notional)} />
        <Field
          label="Capped quantity"
          value={data.capped_quantity != null ? fmtNumber(data.capped_quantity) : "—"}
        />
        <Field
          label="Max loss estimate"
          value={data.max_loss_estimate != null ? fmtMoney(data.max_loss_estimate) : "—"}
        />
        <Field
          label="Buying power required"
          value={
            data.buying_power_required != null ? fmtMoney(data.buying_power_required) : "—"
          }
        />
      </Section>

      <Section title="Formula trace">
        {data.calculation_steps.length === 0 ? (
          <span className="text-fg-subtle">no formula steps recorded.</span>
        ) : (
          <table className="ut-table">
            <thead>
              <tr>
                <th>Step</th>
                <th>Formula</th>
                <th>Inputs</th>
                <th>Output</th>
              </tr>
            </thead>
            <tbody>
              {data.calculation_steps.map((step, i) => (
                <tr key={`${step.name}-${i}`}>
                  <td className="font-medium">{step.name}</td>
                  <td className="font-mono text-[10px]">{step.formula}</td>
                  <td className="font-mono text-[10px] text-fg-muted">
                    {JSON.stringify(step.inputs)}
                  </td>
                  <td className="tabular">{fmtNumber(step.output)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {(data.constraints_applied.length > 0 ||
        data.violations.length > 0 ||
        data.warnings.length > 0) && (
        <Section title="Constraints / Warnings / Violations">
          <div className="space-y-1">
            {data.constraints_applied.map((c) => (
              <div key={c}>
                <StatusBadge tone="info">constraint</StatusBadge> <span>{c}</span>
              </div>
            ))}
            {data.warnings.map((w) => (
              <div key={w}>
                <StatusBadge tone="warn">warning</StatusBadge> <span>{w}</span>
              </div>
            ))}
            {data.violations.map((v) => (
              <div key={v}>
                <StatusBadge tone="danger">violation</StatusBadge> <span>{v}</span>
              </div>
            ))}
          </div>
        </Section>
      )}

      <Section title="Lineage">
        <Field label="Risk decision id" value={data.risk_decision_id} />
        <Field label="SignalPlan id" value={data.signal_plan_id} />
        <Field label="Risk plan version id" value={data.risk_plan_version_id} />
        <Field label="Strategy version id" value={data.strategy_version_id} />
        <Field
          label="Candidate intent id"
          value={data.candidate_trade_intent_id ?? "—"}
        />
        <Field label="Feature snapshot id" value={data.feature_snapshot_id ?? "—"} />
        <Field label="Resolver version" value={data.risk_resolver_version} />
        <Field label="Created at" value={data.created_at} />
      </Section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div className="rounded border border-border p-3">
      <div className="mb-2 text-[11px] uppercase tracking-wider text-fg-muted">{title}</div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs md:grid-cols-3">{children}</div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div>
      <div className="text-fg-muted">{label}</div>
      <div className="break-all">{value}</div>
    </div>
  );
}

function decisionTone(decision: string): "ok" | "warn" | "danger" | "info" | "muted" {
  switch (decision) {
    case "approved":
      return "ok";
    case "reduced":
    case "capped":
      return "warn";
    case "rejected":
      return "danger";
    case "skipped":
      return "muted";
    case "requires_operator":
      return "info";
    default:
      return "muted";
  }
}

function fmtMoney(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 4,
  }).format(n);
}

function fmtNumber(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return n.toFixed(4);
}

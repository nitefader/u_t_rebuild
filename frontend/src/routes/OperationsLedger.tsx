import { useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ListChecks, ReceiptText } from "lucide-react";
import { OperationsApi } from "@/api/operations";
import { AccountsApi } from "@/api/accounts";
import { ManualTradeApi } from "@/api/manualTrade";
import type { ManualOrderResponse } from "@/api/schemas/manualTrade";
import type { AccountOperations } from "@/api/schemas/operations";
import type { BrokerAccount } from "@/api/schemas/accounts";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { formatCurrency, formatTimestamp, relativeTime } from "@/lib/format";
import { getProtectionDisplay } from "@/lib/protectionDisplay";

/**
 * OperationsLedger — persistent aggregated Orders + Positions tables
 * on the Operations page. Polls every 5s so the operator never has
 * to open a drawer to know what the broker holds.
 *
 * Aggregation is client-side until the backend exposes
 * `/api/v1/operations/positions` and `/api/v1/operations/orders`
 * (cross-account read-models). For ~10 accounts the parallel
 * per-account fetches are cheap and the operator sees the same
 * truth as the per-Account drawer.
 */
export function OperationsLedger(): JSX.Element {
  const accounts = useQuery({
    queryKey: ["accounts", "list"],
    queryFn: () => AccountsApi.list(),
    refetchInterval: 30_000,
  });

  const accountList = accounts.data?.accounts ?? [];
  const opsQueries = useQueries({
    queries: accountList.map((a) => ({
      queryKey: ["operations", "account", a.id],
      queryFn: () => OperationsApi.account(a.id),
      refetchInterval: 5_000,
      retry: false,
    })),
  });
  const manualOrderQueries = useQueries({
    queries: accountList.map((a) => ({
      queryKey: ["manual-trade", "list", a.id],
      queryFn: () => ManualTradeApi.list(a.id),
      refetchInterval: 5_000,
      retry: false,
    })),
  });

  const aggregated = useMemo(
    () => aggregate(accountList, opsQueries.map((q) => q.data ?? null), manualOrderQueries.map((q) => q.data?.orders ?? null)),
    [accountList, opsQueries, manualOrderQueries],
  );

  const anyError = opsQueries.some((q) => q.isError) || manualOrderQueries.some((q) => q.isError);
  const allLoaded = opsQueries.every((q) => q.isFetched);
  const errors = opsQueries
    .map((q, i) => ({ account: accountList[i], err: q.error as Error | null }))
    .filter((e) => e.err);

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      <PositionsCard
        positions={aggregated.positions}
        loading={accounts.isLoading || !allLoaded}
        anyError={anyError}
        errors={errors}
      />
      <OrdersCard
        orders={aggregated.orders}
        loading={accounts.isLoading || !allLoaded}
        anyError={anyError}
        errors={errors}
      />
    </div>
  );
}

interface AggregatedPosition {
  accountId: string;
  accountLabel: string;
  symbol: string;
  qty: number;
  side: string | null;
  avg: number | null;
  marketValue: number | null;
  unrealized: number | null;
  protectionStatus: string;
  protectiveOrderCount: number;
}

interface AggregatedOrder {
  accountId: string;
  accountLabel: string;
  orderId: string;
  symbol: string;
  side: string;
  qty: number;
  filled: number;
  status: string;
  intent: string;
  submittedAt: string;
  source: "manual" | "broker";
}

function aggregate(
  accounts: BrokerAccount[],
  ops: Array<AccountOperations | null>,
  manualOrders: Array<ManualOrderResponse[] | null>,
): { positions: AggregatedPosition[]; orders: AggregatedOrder[] } {
  const labelByAccount = new Map(accounts.map((a) => [a.id, a.display_name]));
  const positions: AggregatedPosition[] = [];
  const orders: AggregatedOrder[] = [];

  for (let i = 0; i < accounts.length; i++) {
    const a = accounts[i];
    const ac = ops[i];
    if (ac) {
      // T-5 Bracket Program: build a lineage->view lookup so we can stamp
      // operator-visible protection_status onto each aggregated row.
      const viewByLineage = new Map<string, { protection_status: string; protective_order_count: number }>();
      for (const v of ac.position_views ?? []) {
        const lineageId = (v.snapshot as { position_lineage_id?: string | null }).position_lineage_id ?? null;
        if (lineageId) {
          viewByLineage.set(lineageId, {
            protection_status: v.protection_status ?? "unknown",
            protective_order_count: v.protective_order_count ?? 0,
          });
        }
      }
      for (const p of ac.positions) {
        const r = p as {
          symbol?: string;
          qty?: number | null;
          quantity?: number | null;
          avg_entry_price?: number | null;
          average_entry_price?: number | null;
          market_value?: number | null;
          unrealized_pl?: number | null;
          side?: string | null;
          position_lineage_id?: string | null;
        };
        const view = r.position_lineage_id ? viewByLineage.get(r.position_lineage_id) : undefined;
        positions.push({
          accountId: a.id,
          accountLabel: labelByAccount.get(a.id) ?? a.id,
          symbol: r.symbol ?? "—",
          qty: r.qty ?? r.quantity ?? 0,
          side: r.side ?? null,
          avg: r.avg_entry_price ?? r.average_entry_price ?? null,
          marketValue: r.market_value ?? null,
          unrealized: r.unrealized_pl ?? null,
          protectionStatus: view?.protection_status ?? "unknown",
          protectiveOrderCount: view?.protective_order_count ?? 0,
        });
      }
      for (const o of ac.open_broker_orders) {
        const r = o as {
          broker_order_id: string;
          symbol: string;
          side?: string | null;
          qty?: number | null;
          filled_qty?: number | null;
          status: string;
          timestamp?: string | null;
        };
        orders.push({
          accountId: a.id,
          accountLabel: labelByAccount.get(a.id) ?? a.id,
          orderId: r.broker_order_id,
          symbol: r.symbol,
          side: r.side ?? "—",
          qty: r.qty ?? 0,
          filled: r.filled_qty ?? 0,
          status: r.status,
          intent: "—",
          submittedAt: r.timestamp ?? "",
          source: "broker",
        });
      }
    }
    const manuals = manualOrders[i];
    if (manuals) {
      for (const o of manuals) {
        orders.push({
          accountId: a.id,
          accountLabel: labelByAccount.get(a.id) ?? a.id,
          orderId: o.order_id,
          symbol: o.symbol,
          side: o.side,
          qty: o.quantity,
          filled: o.filled_quantity,
          status: o.status,
          intent: typeof o.intent === "string" ? o.intent : String(o.intent),
          submittedAt: o.submitted_at,
          source: "manual",
        });
      }
    }
  }

  positions.sort(
    (a, b) =>
      Math.abs(b.marketValue ?? 0) - Math.abs(a.marketValue ?? 0) ||
      a.accountLabel.localeCompare(b.accountLabel),
  );
  orders.sort((a, b) => (b.submittedAt || "").localeCompare(a.submittedAt || ""));
  return { positions, orders };
}

function PositionsCard({
  positions,
  loading,
  anyError,
  errors,
}: {
  positions: AggregatedPosition[];
  loading: boolean;
  anyError: boolean;
  errors: { account: BrokerAccount | undefined; err: Error | null }[];
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <ListChecks className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
            Positions (all Accounts)
          </span>
        </CardTitle>
        <StatusBadge tone={anyError ? "warn" : "neutral"}>{positions.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        {loading ? (
          <div className="p-4">
            <LoadingState title="Loading positions" />
          </div>
        ) : anyError && positions.length === 0 ? (
          <div className="p-4">
            <ErrorState
              title="Could not load positions for one or more accounts"
              detail={errors.map((e) => `${e.account?.display_name ?? "?"}: ${e.err?.message ?? ""}`).join("; ")}
            />
          </div>
        ) : positions.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No open positions" message="No Account is holding inventory right now." />
          </div>
        ) : (
          <table className="ut-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Avg entry</th>
                <th>Market value</th>
                <th>Unrealized</th>
                <th>Protection</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => {
                const tone = p.unrealized == null ? "neutral" : p.unrealized > 0 ? "ok" : p.unrealized < 0 ? "danger" : "neutral";
                const protectionDisplay = getProtectionDisplay(
                  p.protectionStatus,
                  p.protectiveOrderCount,
                );
                return (
                  <tr key={`${p.accountId}-${p.symbol}-${i}`}>
                    <td className="text-fg-muted">{p.accountLabel}</td>
                    <td className="font-medium">{p.symbol}</td>
                    <td>
                      <StatusBadge tone={p.side === "short" ? "danger" : "ok"}>{p.side ?? "—"}</StatusBadge>
                    </td>
                    <td className="tabular">{p.qty}</td>
                    <td className="tabular">{formatCurrency(p.avg)}</td>
                    <td className="tabular">{formatCurrency(p.marketValue)}</td>
                    <td className="tabular">
                      <span
                        className={
                          tone === "ok"
                            ? "text-ok"
                            : tone === "danger"
                              ? "text-danger"
                              : "text-fg"
                        }
                      >
                        {formatCurrency(p.unrealized)}
                      </span>
                    </td>
                    <td title={protectionDisplay.title}>
                      <StatusBadge tone={protectionDisplay.tone}>
                        {protectionDisplay.label}
                      </StatusBadge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

function OrdersCard({
  orders,
  loading,
  anyError,
  errors,
}: {
  orders: AggregatedOrder[];
  loading: boolean;
  anyError: boolean;
  errors: { account: BrokerAccount | undefined; err: Error | null }[];
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <ReceiptText className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
            Orders (all Accounts)
          </span>
        </CardTitle>
        <StatusBadge tone={anyError ? "warn" : "neutral"}>{orders.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        {loading ? (
          <div className="p-4">
            <LoadingState title="Loading orders" />
          </div>
        ) : anyError && orders.length === 0 ? (
          <div className="p-4">
            <ErrorState
              title="Could not load orders for one or more accounts"
              detail={errors.map((e) => `${e.account?.display_name ?? "?"}: ${e.err?.message ?? ""}`).join("; ")}
            />
          </div>
        ) : orders.length === 0 ? (
          <div className="p-4">
            <EmptyState title="No orders" message="Manual or system orders will appear here as soon as they land." />
          </div>
        ) : (
          <table className="ut-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Account</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>Qty</th>
                <th>Filled</th>
                <th>Status</th>
                <th>Source</th>
                <th>Intent</th>
              </tr>
            </thead>
            <tbody>
              {orders.slice(0, 50).map((o) => (
                <tr key={`${o.accountId}-${o.orderId}`}>
                  <td className="text-fg-muted" title={formatTimestamp(o.submittedAt)}>
                    {o.submittedAt ? relativeTime(o.submittedAt) : "—"}
                  </td>
                  <td className="text-fg-muted">{o.accountLabel}</td>
                  <td className="font-medium">{o.symbol}</td>
                  <td>
                    <StatusBadge tone={o.side === "short" ? "danger" : "ok"}>{o.side}</StatusBadge>
                  </td>
                  <td className="tabular">{o.qty}</td>
                  <td className="tabular text-fg-muted">{o.filled}</td>
                  <td>
                    <StatusBadge tone={statusTone(o.status)}>{o.status}</StatusBadge>
                  </td>
                  <td>
                    <StatusBadge tone={o.source === "manual" ? "info" : "muted"}>{o.source}</StatusBadge>
                  </td>
                  <td className="text-fg-muted">{o.intent}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardBody>
    </Card>
  );
}

function statusTone(status: string): "ok" | "warn" | "danger" | "info" | "muted" | "neutral" {
  switch (status) {
    case "filled":
      return "ok";
    case "partially_filled":
      return "info";
    case "rejected":
    case "failed":
      return "danger";
    case "canceled":
    case "expired":
      return "muted";
    default:
      return "info";
  }
}

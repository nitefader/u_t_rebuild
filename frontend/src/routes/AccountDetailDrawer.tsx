import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Brain, ReceiptText } from "lucide-react";
import { OperationsApi } from "@/api/operations";
import type { BrokerAccount } from "@/api/schemas/accounts";
import { Banner } from "@/components/ui/Banner";
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
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { formatCurrency, relativeTime } from "@/lib/format";
import { latestBrokerSyncTimestamp } from "@/lib/brokerSync";
import { getProtectionDisplay } from "@/lib/protectionDisplay";
import { PositionExplainDrawer } from "./PositionExplainDrawer";
import { ManualOrderDrawer } from "./ManualOrderDrawer";
import { RiskCardPanel } from "./RiskCardPanel";
import { AccountRiskPlanCard } from "@/components/risk_plans/AccountRiskPlanCard";

/**
 * AccountDetailDrawer — operator inspection for a single Account.
 *
 * Reads `/api/v1/operations/accounts/{id}` for snapshot, sync state,
 * positions, open broker orders, internal-order ledger summary, and
 * subscribed deployments. Read-only — pause/resume/flatten still
 * live on the Account card via Operations control commands.
 */
export function AccountDetailDrawer({
  open,
  onOpenChange,
  account,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  account: BrokerAccount | null;
}): JSX.Element {
  const detail = useQuery({
    queryKey: ["operations", "account", account?.id],
    queryFn: () => OperationsApi.account(account!.id),
    enabled: open && account != null,
    refetchInterval: 5_000,
  });

  const [explainOpen, setExplainOpen] = useState(false);
  const [explainTarget, setExplainTarget] = useState<{
    lineageId: string;
    symbol: string;
  } | null>(null);
  const [manualOrderOpen, setManualOrderOpen] = useState(false);

  function openExplain(symbol: string, lineageId: string | null): void {
    if (!lineageId) return;
    setExplainTarget({ symbol, lineageId });
    setExplainOpen(true);
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-w-2xl">
        <DrawerHeader>
          <DrawerTitle>{account?.display_name ?? "Account"}</DrawerTitle>
          <DrawerDescription>
            Operator inspection. Pause / resume / flatten live on the Account card.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {!account ? null : detail.isLoading ? (
            <LoadingState title="Loading account" />
          ) : detail.isError ? (
            <ErrorState
              title="Could not load account"
              detail={(detail.error as Error)?.message}
              onRetry={() => detail.refetch()}
            />
          ) : !detail.data ? null : (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Snapshot</CardTitle>
                  <span className="flex items-center gap-2">
                    <StatusBadge tone={detail.data.is_paused ? "warn" : "ok"}>
                      {detail.data.is_paused ? "Paused" : "Active"}
                    </StatusBadge>
                    {detail.data.broker_sync_freshness?.is_stale ? (
                      <StatusBadge tone="warn">Sync Stale</StatusBadge>
                    ) : (
                      <StatusBadge tone="ok">Sync Fresh</StatusBadge>
                    )}
                  </span>
                </CardHeader>
                <CardBody className="grid grid-cols-3 gap-2 text-xs">
                  <KV label="Equity" value={formatCurrency(detail.data.broker_account_snapshot?.equity ?? null)} />
                  <KV label="Cash" value={formatCurrency(detail.data.broker_account_snapshot?.cash ?? null)} />
                  <KV
                    label="Buying Power"
                    value={formatCurrency(detail.data.broker_account_snapshot?.buying_power ?? null)}
                  />
                  <KV
                    label="Multiplier"
                    value={detail.data.broker_account_snapshot?.multiplier != null ? `${detail.data.broker_account_snapshot.multiplier}x` : "—"}
                  />
                  <KV
                    label="Portfolio value"
                    value={formatCurrency(detail.data.broker_account_snapshot?.portfolio_value ?? null)}
                  />
                  <KV
                    label="Maintenance margin"
                    value={formatCurrency(detail.data.broker_account_snapshot?.maintenance_margin ?? null)}
                  />
                  <KV
                    label="Day trade count"
                    value={String(detail.data.broker_account_snapshot?.daytrade_count ?? "—")}
                  />
                  <KV label="Currency" value={detail.data.broker_account_snapshot?.currency ?? "—"} />
                  <KV
                    label="Transfers blocked"
                    value={detail.data.broker_account_snapshot?.transfers_blocked ? "yes" : "no"}
                  />
                  <KV
                    label="Trading blocked"
                    value={detail.data.broker_account_snapshot?.trading_blocked ? "yes" : "no"}
                  />
                  <KV
                    label="Account blocked"
                    value={detail.data.broker_account_snapshot?.account_blocked ? "yes" : "no"}
                  />
                  <KV
                    label="Last sync"
                    value={
                      latestBrokerSyncTimestamp(detail.data.broker_sync_freshness)
                        ? relativeTime(latestBrokerSyncTimestamp(detail.data.broker_sync_freshness)!)
                        : "—"
                    }
                  />
                </CardBody>
                {detail.data.broker_sync_freshness?.stale_reason ? (
                  <div className="px-4 pb-3">
                    <Banner severity="warning" title="Sync stale" message={detail.data.broker_sync_freshness.stale_reason} />
                  </div>
                ) : null}
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Open positions</CardTitle>
                  <span className="flex items-center gap-2">
                    <StatusBadge>{detail.data.positions.length}</StatusBadge>
                    <Button
                      size="sm"
                      variant="primary"
                      leftIcon={<ReceiptText className="h-3.5 w-3.5" aria-hidden="true" />}
                      onClick={() => setManualOrderOpen(true)}
                    >
                      Manual Order
                    </Button>
                  </span>
                </CardHeader>
                <CardBody className="p-0">
                  {detail.data.positions.length === 0 ? (
                    <div className="p-4">
                      <EmptyState title="No open positions" message="Account is flat." />
                    </div>
                  ) : (
                    <table className="ut-table">
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th>Quantity</th>
                          <th>Avg entry</th>
                          <th>Market value</th>
                          <th>Unrealized P&amp;L</th>
                          <th>Protection</th>
                          <th></th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.data.positions.map((p) => {
                          // Backend payload uses `qty` + `avg_entry_price` (the long-form
                          // names exist in older drafts and are tolerated for safety).
                          const symbol = (p as { symbol?: string }).symbol ?? "—";
                          const rawP = p as {
                            qty?: number | null;
                            quantity?: number | null;
                            avg_entry_price?: number | null;
                            average_entry_price?: number | null;
                            market_value?: number | null;
                            unrealized_pl?: number | null;
                            position_lineage_id?: string | null;
                          };
                          const quantity = rawP.qty ?? rawP.quantity ?? 0;
                          const avg = rawP.avg_entry_price ?? rawP.average_entry_price ?? null;
                          const mv = rawP.market_value ?? null;
                          const upl = rawP.unrealized_pl ?? null;
                          const lineageId = rawP.position_lineage_id ?? null;
                          const uplTone =
                            upl == null ? "neutral" : upl > 0 ? "ok" : upl < 0 ? "danger" : "neutral";
                          // T-5 Bracket Program: protection_status from the
                          // operator-derived position_views array. Match by
                          // position_lineage_id (only stable join key).
                          const matchingView = lineageId
                            ? (detail.data.position_views ?? []).find(
                                (v) =>
                                  (v.snapshot as { position_lineage_id?: string | null }).position_lineage_id ===
                                  lineageId,
                              )
                            : undefined;
                          const protectionStatus = matchingView?.protection_status ?? "unknown";
                          const protectionDisplay = getProtectionDisplay(
                            protectionStatus,
                            matchingView?.protective_order_count ?? 0,
                          );
                          // Critic Fix #7: row key uses lineage_id (stable
                          // across same-symbol-different-lineage rows) rather
                          // than `${symbol}-${quantity}` (collides on multi-
                          // entry same-symbol same-qty positions).
                          const rowKey = lineageId ?? `${symbol}-${quantity}-fallback`;
                          return (
                            <tr key={rowKey}>
                              <td className="font-medium">{symbol}</td>
                              <td className="tabular">{quantity}</td>
                              <td className="tabular">{formatCurrency(avg)}</td>
                              <td className="tabular">{formatCurrency(mv)}</td>
                              <td className="tabular">
                                <span
                                  className={
                                    uplTone === "ok"
                                      ? "text-ok"
                                      : uplTone === "danger"
                                        ? "text-danger"
                                        : "text-fg"
                                  }
                                >
                                  {formatCurrency(upl)}
                                </span>
                              </td>
                              <td title={protectionDisplay.title}>
                                <StatusBadge tone={protectionDisplay.tone}>
                                  {protectionDisplay.label}
                                </StatusBadge>
                              </td>
                              <td className="text-right">
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  leftIcon={<Brain className="h-3.5 w-3.5" aria-hidden="true" />}
                                  onClick={() => openExplain(symbol, lineageId)}
                                  title={
                                    lineageId
                                      ? "Open the position explainer"
                                      : "Awaiting PositionLineage backend"
                                  }
                                  disabled={!lineageId}
                                >
                                  Explain
                                </Button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </CardBody>
              </Card>

              {account ? <AccountRiskPlanCard accountId={account.id} /> : null}
              {account ? <RiskCardPanel accountId={account.id} /> : null}

              <Card>
                <CardHeader>
                  <CardTitle>Open broker orders</CardTitle>
                  <StatusBadge>{detail.data.open_broker_orders.length}</StatusBadge>
                </CardHeader>
                <CardBody className="p-0">
                  {detail.data.open_broker_orders.length === 0 ? (
                    <div className="p-4">
                      <EmptyState title="No open broker orders" message="No orders waiting at the broker." />
                    </div>
                  ) : (
                    <table className="ut-table">
                      <thead>
                        <tr>
                          <th>Symbol</th>
                          <th>Side</th>
                          <th>Quantity</th>
                          <th>Status</th>
                          <th>Type</th>
                          <th>Broker order id</th>
                          <th>Client order id</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.data.open_broker_orders.map((o) => (
                          <tr key={o.broker_order_id}>
                            <td className="font-medium">{o.symbol}</td>
                            <td className="tabular">{(o.side ?? "—").toUpperCase()}</td>
                            <td className="tabular">{o.qty ?? "—"}</td>
                            <td>
                              <StatusBadge tone="info">{o.status}</StatusBadge>
                            </td>
                            <td className="tabular">{o.order_type ?? "—"}</td>
                            <td className="font-mono text-xs">{o.broker_order_id.slice(0, 12)}</td>
                            <td className="font-mono text-xs">{o.client_order_id.slice(0, 16)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardBody>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Internal order ledger</CardTitle>
                  <StatusBadge>{detail.data.internal_order_ledger_summary.total_count}</StatusBadge>
                </CardHeader>
                <CardBody className="grid grid-cols-3 gap-2 text-xs">
                  <KV label="Open" value={String(detail.data.internal_order_ledger_summary.open_count)} />
                  <KV label="Terminal" value={String(detail.data.internal_order_ledger_summary.terminal_count)} />
                  <KV label="Total" value={String(detail.data.internal_order_ledger_summary.total_count)} />
                  <div className="col-span-3 mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(detail.data.internal_order_ledger_summary.by_status).map(([status, count]) => (
                      <StatusBadge key={status} tone="muted">
                        {status} · {count}
                      </StatusBadge>
                    ))}
                  </div>
                </CardBody>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Subscribed deployments</CardTitle>
                  <StatusBadge>{detail.data.deployments.length}</StatusBadge>
                </CardHeader>
                <CardBody className="p-0">
                  {detail.data.deployments.length === 0 ? (
                    <div className="p-4">
                      <EmptyState title="No deployments" message="This Account is not subscribed to any Deployment." />
                    </div>
                  ) : (
                    <table className="ut-table">
                      <thead>
                        <tr>
                          <th>Deployment</th>
                          <th>Status</th>
                          <th>Strategy version</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detail.data.deployments.map((d) => (
                          <tr key={d.deployment_id}>
                            <td className="font-mono text-xs">{d.deployment_id.slice(0, 8)}</td>
                            <td>
                              <StatusBadge tone={d.is_running ? "ok" : "muted"}>{d.status}</StatusBadge>
                            </td>
                            <td className="font-mono text-xs">
                              {d.strategy_version_id ? d.strategy_version_id.slice(0, 8) : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardBody>
              </Card>
            </>
          )}
        </DrawerBody>
      </DrawerContent>
      <PositionExplainDrawer
        open={explainOpen}
        onOpenChange={(b) => {
          setExplainOpen(b);
          if (!b) setExplainTarget(null);
        }}
        accountId={account?.id ?? null}
        positionLineageId={explainTarget?.lineageId ?? null}
        symbolHint={explainTarget?.symbol}
      />
      {account ? (
        <ManualOrderDrawer
          open={manualOrderOpen}
          onOpenChange={setManualOrderOpen}
          account={account}
        />
      ) : null}
    </Drawer>
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

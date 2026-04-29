import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, KeyRound, Pencil, Plus, Trash2 } from "lucide-react";
import { AccountsApi } from "@/api/accounts";
import { AccountDetailDrawer } from "./AccountDetailDrawer";
import { OperationsApi } from "@/api/operations";
import { SystemApi } from "@/api/system";
import type { BrokerAccount, TradingMode } from "@/api/schemas/accounts";
import type { AccountSummary } from "@/api/schemas/operations";
import type { TradeStreamStatus } from "@/api/schemas/system";
import { ApiError } from "@/api/client";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DangerConfirm } from "@/components/ui/DangerConfirm";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { Select } from "@/components/ui/Select";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { SyncSignal } from "@/components/badges/SyncSignal";
import { TextField } from "@/components/ui/TextField";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { tradeSyncToState } from "./Dashboard";
import { PageHeader } from "./PageHeader";
import { formatCurrency, relativeTime } from "@/lib/format";
import { latestBrokerSyncTimestamp } from "@/lib/brokerSync";

export function Accounts(): JSX.Element {
  const list = useQuery({
    queryKey: ["accounts", "list"],
    queryFn: () => AccountsApi.list(),
    refetchInterval: 15_000,
  });
  const streams = useQuery({
    queryKey: ["system", "streams"],
    queryFn: () => SystemApi.streams(),
    refetchInterval: 5_000,
  });
  const overview = useQuery({
    queryKey: ["operations", "overview"],
    queryFn: () => OperationsApi.overview(),
    refetchInterval: 8_000,
  });
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Accounts"
        subtitle="Broker-connected trading accounts. Provider + mode metadata only — paper and live are not separate runtimes."
        explainSlug="accounts"
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setCreateOpen(true)}
          >
            Add Account
          </Button>
        }
      />

      {list.isLoading ? (
        <LoadingState title="Loading accounts" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load accounts"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : list.data?.accounts.length === 0 ? (
        <EmptyState
          title="No accounts yet"
          message="Add a broker Account (Paper or Live) to begin. Ultimate Trader supports Alpaca today."
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {list.data?.accounts.map((a) => (
            <AccountCard
              key={a.id}
              account={a}
              tradeStream={streams.data?.trade_streams.find((s) => s.account_id === a.id)}
              accountSummary={overview.data?.broker_accounts.find((summary) => summary.account_id === a.id)}
            />
          ))}
        </div>
      )}

      <CreateAccountDrawer open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

function AccountCard({
  account,
  tradeStream,
  accountSummary,
}: {
  account: BrokerAccount;
  tradeStream: TradeStreamStatus | undefined;
  accountSummary: AccountSummary | undefined;
}): JSX.Element {
  const qc = useQueryClient();
  const [credsOpen, setCredsOpen] = useState(false);
  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);

  const opAccount = useQuery({
    queryKey: ["operations", "account", account.id],
    queryFn: () => OperationsApi.account(account.id),
    refetchInterval: 8_000,
  });

  const remove = useMutation({
    mutationFn: () => AccountsApi.delete(account.id, account.display_name, account.mode),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["accounts", "list"] });
      void qc.invalidateQueries({ queryKey: ["operations", "overview"] });
    },
  });

  const isLive = account.mode === "BROKER_LIVE";
  const equity =
    accountSummary?.snapshot?.equity ??
    opAccount.data?.broker_account_snapshot?.equity ??
    account.last_account_snapshot?.equity ??
    null;
  const cash =
    accountSummary?.snapshot?.cash ??
    opAccount.data?.broker_account_snapshot?.cash ??
    account.last_account_snapshot?.cash ??
    null;
  const buyingPower =
    accountSummary?.snapshot?.buying_power ??
    opAccount.data?.broker_account_snapshot?.buying_power ??
    account.last_account_snapshot?.buying_power ??
    null;
  const brokerSync =
    accountSummary?.sync_state ?? opAccount.data?.broker_sync_freshness ?? account.broker_sync_freshness ?? null;
  const stale = brokerSync?.is_stale ?? false;
  const lastSyncAt = latestBrokerSyncTimestamp(brokerSync);
  const openBrokerOrders = opAccount.data?.open_broker_orders ?? [];
  const positions = opAccount.data?.positions ?? [];
  const openOrderCount = Math.max(accountSummary?.open_orders_count ?? 0, openBrokerOrders.length);
  const positionCount = Math.max(accountSummary?.positions_count ?? 0, positions.length);

  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <div className="min-w-0 flex-1">
          <div className="font-semibold tracking-tight">{account.display_name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge tone="info">{account.provider}</StatusBadge>
            <StatusBadge tone={isLive ? "danger" : "ok"}>{isLive ? "Live" : "Paper"}</StatusBadge>
            {account.needs_credentials ? (
              <StatusBadge tone="warn">Needs Credentials</StatusBadge>
            ) : (
              <StatusBadge tone="ok">Credentials Valid</StatusBadge>
            )}
            {stale ? <StatusBadge tone="warn">Sync Stale</StatusBadge> : <StatusBadge tone="ok">Sync Fresh</StatusBadge>}
            {tradeStream ? <SyncSignal state={tradeSyncToState(tradeStream)} /> : null}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 px-4 py-3 text-xs">
        <KeyValue label="Equity" value={formatCurrency(equity)} />
        <KeyValue label="Cash" value={formatCurrency(cash)} />
        <KeyValue label="Buying Power" value={formatCurrency(buyingPower)} />
        <KeyValue label="Open Orders" value={String(openOrderCount)} />
        <KeyValue label="Positions" value={String(positionCount)} />
        <KeyValue label="Last sync" value={lastSyncAt ? relativeTime(lastSyncAt) : "—"} />
      </div>

      {openBrokerOrders.length > 0 ? (
        <div className="border-t border-border/70 px-4 py-2">
          <div className="mb-1 text-xs font-medium text-fg-subtle">Open broker orders</div>
          <div className="space-y-1">
            {openBrokerOrders.slice(0, 3).map((order) => (
              <div
                key={order.broker_order_id}
                className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 text-xs"
              >
                <span className="truncate font-medium text-fg">{order.symbol}</span>
                <span className="tabular text-fg-muted">
                  {(order.side ?? "—").toUpperCase()} {order.qty ?? "—"}
                </span>
                <StatusBadge tone="info">{order.status}</StatusBadge>
              </div>
            ))}
            {openBrokerOrders.length > 3 ? (
              <div className="text-xs text-fg-subtle">+{openBrokerOrders.length - 3} more in View</div>
            ) : null}
          </div>
        </div>
      ) : null}

      {positions.length > 0 ? (
        <div className="border-t border-border/70 px-4 py-2">
          <div className="mb-1 text-xs font-medium text-fg-subtle">Open positions</div>
          <div className="space-y-1">
            {positions.slice(0, 3).map((position) => (
              <div
                key={`${position.symbol}-${position.quantity}`}
                className="grid grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-2 text-xs"
              >
                <span className="truncate font-medium text-fg">{position.symbol}</span>
                <span className="tabular text-fg-muted">
                  {(position.side ?? "—").toUpperCase()} {position.quantity}
                </span>
                <span className={position.unrealized_pl && position.unrealized_pl < 0 ? "text-danger" : "text-ok"}>
                  {formatCurrency(position.unrealized_pl ?? null)}
                </span>
              </div>
            ))}
            {positions.length > 3 ? (
              <div className="text-xs text-fg-subtle">+{positions.length - 3} more in View</div>
            ) : null}
          </div>
        </div>
      ) : null}

      {account.needs_credentials ? (
        <div className="px-4 pb-3">
          <Banner
            severity="warning"
            title="Operator must enter credentials"
            message="The encrypted store has no entry for this Account. Trading is gated until you re-enter."
          />
        </div>
      ) : null}

      <div className="flex flex-wrap gap-1 border-t border-border/70 px-4 py-2">
        <Button
          size="sm"
          variant="primary"
          leftIcon={<Eye className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={() => setDetailOpen(true)}
        >
          View
        </Button>
        <Button
          size="sm"
          variant="secondary"
          leftIcon={<KeyRound className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={() => setCredsOpen(true)}
        >
          Edit Credentials
        </Button>
        <Button
          size="sm"
          variant="ghost"
          leftIcon={<Pencil className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={() => setRenameOpen(true)}
        >
          Rename
        </Button>
        <Button
          size="sm"
          variant="danger"
          leftIcon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={() => setDeleteOpen(true)}
        >
          Delete
        </Button>
      </div>

      <AccountDetailDrawer open={detailOpen} onOpenChange={setDetailOpen} account={account} />
      <ReplaceCredentialsDrawer open={credsOpen} onOpenChange={setCredsOpen} account={account} />
      <RenameDrawer open={renameOpen} onOpenChange={setRenameOpen} account={account} />
      <DangerConfirm
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Delete Account "${account.display_name}"?`}
        message={
          <span>
            This deletes the Account record and stops its Trade Sync. Type{" "}
            <strong>{account.display_name}</strong> to confirm. The account will be archived if it has lineage; hard-deleted otherwise.
          </span>
        }
        expected={account.display_name}
        actionLabel="Delete Account"
        tone="danger"
        busy={remove.isPending}
        onConfirm={async () => {
          try {
            await remove.mutateAsync();
          } finally {
            setDeleteOpen(false);
          }
        }}
      />
    </Card>
  );
}

function KeyValue({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-fg-subtle">{label}</span>
      <span className="tabular text-fg">{value}</span>
    </div>
  );
}

function ReplaceCredentialsDrawer({
  open,
  onOpenChange,
  account,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  account: BrokerAccount;
}): JSX.Element {
  const qc = useQueryClient();
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const replace = useMutation({
    mutationFn: () => AccountsApi.replaceCredentials(account.id, apiKey, apiSecret),
    onSuccess: (resp) => {
      setError(null);
      setNotice(`Validation: ${resp.validation_status}. ${resp.message}`);
      setApiKey("");
      setApiSecret("");
      void qc.invalidateQueries({ queryKey: ["accounts", "list"] });
    },
    onError: (e) => setError(e instanceof ApiError ? `${e.detail || e.message}` : String(e)),
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Edit credentials · {account.display_name}</DrawerTitle>
          <DrawerDescription>
            Secrets are stored encrypted (AES-GCM). They never round-trip through the browser after save.
            Mode ({account.mode}) is pinned and cannot change.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Validation failed" message={error} /> : null}
          {notice ? <Banner severity="info" title="Saved" message={notice} /> : null}
          <TextField label="API Key" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          <TextField label="API Secret" type="password" autoComplete="off" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!apiKey || !apiSecret}
            loading={replace.isPending}
            onClick={() => replace.mutate()}
          >
            Save credentials
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function RenameDrawer({
  open,
  onOpenChange,
  account,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  account: BrokerAccount;
}): JSX.Element {
  const qc = useQueryClient();
  const [name, setName] = useState(account.display_name);
  const [error, setError] = useState<string | null>(null);

  const rename = useMutation({
    mutationFn: () => AccountsApi.updateDetails(account.id, name.trim()),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["accounts", "list"] });
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Rename Account</DrawerTitle>
          <DrawerDescription>Display name only. Mode and credentials are unaffected.</DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Update failed" message={error} /> : null}
          <TextField label="Display name" value={name} onChange={(e) => setName(e.target.value)} />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            variant="primary"
            size="sm"
            loading={rename.isPending}
            disabled={!name.trim() || name.trim() === account.display_name}
            onClick={() => rename.mutate()}
          >
            Save name
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function CreateAccountDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const [displayName, setDisplayName] = useState("");
  const [mode, setMode] = useState<TradingMode>("BROKER_PAPER");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  function reset(): void {
    setDisplayName("");
    setMode("BROKER_PAPER");
    setApiKey("");
    setApiSecret("");
    setError(null);
  }

  const create = useMutation({
    mutationFn: () =>
      AccountsApi.create({
        display_name: displayName.trim(),
        provider: "alpaca",
        mode,
        api_key: apiKey.trim(),
        api_secret: apiSecret.trim(),
      }),
    onSuccess: () => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["accounts", "list"] });
      void qc.invalidateQueries({ queryKey: ["operations", "overview"] });
      void qc.invalidateQueries({ queryKey: ["system", "streams"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const formValid = displayName.trim().length > 0 && apiKey.trim().length > 0 && apiSecret.trim().length > 0;
  const isLive = mode === "BROKER_LIVE";

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Add Account</DrawerTitle>
          <DrawerDescription>
            Provider + mode pinned at create. Backend derives the broker base URL from those.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not create" message={error} /> : null}
          {isLive ? (
            <Banner
              severity="warning"
              title="LIVE Account"
              message="You will trade real money. We'll require type-name-to-confirm before save."
            />
          ) : null}
          <TextField label="Display name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          <Select label="Mode" value={mode} onChange={(e) => setMode(e.target.value as TradingMode)}>
            <option value="BROKER_PAPER">Paper</option>
            <option value="BROKER_LIVE">Live</option>
          </Select>
          <TextField label="API Key" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
          <TextField label="API Secret" type="password" autoComplete="off" value={apiSecret} onChange={(e) => setApiSecret(e.target.value)} />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant={isLive ? "danger" : "primary"}
            size="sm"
            disabled={!formValid}
            loading={create.isPending}
            onClick={() => {
              if (isLive) setConfirmOpen(true);
              else create.mutate();
            }}
          >
            {isLive ? "Confirm and create LIVE Account" : "Create Account"}
          </Button>
        </DrawerFooter>
      </DrawerContent>
      <DangerConfirm
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Confirm LIVE Account creation"
        message={
          <span>
            You are registering real-money credentials for{" "}
            <strong>{displayName.trim()}</strong>. Type that exact name to confirm.
          </span>
        }
        expected={displayName.trim()}
        actionLabel="Create LIVE Account"
        tone="danger"
        busy={create.isPending}
        onConfirm={async () => {
          await create.mutateAsync();
          setConfirmOpen(false);
        }}
      />
    </Drawer>
  );
}

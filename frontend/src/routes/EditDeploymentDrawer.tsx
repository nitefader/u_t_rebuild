import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { AccountsApi } from "@/api/accounts";
import { DeploymentsApi } from "@/api/deployments";
import { WatchlistsApi } from "@/api/watchlists";
import type { Deployment } from "@/api/schemas/deployments";
import { TRADING_HORIZON_LABELS, type TradingHorizon } from "@/api/schemas/risk";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
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
import { TextField } from "@/components/ui/TextField";

export function EditDeploymentDrawer({
  open,
  onOpenChange,
  deployment,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  deployment: Deployment;
}): JSX.Element {
  const qc = useQueryClient();
  const watchlists = useQuery({ queryKey: ["watchlists", "list"], queryFn: () => WatchlistsApi.list(), enabled: open });
  const accounts = useQuery({ queryKey: ["accounts", "list"], queryFn: () => AccountsApi.list(), enabled: open });

  const [name, setName] = useState(deployment.name);
  const [description, setDescription] = useState(deployment.description ?? "");
  const [watchlistIds, setWatchlistIds] = useState<string[]>([...deployment.watchlist_ids]);
  const [accountIds, setAccountIds] = useState<string[]>([...deployment.subscribed_account_ids]);
  const [riskHorizon, setRiskHorizon] = useState<TradingHorizon | "">(
    deployment.risk_horizon ?? "",
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(deployment.name);
    setDescription(deployment.description ?? "");
    setWatchlistIds([...deployment.watchlist_ids]);
    setAccountIds([...deployment.subscribed_account_ids]);
    setRiskHorizon(deployment.risk_horizon ?? "");
    setError(null);
  }, [open, deployment]);

  const editable = deployment.lifecycle_status !== "active";

  const save = useMutation({
    mutationFn: () =>
      DeploymentsApi.update(deployment.deployment_id, {
        name: name.trim(),
        description: description.trim() || null,
        strategy_version_id: deployment.strategy_version_id,
        watchlist_ids: watchlistIds,
        subscribed_account_ids: accountIds,
        runtime_overrides: deployment.runtime_overrides,
        risk_horizon: riskHorizon !== "" ? riskHorizon : null,
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["deployments", "list"] });
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const subscribe = useMutation({
    mutationFn: (accountId: string) => DeploymentsApi.subscribe(deployment.deployment_id, accountId),
    onSuccess: (resp) => {
      setAccountIds([...resp.deployment.subscribed_account_ids]);
      void qc.invalidateQueries({ queryKey: ["deployments", "list"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });
  const unsubscribe = useMutation({
    mutationFn: (accountId: string) => DeploymentsApi.unsubscribe(deployment.deployment_id, accountId),
    onSuccess: (resp) => {
      setAccountIds([...resp.deployment.subscribed_account_ids]);
      void qc.invalidateQueries({ queryKey: ["deployments", "list"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Edit deployment · {deployment.name}</DrawerTitle>
          <DrawerDescription>
            {editable
              ? "Pause or stop the deployment to change Strategy version or watchlists. Subscriptions can change at any time."
              : "This deployment is ACTIVE. Only Account subscriptions can change while it runs. Pause it to edit other fields."}
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Update failed" message={error} /> : null}
          <TextField
            label="Display name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={!editable}
          />
          <TextField
            label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={!editable}
          />

          <Select
            label="Risk horizon"
            value={riskHorizon}
            onChange={(e) => setRiskHorizon(e.target.value as TradingHorizon | "")}
            disabled={!editable}
            hint="Determines which per-horizon RiskPlan each Account uses. Deployment chooses horizon; Account chooses RiskPlan; Governor enforces."
          >
            <option value="">— use Strategy default —</option>
            {(Object.entries(TRADING_HORIZON_LABELS) as [TradingHorizon, string][]).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </Select>
          {/* Slice B fix B-RISK-1: when no explicit horizon is declared, the
              Governor does NOT fire the missing-plan rejection rule (it only
              activates on explicit horizons). Surface this so the operator
              knows enforcement is opt-in. */}
          {riskHorizon === "" && editable ? (
            <Banner
              severity="warning"
              title="Per-horizon RiskPlan enforcement is OFF"
              message="With no explicit risk horizon, the Governor will not require subscribed Accounts to map a RiskPlan for this Deployment. Only AccountRiskConfig limits and the Strategy default horizon's plan (if any) apply."
            />
          ) : null}

          <div>
            <div className="mb-1 text-xs text-fg-muted">Watchlists</div>
            <div className="grid max-h-32 grid-cols-1 gap-1 overflow-y-auto rounded border border-border bg-bg-inset p-2 text-sm">
              {(watchlists.data?.watchlists ?? []).map((w) => (
                <label key={w.watchlist_id} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    disabled={!editable}
                    checked={watchlistIds.includes(w.watchlist_id)}
                    onChange={(e) =>
                      setWatchlistIds((prev) =>
                        e.target.checked
                          ? [...prev, w.watchlist_id]
                          : prev.filter((id) => id !== w.watchlist_id),
                      )
                    }
                  />
                  <span className="truncate">{w.name}</span>
                  <span className="ml-auto text-xs text-fg-muted">{w.kind}</span>
                </label>
              ))}
              {(watchlists.data?.watchlists ?? []).length === 0 ? (
                <span className="text-xs text-fg-muted">No watchlists configured.</span>
              ) : null}
            </div>
          </div>

          <div>
            <div className="mb-1 flex items-center justify-between text-xs text-fg-muted">
              <span>Subscribed accounts</span>
              {!editable ? (
                <StatusBadge tone="info">live subscribe / unsubscribe</StatusBadge>
              ) : null}
            </div>
            <div className="grid max-h-40 grid-cols-1 gap-1 overflow-y-auto rounded border border-border bg-bg-inset p-2 text-sm">
              {(accounts.data?.accounts ?? []).map((a) => {
                const isSubscribed = accountIds.includes(a.id);
                return (
                  <div key={a.id} className="flex items-center gap-2">
                    {editable ? (
                      <input
                        type="checkbox"
                        checked={isSubscribed}
                        onChange={(e) =>
                          setAccountIds((prev) =>
                            e.target.checked ? [...prev, a.id] : prev.filter((id) => id !== a.id),
                          )
                        }
                      />
                    ) : (
                      <StatusBadge tone={isSubscribed ? "ok" : "muted"} size="sm">
                        {isSubscribed ? "subscribed" : "—"}
                      </StatusBadge>
                    )}
                    <span className="truncate">{a.display_name}</span>
                    <span className="ml-auto text-xs text-fg-muted">
                      {a.mode === "BROKER_LIVE" ? "Live" : "Paper"}
                    </span>
                    {!editable ? (
                      isSubscribed ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => unsubscribe.mutate(a.id)}
                          loading={unsubscribe.isPending}
                        >
                          Unsubscribe
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="primary"
                          onClick={() => subscribe.mutate(a.id)}
                          loading={subscribe.isPending}
                        >
                          Subscribe
                        </Button>
                      )
                    ) : null}
                  </div>
                );
              })}
              {(accounts.data?.accounts ?? []).length === 0 ? (
                <span className="text-xs text-fg-muted">No accounts configured.</span>
              ) : null}
            </div>
          </div>
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          {editable ? (
            <Button
              variant="primary"
              size="sm"
              loading={save.isPending}
              disabled={!name.trim() || watchlistIds.length === 0 || accountIds.length === 0}
              onClick={() => save.mutate()}
            >
              Save
            </Button>
          ) : null}
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

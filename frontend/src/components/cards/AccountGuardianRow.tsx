import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Shield, ShieldCheck, X } from "lucide-react";
import { AccountsApi } from "@/api/accounts";
import { DeploymentsApi } from "@/api/deployments";
import type { BrokerAccount } from "@/api/schemas/accounts";
import { ApiError } from "@/api/client";
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
import { Banner } from "@/components/ui/Banner";
import { useToast } from "@/components/ui/Toast";

/**
 * AccountGuardianRow — operator UI for M11 Account Guardian Assignment.
 *
 * State surfaces (M11 plan FR11.8 + FR11.9):
 *   None  →  "Guardian: None [Select Guardian Deployment]"
 *   Set   →  "Guardian: <Name>  [Change] [Remove]"
 *
 * Selection drawer lists every Deployment subscribed to this Account
 * (the natural candidate set), filtered to only those the operator has
 * authority to set as Guardian. No "auto-select first compatible"
 * option — operator decision (plan resolved Q-AutoSelect: drop).
 *
 * Mutates via AccountsApi.setGuardian which calls
 *   PUT /api/v1/broker-accounts/{id}/guardian
 * Backend route owned by Codex (queued in INBOX_CODEX).
 */
export interface AccountGuardianRowProps {
  account: BrokerAccount;
}

export function AccountGuardianRow({ account }: AccountGuardianRowProps): JSX.Element {
  const [selectOpen, setSelectOpen] = useState(false);

  const guardianId = account.guardian_deployment_id ?? null;
  const guardianName = account.guardian_deployment_name ?? null;

  return (
    <div className="flex flex-wrap items-center gap-2 border-t border-border/70 px-4 py-2 text-xs">
      <Shield
        className={`h-3.5 w-3.5 ${guardianId ? "text-accent" : "text-fg-subtle"}`}
        aria-hidden="true"
      />
      <span className="font-medium text-fg-muted">Guardian:</span>
      {guardianId ? (
        <>
          <span className="font-semibold text-fg">{guardianName ?? "(unknown name)"}</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setSelectOpen(true)}
            aria-label={`Change Guardian for ${account.display_name}`}
          >
            Change
          </Button>
          <RemoveGuardianButton account={account} />
        </>
      ) : (
        <>
          <span className="text-fg-subtle">None</span>
          <Button
            size="sm"
            variant="secondary"
            leftIcon={<ShieldCheck className="h-3 w-3" aria-hidden="true" />}
            onClick={() => setSelectOpen(true)}
            aria-label={`Select Guardian Deployment for ${account.display_name}`}
          >
            Select Guardian Deployment
          </Button>
        </>
      )}

      {selectOpen ? (
        <SelectGuardianDrawer
          account={account}
          open={selectOpen}
          onOpenChange={setSelectOpen}
        />
      ) : null}
    </div>
  );
}

function RemoveGuardianButton({ account }: { account: BrokerAccount }): JSX.Element {
  const qc = useQueryClient();
  const toast = useToast();
  const remove = useMutation({
    mutationFn: () => AccountsApi.setGuardian(account.id, null),
    onSuccess: () => {
      toast.show({
        severity: "ok",
        title: `Guardian removed from "${account.display_name}"`,
        description: "Account no longer has a Guardian. Existing adopted positions retain their lineage.",
      });
      void qc.invalidateQueries({ queryKey: ["accounts", "list"] });
      void qc.invalidateQueries({ queryKey: ["operations", "account", account.id] });
    },
    onError: (e) =>
      toast.show({
        severity: "danger",
        title: "Could not remove Guardian",
        description: e instanceof ApiError ? e.detail ?? e.message : String(e),
      }),
  });
  return (
    <Button
      size="sm"
      variant="ghost"
      leftIcon={<X className="h-3 w-3" aria-hidden="true" />}
      loading={remove.isPending}
      onClick={() => remove.mutate()}
      aria-label={`Remove Guardian from ${account.display_name}`}
    >
      Remove
    </Button>
  );
}

function SelectGuardianDrawer({
  account,
  open,
  onOpenChange,
}: {
  account: BrokerAccount;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const toast = useToast();
  const [selected, setSelected] = useState<string>(
    account.guardian_deployment_id ?? "",
  );
  const [error, setError] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ["deployments", "list", "guardian-pick"],
    queryFn: () => DeploymentsApi.list(),
    staleTime: 30_000,
  });

  const candidates = useMemo(() => {
    const all = list.data?.deployments ?? [];
    // Prefer Deployments subscribed to this Account — the natural
    // candidate set per M11 plan. If the backend list endpoint doesn't
    // surface `subscribed_account_ids` (or returns it empty for every
    // row), fall back to ALL Deployments so the operator can still pick
    // a Guardian. The drawer banner clarifies the fallback when it fires.
    const subscribed = all.filter((d) => {
      const subs = (d as { subscribed_account_ids?: string[] }).subscribed_account_ids ?? [];
      return subs.includes(account.id);
    });
    if (subscribed.length > 0) return subscribed;
    return all;
  }, [list.data, account.id]);

  const usingFallback =
    !list.isLoading
    && (list.data?.deployments?.length ?? 0) > 0
    && candidates.length > 0
    && !candidates.some((d) => {
      const subs = (d as { subscribed_account_ids?: string[] }).subscribed_account_ids ?? [];
      return subs.includes(account.id);
    });

  const assign = useMutation({
    mutationFn: () =>
      AccountsApi.setGuardian(account.id, selected.trim() === "" ? null : selected),
    onSuccess: () => {
      toast.show({
        severity: "ok",
        title: `Guardian set on "${account.display_name}"`,
        description: "The selected Deployment can now adopt orphaned or owner-down positions for this Account.",
      });
      void qc.invalidateQueries({ queryKey: ["accounts", "list"] });
      void qc.invalidateQueries({ queryKey: ["operations", "account", account.id] });
      onOpenChange(false);
    },
    onError: (e) => {
      const detail = e instanceof ApiError ? e.detail ?? e.message : String(e);
      setError(detail);
      toast.show({ severity: "danger", title: "Could not set Guardian", description: detail });
    },
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Select Guardian Deployment</DrawerTitle>
          <DrawerDescription>
            Pre-authorize one Deployment to adopt orphaned positions or positions whose owner
            Deployment is down on <strong>{account.display_name}</strong>. Adoption is one-way;
            operator can manually transfer ownership back later. Guardian does not bypass
            Governor and only adopts positions that are NOT already protected by existing
            broker orders.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not set Guardian" message={error} /> : null}
          {usingFallback ? (
            <Banner
              severity="info"
              title="Listing all Deployments"
              message="No Deployments report a subscription to this Account; showing all Deployments so you can still assign a Guardian. The chosen Deployment does not have to be subscribed."
            />
          ) : null}
          {list.isLoading ? (
            <div className="text-xs text-fg-muted">Loading Deployments…</div>
          ) : candidates.length === 0 ? (
            <Banner
              severity="info"
              title="No Deployments yet"
              message="No Deployments exist on this platform. Create one before assigning a Guardian."
            />
          ) : (
            <Select
              label="Guardian Deployment"
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
            >
              <option value="">— None —</option>
              {candidates.map((d) => (
                <option key={d.deployment_id} value={d.deployment_id}>
                  {d.name}
                </option>
              ))}
            </Select>
          )}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            loading={assign.isPending}
            disabled={selected === (account.guardian_deployment_id ?? "")}
            onClick={() => assign.mutate()}
          >
            Save Guardian
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

import { Shield, ShieldAlert, ShieldCheck, ShieldOff } from "lucide-react";
import type { BrokerPositionSnapshot } from "@/api/schemas/operations";
import { StatusBadge } from "./StatusBadge";

/**
 * GuardianBadges — surfaces Guardian + adoption lineage state on a
 * position row. Each badge is operator-readable; raw IDs never appear
 * (per AGENTS.md "Human-Readable Frontend Data Rule").
 *
 * State matrix (M11 plan FR11.7 + FR11.4 cases):
 *   1. snapshot.deployment_name + adoption_status="managed"      → "Managed by <Name>"
 *   2. adoption_status="adopted_by_guardian", reason="owner_unknown"
 *                                                                → "Adopted by <Guardian>" + "Orphan adopted"
 *   3. adoption_status="adopted_by_guardian", reason="owner_deployment_down_unprotected"
 *                                                                → "Adopted by <Guardian>" + "Owner Down: <orig>"
 *   4. owner_deployment_healthy=false + owner_self_protected=true → "Owner Down (Self-Protected)"
 *      (no Guardian adoption — broker's own protective orders cover it; FR11.4 case 4)
 *   5. unmanaged_broker_position=true                             → "Unmanaged"
 *
 * The component is read-only — adoption / transfer actions live in
 * GuardianTransferAction (separate component using HoldToArmConfirm).
 */
export interface GuardianBadgesProps {
  snapshot: BrokerPositionSnapshot;
  /** When provided, also renders the Account-level "Guardian Active" chip. */
  accountGuardianName?: string | null;
}

export function GuardianBadges({
  snapshot,
  accountGuardianName,
}: GuardianBadgesProps): JSX.Element | null {
  const adoption = snapshot.adoption_status ?? null;
  const reason = snapshot.adoption_reason ?? null;
  const ownerName =
    snapshot.original_owner_deployment_name ?? snapshot.deployment_name ?? null;
  const guardianName = accountGuardianName ?? snapshot.deployment_name ?? null;
  const ownerHealthy = snapshot.owner_deployment_healthy ?? null;
  const selfProtected = snapshot.owner_self_protected ?? null;
  const unmanaged = snapshot.unmanaged_broker_position ?? false;

  const items: JSX.Element[] = [];

  if (adoption === "adopted_by_guardian") {
    items.push(
      <StatusBadge key="adopted" tone="info">
        <Shield className="h-3 w-3" aria-hidden="true" />
        Adopted by {guardianName ?? "Guardian"}
      </StatusBadge>,
    );
    if (reason === "owner_unknown") {
      items.push(
        <StatusBadge key="orphan" tone="warn">
          Orphan adopted
        </StatusBadge>,
      );
    } else if (reason === "owner_deployment_down_unprotected" && ownerName) {
      items.push(
        <StatusBadge key="ownerdown" tone="warn">
          <ShieldOff className="h-3 w-3" aria-hidden="true" />
          Owner Down: {ownerName}
        </StatusBadge>,
      );
    }
  } else if (ownerHealthy === false && selfProtected === true) {
    // FR11.4 case 4 — Guardian intentionally did NOT adopt because
    // broker's existing protective orders cover the position.
    items.push(
      <StatusBadge key="ownerdown-protected" tone="info">
        <ShieldCheck className="h-3 w-3" aria-hidden="true" />
        Owner Down (Self-Protected){ownerName ? `: ${ownerName}` : ""}
      </StatusBadge>,
    );
  } else if (unmanaged || adoption === "unmanaged") {
    items.push(
      <StatusBadge key="unmanaged" tone="warn">
        <ShieldAlert className="h-3 w-3" aria-hidden="true" />
        Unmanaged
      </StatusBadge>,
    );
  }

  if (accountGuardianName && adoption !== "adopted_by_guardian") {
    items.push(
      <StatusBadge key="guardian-active" tone="muted">
        <Shield className="h-3 w-3" aria-hidden="true" />
        Guardian: {accountGuardianName}
      </StatusBadge>,
    );
  }

  if (items.length === 0) return null;
  return <div className="flex flex-wrap items-center gap-1">{items}</div>;
}

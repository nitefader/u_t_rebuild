/**
 * T-5 Bracket Program — single source of truth for the operator-visible
 * protection_status badge tone + label across Operations surfaces.
 *
 * Single definition shared by AccountDetailDrawer (per-account Open
 * Positions card) and OperationsLedger (all-accounts Positions table).
 * Adding a future status value requires editing only this file.
 *
 * Critic Fix #8 (T-5): unknown status values render with a `warn` tone
 * and an explicit "?" label, NOT silently as neutral "—". Silent
 * neutral hides backend additions that the frontend has not yet
 * adopted, which is the same kind of "no operator signal" failure
 * mode that PROTECTION_NAKED is supposed to prevent.
 */

export type ProtectionTone = "ok" | "warn" | "danger" | "neutral";

export interface ProtectionDisplay {
  tone: ProtectionTone;
  label: string;
  /**
   * `title` provides a tooltip explaining what the operator sees, so
   * "Protected (2)" doesn't make the operator wonder if they have a
   * duplicate stop, and "—" doesn't conflate "no protection state" with
   * "missing data".
   */
  title: string;
}

export function getProtectionDisplay(
  protectionStatus: string,
  protectiveOrderCount: number,
): ProtectionDisplay {
  switch (protectionStatus) {
    case "protected":
      return {
        tone: "ok",
        label: `Protected (${protectiveOrderCount})`,
        title:
          protectiveOrderCount > 1
            ? `${protectiveOrderCount} active stop orders — normal for incremental fill coverage as partial fills accumulate`
            : "Active stop order in place",
      };
    case "naked":
      return {
        tone: "danger",
        label: "NAKED",
        title:
          "Entry filled but no active protective stop. Operator action required.",
      };
    case "pending_protection":
      return {
        tone: "warn",
        label: "Stop Pending",
        title:
          "Stop child created but not yet acknowledged by the broker. Will flip to Protected once the broker accepts.",
      };
    case "unknown":
      return {
        tone: "neutral",
        label: "—",
        title:
          "Position not tracked by the bracket runtime (manual position, legacy lineage, or pre-T-5 entry).",
      };
    default:
      return {
        tone: "warn",
        label: `? (${protectionStatus})`,
        title: `Unknown protection status "${protectionStatus}" — frontend has not been updated for a new backend value. Investigate.`,
      };
  }
}

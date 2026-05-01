/**
 * draftDefaults — minimal valid placeholder shapes for fields not yet surfaced in the Slice 6 UI.
 * These are the single canonical place where backend validator minimums are encoded.
 * Slices 7 and 8 will replace these stubs with real UI.
 */

import type {
  StrategyStopV4Draft,
  StrategyLegV4Draft,
  StrategyLogicalExitV4Draft,
} from "@/api/schemas/strategiesV4";

function uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/** Smallest valid stop array — one simple % stop covering all legs. */
export function buildPlaceholderStops(): StrategyStopV4Draft[] {
  return [
    {
      id: uuid(),
      mode: "simple",
      scope: "all",
      simple_type: "%",
      simple_value: 1.0,
    },
  ];
}

/**
 * Smallest valid legs array — one 100% target leg.
 * sum(size_pct) = 1.0 satisfies the backend validator.
 */
export function buildPlaceholderLegs(): StrategyLegV4Draft[] {
  return [
    {
      id: uuid(),
      position: 1,
      kind: "target",
      size_pct: 1.0,
      target_type: "%",
      target_value: 2.0,
      on_fill_action: { kind: "be_exact" },
    },
  ];
}

/** Empty logical exits object (backend accepts empty arrays). */
export function buildPlaceholderLogicalExits(): {
  long: StrategyLogicalExitV4Draft[];
  short: StrategyLogicalExitV4Draft[];
} {
  return { long: [], short: [] };
}

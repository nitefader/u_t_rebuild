/**
 * legAutoBalance — pure helpers for managing leg size_pct distribution.
 *
 * All size_pct values are in the 0..1 range (matching the backend domain).
 * Display layer is responsible for converting to/from percentages.
 */

import type { StrategyStopV4Draft, StrategyLegV4Draft } from "@/api/schemas/strategiesV4";

// Re-export the draft types used by callers for convenience.
export type LegDraft = StrategyLegV4Draft;
export type StopDraft = StrategyStopV4Draft;

const PRECISION = 4;
const SUM_TOLERANCE = 1e-6;

function round4(n: number): number {
  return Math.round(n * 10 ** PRECISION) / 10 ** PRECISION;
}

/**
 * Redistribute size_pct evenly across all legs (each gets 1/N).
 * Rounds to 4 decimal places; nudges the last leg so the sum is exactly 1.0.
 */
export function autoBalance(legs: LegDraft[]): LegDraft[] {
  if (legs.length === 0) return [];
  const share = round4(1 / legs.length);
  const result = legs.map((leg) => ({ ...leg, size_pct: share }));
  // Correct rounding error on the last leg
  const partialSum = result.slice(0, -1).reduce((acc, l) => acc + l.size_pct, 0);
  result[result.length - 1] = {
    ...result[result.length - 1],
    size_pct: round4(1.0 - partialSum),
  };
  return result;
}

/**
 * Remove the leg at removedIndex; reassign positions 1..N-1; redistribute
 * the removed leg's size_pct proportionally onto the remaining legs.
 * Sum stays 1.0.
 */
export function redistributeOnRemove(legs: LegDraft[], removedIndex: number): LegDraft[] {
  if (legs.length <= 1) return legs; // cannot remove the last leg
  const removed = legs[removedIndex];
  const remaining = legs.filter((_, i) => i !== removedIndex);
  const removedShare = removed.size_pct;
  const remainingSum = remaining.reduce((acc, l) => acc + l.size_pct, 0);

  let redistributed: LegDraft[];
  if (remainingSum < SUM_TOLERANCE) {
    // degenerate: distribute evenly
    redistributed = autoBalance(remaining);
  } else {
    redistributed = remaining.map((leg) => ({
      ...leg,
      size_pct: round4(leg.size_pct + removedShare * (leg.size_pct / remainingSum)),
    }));
    // correct rounding error
    const partialSum = redistributed.slice(0, -1).reduce((acc, l) => acc + l.size_pct, 0);
    redistributed[redistributed.length - 1] = {
      ...redistributed[redistributed.length - 1],
      size_pct: round4(1.0 - partialSum),
    };
  }

  // Reassign contiguous positions 1..N
  return redistributed.map((leg, i) => ({ ...leg, position: i + 1 }));
}

/**
 * Append a new leg with a fair share by re-running auto-balance over all legs.
 */
export function appendLegEvenly(
  legs: LegDraft[],
  newLeg: Omit<LegDraft, "size_pct" | "position">,
): LegDraft[] {
  const draft: LegDraft = {
    ...newLeg,
    size_pct: 0, // placeholder; overwritten by autoBalance
    position: legs.length + 1, // placeholder; overwritten below
  };
  const withNew = [...legs, draft];
  const balanced = autoBalance(withNew);
  // Ensure contiguous positions
  return balanced.map((leg, i) => ({ ...leg, position: i + 1 }));
}

/**
 * Validate leg invariants matching the backend domain.
 */
export function validateLegs(legs: LegDraft[]): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (legs.length === 0) {
    return { valid: false, errors: ["At least one leg is required"] };
  }

  // Contiguous positions 1..N
  const sorted = [...legs].sort((a, b) => a.position - b.position);
  for (let i = 0; i < sorted.length; i++) {
    if (sorted[i].position !== i + 1) {
      errors.push(`Leg positions must be contiguous 1..${sorted.length}; position ${i + 1} missing`);
      break;
    }
  }

  // At most one runner
  const runners = legs.filter((l) => l.kind === "runner");
  if (runners.length > 1) {
    errors.push("At most one runner leg is allowed");
  }

  // At least one target
  const targets = legs.filter((l) => l.kind === "target");
  if (targets.length === 0) {
    errors.push("At least one target leg is required");
  }

  // Sum of size_pct == 1.0
  const total = legs.reduce((acc, l) => acc + l.size_pct, 0);
  if (Math.abs(total - 1.0) > SUM_TOLERANCE) {
    errors.push(`Leg sizes must total 100% (currently ${(total * 100).toFixed(2)}%)`);
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate stop invariants matching the backend domain.
 */
export function validateStops(stops: StopDraft[]): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (stops.length === 0) {
    errors.push("At least one stop is required");
  }

  for (let i = 0; i < stops.length; i++) {
    const s = stops[i];
    if (s.mode === "simple") {
      if (!s.simple_type) {
        errors.push(`Stop ${i + 1}: simple_type is required in simple mode`);
      }
      if (s.simple_value == null) {
        errors.push(`Stop ${i + 1}: simple_value is required in simple mode`);
      }
    } else if (s.mode === "expression") {
      if (!s.expression_text || s.expression_text.trim() === "") {
        errors.push(`Stop ${i + 1}: expression_text is required in expression mode`);
      }
    }
  }

  return { valid: errors.length === 0, errors };
}

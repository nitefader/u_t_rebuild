import { describe, expect, it } from "vitest";
import {
  autoBalance,
  redistributeOnRemove,
  appendLegEvenly,
  validateLegs,
  validateStops,
} from "./legAutoBalance";
import type { LegDraft, StopDraft } from "./legAutoBalance";

const SUM_TOLERANCE = 1e-6;

function makeLeg(overrides: Partial<LegDraft> = {}): LegDraft {
  return {
    id: "leg-1",
    position: 1,
    kind: "target",
    size_pct: 1.0,
    target_type: "%",
    target_value: 1.0,
    on_fill_action: { kind: "be_exact" },
    ...overrides,
  };
}

function sumSizePct(legs: LegDraft[]): number {
  return legs.reduce((acc, l) => acc + l.size_pct, 0);
}

// ----------------------------------------------------------------------------
// autoBalance
// ----------------------------------------------------------------------------

describe("autoBalance", () => {
  it("returns empty array for empty input", () => {
    expect(autoBalance([])).toEqual([]);
  });

  it("single leg gets size_pct=1.0", () => {
    const result = autoBalance([makeLeg({ size_pct: 0.3 })]);
    expect(result).toHaveLength(1);
    expect(result[0].size_pct).toBeCloseTo(1.0, 6);
  });

  it("two legs each get 0.5", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, size_pct: 0.8 }),
      makeLeg({ id: "b", position: 2, size_pct: 0.2 }),
    ];
    const result = autoBalance(legs);
    expect(result[0].size_pct).toBeCloseTo(0.5, 4);
    expect(result[1].size_pct).toBeCloseTo(0.5, 4);
    expect(sumSizePct(result)).toBeCloseTo(1.0, 6);
  });

  it("three legs sum to exactly 1.0 after rounding correction", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, size_pct: 0.5 }),
      makeLeg({ id: "b", position: 2, size_pct: 0.3 }),
      makeLeg({ id: "c", position: 3, size_pct: 0.2 }),
    ];
    const result = autoBalance(legs);
    expect(result).toHaveLength(3);
    const total = sumSizePct(result);
    expect(Math.abs(total - 1.0)).toBeLessThanOrEqual(SUM_TOLERANCE);
  });

  it("seven legs sum to exactly 1.0 (rounding stress)", () => {
    const legs = Array.from({ length: 7 }, (_, i) =>
      makeLeg({ id: `l${i}`, position: i + 1, size_pct: 1 / 7 }),
    );
    const result = autoBalance(legs);
    expect(Math.abs(sumSizePct(result) - 1.0)).toBeLessThanOrEqual(SUM_TOLERANCE);
  });

  it("preserves all other fields (id, kind, target_type, etc.)", () => {
    const legs = [
      makeLeg({ id: "keep-a", kind: "runner", target_type: "ATR", target_value: 2.5, position: 1 }),
      makeLeg({ id: "keep-b", kind: "target", target_type: "$", target_value: 5.0, position: 2 }),
    ];
    const result = autoBalance(legs);
    expect(result[0].id).toBe("keep-a");
    expect(result[0].kind).toBe("runner");
    expect(result[0].target_type).toBe("ATR");
    expect(result[1].id).toBe("keep-b");
  });
});

// ----------------------------------------------------------------------------
// redistributeOnRemove
// ----------------------------------------------------------------------------

describe("redistributeOnRemove", () => {
  it("does not remove if only one leg remains", () => {
    const legs = [makeLeg({ id: "only", position: 1, size_pct: 1.0 })];
    const result = redistributeOnRemove(legs, 0);
    expect(result).toHaveLength(1);
  });

  it("removes the correct leg and sum stays 1.0", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, size_pct: 0.5 }),
      makeLeg({ id: "b", position: 2, size_pct: 0.3 }),
      makeLeg({ id: "c", position: 3, size_pct: 0.2 }),
    ];
    const result = redistributeOnRemove(legs, 0); // remove leg 'a'
    expect(result.find((l) => l.id === "a")).toBeUndefined();
    expect(result).toHaveLength(2);
    expect(Math.abs(sumSizePct(result) - 1.0)).toBeLessThanOrEqual(SUM_TOLERANCE);
  });

  it("reassigns positions to be contiguous 1..N-1", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, size_pct: 0.4 }),
      makeLeg({ id: "b", position: 2, size_pct: 0.3 }),
      makeLeg({ id: "c", position: 3, size_pct: 0.3 }),
    ];
    const result = redistributeOnRemove(legs, 1); // remove middle
    expect(result.map((l) => l.position)).toEqual([1, 2]);
  });

  it("redistributes proportionally", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, size_pct: 0.6 }),
      makeLeg({ id: "b", position: 2, size_pct: 0.4 }),
    ];
    // Remove 'a' (size 0.6). 'b' had 0.4 out of 0.4 remaining (100%), so gets all 0.6 added.
    const result = redistributeOnRemove(legs, 0);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("b");
    expect(Math.abs(result[0].size_pct - 1.0)).toBeLessThanOrEqual(SUM_TOLERANCE);
  });
});

// ----------------------------------------------------------------------------
// appendLegEvenly
// ----------------------------------------------------------------------------

describe("appendLegEvenly", () => {
  it("single existing leg splits evenly after append", () => {
    const legs = [makeLeg({ id: "a", position: 1, size_pct: 1.0 })];
    const result = appendLegEvenly(legs, {
      id: "b",
      kind: "target",
      target_type: "%",
      target_value: 1.0,
      on_fill_action: { kind: "be_exact" },
    });
    expect(result).toHaveLength(2);
    expect(Math.abs(sumSizePct(result) - 1.0)).toBeLessThanOrEqual(SUM_TOLERANCE);
    expect(result[0].size_pct).toBeCloseTo(0.5, 4);
    expect(result[1].size_pct).toBeCloseTo(0.5, 4);
  });

  it("assigns sequential positions", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, size_pct: 0.5 }),
      makeLeg({ id: "b", position: 2, size_pct: 0.5 }),
    ];
    const result = appendLegEvenly(legs, {
      id: "c",
      kind: "target",
      target_type: "%",
      target_value: 1.0,
      on_fill_action: { kind: "be_exact" },
    });
    expect(result.map((l) => l.position)).toEqual([1, 2, 3]);
  });
});

// ----------------------------------------------------------------------------
// validateLegs
// ----------------------------------------------------------------------------

describe("validateLegs", () => {
  it("is invalid with empty legs", () => {
    const { valid, errors } = validateLegs([]);
    expect(valid).toBe(false);
    expect(errors.some((e) => /at least one leg/i.test(e))).toBe(true);
  });

  it("is invalid when sum != 1.0", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, size_pct: 0.4 }),
      makeLeg({ id: "b", position: 2, size_pct: 0.3 }),
    ];
    const { valid, errors } = validateLegs(legs);
    expect(valid).toBe(false);
    expect(errors.some((e) => /total/i.test(e))).toBe(true);
  });

  it("is invalid when more than one runner", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, kind: "runner", size_pct: 0.5 }),
      makeLeg({ id: "b", position: 2, kind: "runner", size_pct: 0.5 }),
    ];
    const { valid, errors } = validateLegs(legs);
    expect(valid).toBe(false);
    expect(errors.some((e) => /runner/i.test(e))).toBe(true);
  });

  it("is invalid when no target leg exists", () => {
    const legs = [makeLeg({ id: "a", position: 1, kind: "runner", size_pct: 1.0 })];
    const { valid, errors } = validateLegs(legs);
    expect(valid).toBe(false);
    expect(errors.some((e) => /target/i.test(e))).toBe(true);
  });

  it("is invalid with non-contiguous positions", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, size_pct: 0.5 }),
      makeLeg({ id: "b", position: 3, size_pct: 0.5 }), // skips position 2
    ];
    const { valid, errors } = validateLegs(legs);
    expect(valid).toBe(false);
    expect(errors.some((e) => /contiguous/i.test(e))).toBe(true);
  });

  it("is valid for a single 100% target leg", () => {
    const legs = [makeLeg({ id: "a", position: 1, kind: "target", size_pct: 1.0 })];
    const { valid } = validateLegs(legs);
    expect(valid).toBe(true);
  });

  it("is valid for target + runner summing to 1.0", () => {
    const legs = [
      makeLeg({ id: "a", position: 1, kind: "target", size_pct: 0.7 }),
      makeLeg({ id: "b", position: 2, kind: "runner", size_pct: 0.3 }),
    ];
    const { valid } = validateLegs(legs);
    expect(valid).toBe(true);
  });
});

// ----------------------------------------------------------------------------
// validateStops
// ----------------------------------------------------------------------------

describe("validateStops", () => {
  it("is invalid with empty stops", () => {
    const { valid, errors } = validateStops([]);
    expect(valid).toBe(false);
    expect(errors.some((e) => /at least one stop/i.test(e))).toBe(true);
  });

  it("is invalid when simple stop missing simple_type", () => {
    const stop: StopDraft = {
      id: "s1",
      mode: "simple",
      scope: "all",
      simple_type: null,
      simple_value: 1.0,
    };
    const { valid, errors } = validateStops([stop]);
    expect(valid).toBe(false);
    expect(errors.some((e) => /simple_type/i.test(e))).toBe(true);
  });

  it("is invalid when simple stop missing simple_value", () => {
    const stop: StopDraft = {
      id: "s1",
      mode: "simple",
      scope: "all",
      simple_type: "%",
      simple_value: null,
    };
    const { valid, errors } = validateStops([stop]);
    expect(valid).toBe(false);
    expect(errors.some((e) => /simple_value/i.test(e))).toBe(true);
  });

  it("is invalid when expression stop missing expression_text", () => {
    const stop: StopDraft = {
      id: "s1",
      mode: "expression",
      scope: "all",
      expression_text: "",
    };
    const { valid, errors } = validateStops([stop]);
    expect(valid).toBe(false);
    expect(errors.some((e) => /expression_text/i.test(e))).toBe(true);
  });

  it("is valid for a simple % stop", () => {
    const stop: StopDraft = {
      id: "s1",
      mode: "simple",
      scope: "all",
      simple_type: "%",
      simple_value: 1.0,
    };
    const { valid } = validateStops([stop]);
    expect(valid).toBe(true);
  });

  it("is valid for an expression stop with text", () => {
    const stop: StopDraft = {
      id: "s1",
      mode: "expression",
      scope: "all",
      expression_text: "5m.atr(14)",
    };
    const { valid } = validateStops([stop]);
    expect(valid).toBe(true);
  });
});

import { describe, expect, it } from "vitest";
import {
  asGroup,
  compactGroup,
  emptyCondition,
  emptyLogicalExitRule,
  logicalExitToPayload,
  normalizeCondition,
  summarizeLogicalExit,
} from "./conditionUtils";
import type { LogicalExitRule } from "@/api/schemas/strategyComposer";

describe("asGroup / compactGroup", () => {
  it("wraps a bare condition into a single-child all group", () => {
    const c = emptyCondition();
    const g = asGroup(c);
    expect(g.kind).toBe("group");
    expect(g.operator).toBe("all");
    expect(g.children.length).toBe(1);
    expect(g.children[0]).toBe(c);
  });

  it("compactGroup collapses single-child groups back to the leaf", () => {
    const c = emptyCondition();
    const g = asGroup(c);
    expect(compactGroup(g)).toBe(c);
  });
});

describe("normalizeCondition", () => {
  it("falls back to empty condition for unknown shapes", () => {
    const out = normalizeCondition({ kind: "??" });
    expect(out.kind).toBe("condition");
  });

  it("preserves group operator and recursively normalizes children", () => {
    const out = normalizeCondition({
      kind: "group",
      operator: "any",
      children: [
        { kind: "condition", left_feature: "5m.close[0]", operator: "lt", right_value: 100 },
        { kind: "group", operator: "all", children: [] },
      ],
    });
    expect(out.kind).toBe("group");
    if (out.kind !== "group") return;
    expect(out.operator).toBe("any");
    expect(out.children.length).toBe(2);
  });

  it("clamps unknown operators to gt", () => {
    const out = normalizeCondition({
      kind: "condition",
      left_feature: "x",
      operator: "weird_op",
    });
    if (out.kind !== "condition") throw new Error("expected leaf");
    expect(out.operator).toBe("gt");
  });
});

describe("LogicalExitRule helpers — all seven kinds", () => {
  const KINDS: LogicalExitRule["kind"][] = [
    "feature_condition",
    "bars_since_entry",
    "time_in_position_seconds",
    "time_of_day_et",
    "minutes_before_session_close",
    "session_window",
    "hybrid",
  ];

  it("emptyLogicalExitRule produces a defaulted payload for every kind", () => {
    for (const k of KINDS) {
      const r = emptyLogicalExitRule(k);
      expect(r.kind).toBe(k);
      // Each kind has at least one of its parameter fields populated.
      const summary = summarizeLogicalExit(r);
      expect(typeof summary).toBe("string");
      expect(summary.length).toBeGreaterThan(2);
    }
  });

  it("logicalExitToPayload normalizes numeric fields and strips editor extras", () => {
    const bars = logicalExitToPayload({
      kind: "bars_since_entry",
      bars: 7,
      // editor-only padding that should be stripped
      label: "ignored by the wire",
    } as unknown as LogicalExitRule);
    expect(bars).toEqual({ kind: "bars_since_entry", bars: 7 });

    const time = logicalExitToPayload({
      kind: "time_of_day_et",
      hour: 15,
      minute: 55,
    } as LogicalExitRule);
    expect(time).toEqual({ kind: "time_of_day_et", hour: 15, minute: 55 });
  });

  it("logicalExitToPayload recurses into hybrid children + drops nulls", () => {
    const out = logicalExitToPayload({
      kind: "hybrid",
      operator: "any",
      children: [
        { kind: "bars_since_entry", bars: 3 } as LogicalExitRule,
        { kind: "minutes_before_session_close", minutes_before_close: 5 } as LogicalExitRule,
      ],
    } as LogicalExitRule);
    expect(out).toEqual({
      kind: "hybrid",
      operator: "any",
      children: [
        { kind: "bars_since_entry", bars: 3 },
        { kind: "minutes_before_session_close", minutes_before_close: 5 },
      ],
    });
  });

  it("logicalExitToPayload returns null for nullish input", () => {
    expect(logicalExitToPayload(null)).toBeNull();
    expect(logicalExitToPayload(undefined)).toBeNull();
  });
});

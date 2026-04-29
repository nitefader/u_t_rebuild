/**
 * Pure helpers for editing condition trees and LogicalExitRule trees in
 * the Strategy Builder UI. Keeping these pure (no React, no API) lets
 * the unit-test surface stay small.
 */

import type {
  LogicalExitRule,
  LogicalExitRuleKind,
} from "@/api/schemas/strategyComposer";

export type ConditionOperator =
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "eq"
  | "cross_above"
  | "cross_below";

export const CONDITION_OPERATORS: { value: ConditionOperator; label: string }[] = [
  { value: "gt", label: ">" },
  { value: "gte", label: "≥" },
  { value: "lt", label: "<" },
  { value: "lte", label: "≤" },
  { value: "eq", label: "=" },
  { value: "cross_above", label: "crosses above" },
  { value: "cross_below", label: "crosses below" },
];

export interface ConditionNode {
  kind: "condition";
  left_feature: string;
  operator: ConditionOperator;
  right_feature?: string | null;
  right_value?: number | string | null;
  label?: string | null;
}

export interface ConditionGroup {
  kind: "group";
  operator: "all" | "any" | "and" | "or";
  children: ConditionExpression[];
  label?: string | null;
}

export type ConditionExpression = ConditionNode | ConditionGroup;

export function emptyCondition(): ConditionNode {
  return { kind: "condition", left_feature: "", operator: "gt", right_feature: "", right_value: null };
}

export function emptyGroup(operator: "all" | "any" = "all"): ConditionGroup {
  return { kind: "group", operator, children: [emptyCondition()] };
}

/** Wrap a single condition into an `all` group so the editor can always render rows. */
export function asGroup(expr: ConditionExpression | null | undefined): ConditionGroup {
  if (!expr) return emptyGroup();
  if (expr.kind === "group") return expr;
  return { kind: "group", operator: "all", children: [expr] };
}

/** Unwrap a single-child group back to its child for compact serialization. */
export function compactGroup(group: ConditionGroup): ConditionExpression {
  if (group.children.length === 1) return group.children[0]!;
  return group;
}

/** Replace child at path. Path is a list of indices into nested groups. */
export function replaceAt(
  root: ConditionGroup,
  path: number[],
  next: ConditionExpression,
): ConditionGroup {
  if (path.length === 0) {
    if (next.kind === "group") return next;
    return { ...root, children: [next] };
  }
  const [head, ...rest] = path;
  const children = root.children.slice();
  const target = children[head];
  if (!target) return root;
  if (rest.length === 0) {
    children[head] = next;
  } else {
    if (target.kind !== "group") return root;
    children[head] = replaceAt(target, rest, next);
  }
  return { ...root, children };
}

export function removeAt(root: ConditionGroup, path: number[]): ConditionGroup {
  if (path.length === 0) return root;
  if (path.length === 1) {
    const next = root.children.slice();
    next.splice(path[0]!, 1);
    if (next.length === 0) next.push(emptyCondition());
    return { ...root, children: next };
  }
  const [head, ...rest] = path;
  const target = root.children[head];
  if (!target || target.kind !== "group") return root;
  const children = root.children.slice();
  children[head] = removeAt(target, rest);
  return { ...root, children };
}

export function appendChild(
  root: ConditionGroup,
  path: number[],
  child: ConditionExpression,
): ConditionGroup {
  if (path.length === 0) {
    return { ...root, children: [...root.children, child] };
  }
  const [head, ...rest] = path;
  const target = root.children[head];
  if (!target || target.kind !== "group") return root;
  const children = root.children.slice();
  children[head] = appendChild(target, rest, child);
  return { ...root, children };
}

/**
 * Normalize an unknown condition expression coming back from the backend
 * (which uses .passthrough() on the full schema) into our editor shape.
 * Rejects only obvious shape mismatches; unknown operators fall back to "gt".
 */
export function normalizeCondition(expr: unknown): ConditionExpression {
  if (!expr || typeof expr !== "object") return emptyCondition();
  const obj = expr as Record<string, unknown>;
  if (obj.kind === "group") {
    const op = (obj.operator as string | undefined) ?? "all";
    const children = Array.isArray(obj.children) ? obj.children.map(normalizeCondition) : [emptyCondition()];
    return {
      kind: "group",
      operator: (op === "any" || op === "or" ? "any" : "all") as "all" | "any",
      children,
      label: typeof obj.label === "string" ? obj.label : null,
    };
  }
  // condition
  const operator = ((obj.operator as string | undefined) ?? "gt") as ConditionOperator;
  return {
    kind: "condition",
    left_feature: typeof obj.left_feature === "string" ? obj.left_feature : "",
    operator: CONDITION_OPERATORS.some((o) => o.value === operator) ? operator : "gt",
    right_feature: typeof obj.right_feature === "string" ? obj.right_feature : null,
    right_value:
      typeof obj.right_value === "number" || typeof obj.right_value === "string"
        ? obj.right_value
        : null,
    label: typeof obj.label === "string" ? obj.label : null,
  };
}

// ---------- LogicalExitRule helpers ------------------------------------------

export const LOGICAL_EXIT_KIND_LABELS: Record<LogicalExitRuleKind, string> = {
  feature_condition: "Feature condition",
  bars_since_entry: "Bars since entry",
  time_in_position_seconds: "Time in position (seconds)",
  time_of_day_et: "Time of day (ET)",
  minutes_before_session_close: "Minutes before session close",
  session_window: "Session window",
  hybrid: "Hybrid (combine rules)",
};

export const LOGICAL_EXIT_KIND_SHORT: Record<LogicalExitRuleKind, string> = {
  feature_condition: "Feature",
  bars_since_entry: "Bars",
  time_in_position_seconds: "Seconds",
  time_of_day_et: "Time of day",
  minutes_before_session_close: "Before close",
  session_window: "Session",
  hybrid: "Hybrid",
};

export const SESSION_WINDOW_OPTIONS = [
  { value: "premarket", label: "Premarket" },
  { value: "regular", label: "Regular session" },
  { value: "afterhours", label: "After hours" },
  { value: "opening_auction", label: "Opening auction window" },
  { value: "closing_auction", label: "Closing auction window" },
];

export function emptyLogicalExitRule(kind: LogicalExitRuleKind = "bars_since_entry"): LogicalExitRule {
  switch (kind) {
    case "feature_condition":
      return { kind, feature_condition: emptyCondition() } as LogicalExitRule;
    case "bars_since_entry":
      return { kind, bars: 5 } as LogicalExitRule;
    case "time_in_position_seconds":
      return { kind, seconds: 1800 } as LogicalExitRule;
    case "time_of_day_et":
      return { kind, hour: 15, minute: 55 } as LogicalExitRule;
    case "minutes_before_session_close":
      return { kind, minutes_before_close: 5 } as LogicalExitRule;
    case "session_window":
      return { kind, session: "regular" } as LogicalExitRule;
    case "hybrid":
      return {
        kind,
        operator: "all",
        children: [emptyLogicalExitRule("bars_since_entry"), emptyLogicalExitRule("feature_condition")],
      } as LogicalExitRule;
  }
}

export function summarizeLogicalExit(rule: LogicalExitRule | null | undefined): string {
  if (!rule) return "—";
  switch (rule.kind) {
    case "feature_condition":
      return "Exit when feature condition is true";
    case "bars_since_entry":
      return `Exit ${rule.bars ?? "?"} bar(s) after entry`;
    case "time_in_position_seconds": {
      const s = rule.seconds ?? 0;
      const mins = Math.floor(s / 60);
      const secs = s % 60;
      return `Exit after ${mins}m${secs ? ` ${secs}s` : ""} in position`;
    }
    case "time_of_day_et":
      return `Exit at ${pad2(rule.hour ?? 0)}:${pad2(rule.minute ?? 0)} ET`;
    case "minutes_before_session_close":
      return `Exit ${rule.minutes_before_close ?? "?"} min before regular session close`;
    case "session_window":
      return `Exit during ${rule.session ?? "?"}`;
    case "hybrid": {
      const op = rule.operator === "any" ? "ANY" : "ALL";
      return `Hybrid (${op} of ${rule.children?.length ?? 0} rules)`;
    }
    default:
      return String(rule.kind);
  }
}

function pad2(n: number): string {
  return n.toString().padStart(2, "0");
}

/** Given the editor LogicalExitRule, return a backend-shaped payload. */
export function logicalExitToPayload(rule: LogicalExitRule | null | undefined): LogicalExitRule | null {
  if (!rule) return null;
  const kind = rule.kind;
  if (kind === "feature_condition") {
    return { kind, feature_condition: rule.feature_condition };
  }
  if (kind === "bars_since_entry") return { kind, bars: Number(rule.bars ?? 0) };
  if (kind === "time_in_position_seconds") return { kind, seconds: Number(rule.seconds ?? 0) };
  if (kind === "time_of_day_et")
    return { kind, hour: Number(rule.hour ?? 0), minute: Number(rule.minute ?? 0) };
  if (kind === "minutes_before_session_close")
    return { kind, minutes_before_close: Number(rule.minutes_before_close ?? 0) };
  if (kind === "session_window") return { kind, session: rule.session ?? "regular" };
  if (kind === "hybrid") {
    return {
      kind,
      operator: rule.operator === "any" ? "any" : "all",
      children: ((rule.children ?? []) as LogicalExitRule[])
        .map((c) => logicalExitToPayload(c))
        .filter((c): c is LogicalExitRule => c !== null),
    };
  }
  return rule;
}

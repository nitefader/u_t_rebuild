import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import { useState } from "react";
import type {
  FeatureCatalogItem,
  LogicalExitRule,
} from "@/api/schemas/strategyComposer";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { cn } from "@/lib/cn";
import { ConditionPillBuilder } from "./ConditionPillBuilder";
import { FeaturePicker } from "./FeaturePicker";
import { LogicalExitRulePicker } from "./LogicalExitRulePicker";
import {
  asGroup,
  emptyLogicalExitRule,
  summarizeLogicalExit,
  type ConditionExpression,
} from "./conditionUtils";

/**
 * SignalRuleEditor — editor for one entry- or exit-side rule.
 *
 * Shape mirrors the backend `SignalRule` (frontend type:
 * StrategyVersionPayload.entry_rules[i] / exit_rules[i]):
 *   { name, side, intent_type, condition?, logical_exit_rule? }
 *
 * Doctrine guards baked in:
 *   - Entry rules MUST have a feature condition. The LogicalExitRule
 *     picker is hidden for entries and validation upstream rejects
 *     entry rules carrying a logical_exit_rule.
 *   - Exit rules MAY have a feature condition AND/OR a logical_exit_rule.
 *     If both are present they AND together (the backend SignalEngine
 *     enforces this — UI mirrors). If a kind other than feature_condition
 *     is enough, the operator can clear the condition tree.
 *   - Side defaults to long; short is currently engine-blocked, so we
 *     surface an inline note when long isn't picked.
 */
export interface EditorRule {
  name: string;
  side: "long" | "short";
  intent_type: "entry" | "exit";
  condition?: ConditionExpression | null;
  logical_exit_rule?: LogicalExitRule | null;
  stop_candidate_feature?: string | null;
  target_candidate_feature?: string | null;
}

export interface SignalRuleEditorProps {
  rule: EditorRule;
  onChange: (next: EditorRule) => void;
  onDelete: () => void;
  catalog: FeatureCatalogItem[];
  invalidFeatureRefs?: Set<string>;
  consumer?: string;
  /** When true the rule appears collapsed by default. */
  defaultCollapsed?: boolean;
  index: number;
}

export function SignalRuleEditor(props: SignalRuleEditorProps): JSX.Element {
  const { rule, onChange, onDelete, catalog, invalidFeatureRefs, consumer, defaultCollapsed, index } = props;
  const [open, setOpen] = useState(!defaultCollapsed);
  const isExit = rule.intent_type === "exit";
  const hasLogicalExit = isExit && Boolean(rule.logical_exit_rule);
  const hasCondition = Boolean(rule.condition);

  function setName(v: string): void {
    onChange({ ...rule, name: v });
  }

  function setCondition(next: ConditionExpression | null): void {
    onChange({ ...rule, condition: next });
  }

  function clearCondition(): void {
    onChange({ ...rule, condition: null });
  }

  function setLogicalExitRule(next: LogicalExitRule | null): void {
    onChange({ ...rule, logical_exit_rule: next });
  }

  function attachLogicalExit(): void {
    onChange({ ...rule, logical_exit_rule: emptyLogicalExitRule("bars_since_entry") });
  }

  function ensureConditionForEntry(): void {
    if (!rule.condition) onChange({ ...rule, condition: asGroup(null) });
  }

  return (
    <div className="rounded border border-border bg-bg-raised">
      <div className="flex items-center gap-2 border-b border-border/60 px-3 py-2">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="text-fg-muted hover:text-fg"
          aria-label={open ? "Collapse rule" : "Expand rule"}
        >
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={rule.name}
              onChange={(e) => setName(e.target.value)}
              placeholder={isExit ? `exit_rule_${index + 1}` : `entry_rule_${index + 1}`}
              className="min-w-[12ch] flex-1 rounded border border-transparent bg-transparent px-1 py-0.5 text-sm font-semibold focus:border-accent focus:bg-bg-inset focus:outline-none"
            />
            <StatusBadge tone={isExit ? "warn" : "ok"}>{rule.intent_type}</StatusBadge>
            <StatusBadge tone="info">{rule.side}</StatusBadge>
            {isExit && hasLogicalExit ? (
              <StatusBadge tone="ai">logical_exit</StatusBadge>
            ) : null}
            {!hasCondition && !hasLogicalExit ? (
              <StatusBadge tone="danger">empty</StatusBadge>
            ) : null}
          </div>
          {!open ? (
            <div className="mt-0.5 truncate text-[11px] text-fg-muted">
              {hasLogicalExit ? summarizeLogicalExit(rule.logical_exit_rule) : null}
              {hasLogicalExit && hasCondition ? " · also AND condition" : null}
              {!hasLogicalExit && hasCondition ? "Feature condition" : null}
            </div>
          ) : null}
        </div>
        <select
          value={rule.side}
          onChange={(e) => onChange({ ...rule, side: e.target.value as "long" | "short" })}
          className="rounded border border-border bg-bg-inset px-1.5 py-0.5 text-[11px] focus:border-accent focus:outline-none"
        >
          <option value="long">long</option>
          <option value="short">short</option>
        </select>
        <button
          type="button"
          onClick={onDelete}
          className="rounded p-1 text-fg-subtle hover:bg-bg-subtle hover:text-danger"
          aria-label="Remove rule"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>

      {open ? (
        <div className="space-y-3 px-3 py-2.5">
          {rule.side === "short" ? (
            <div className="rounded border border-warn/40 bg-warn-subtle px-2 py-1 text-[11px] text-warn">
              Short side is engine-gated; backtest/runtime currently short-circuits non-LONG entries. Roadmap item.
            </div>
          ) : null}

          {/* Condition tree (always available; required for entries) */}
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
                Feature condition {isExit ? "(optional)" : "(required)"}
              </span>
              {hasCondition ? (
                isExit ? (
                  <button
                    type="button"
                    onClick={clearCondition}
                    className="text-[10px] text-fg-muted hover:text-danger"
                  >
                    clear
                  </button>
                ) : null
              ) : (
                <Button type="button" size="sm" variant="ghost" onClick={ensureConditionForEntry}>
                  Add condition tree
                </Button>
              )}
            </div>
            {hasCondition ? (
              <ConditionPillBuilder
                value={rule.condition!}
                onChange={setCondition}
                catalog={catalog}
                invalidFeatureRefs={invalidFeatureRefs}
                consumer={consumer}
              />
            ) : null}
          </div>

          {/* Logical exit picker — exits only */}
          {isExit ? (
            <div>
              <div className="mb-1 flex items-center gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
                  Logical exit rule
                </span>
                <span className="text-[10px] text-fg-subtle">
                  time / bars / session / hybrid all live under one of the seven logical_exit kinds
                </span>
                {!hasLogicalExit ? (
                  <Button type="button" size="sm" variant="ghost" onClick={attachLogicalExit}>
                    Attach logical exit
                  </Button>
                ) : null}
              </div>
              {hasLogicalExit ? (
                <LogicalExitRulePicker
                  value={rule.logical_exit_rule!}
                  onChange={setLogicalExitRule}
                  catalog={catalog}
                  invalidFeatureRefs={invalidFeatureRefs}
                  consumer={consumer}
                  removable
                />
              ) : null}
            </div>
          ) : null}

          {/* Stop / target candidate features (exit rules only) */}
          {isExit ? (
            <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wide text-fg-muted">
                  Stop candidate feature (optional)
                </div>
                <FeaturePicker
                  value={rule.stop_candidate_feature ?? ""}
                  onChange={(v) => onChange({ ...rule, stop_candidate_feature: v || null })}
                  catalog={catalog}
                  consumer={consumer ?? "backtest"}
                  placeholder="pick stop feature"
                />
              </div>
              <div>
                <div className="mb-1 text-[10px] uppercase tracking-wide text-fg-muted">
                  Target candidate feature (optional)
                </div>
                <FeaturePicker
                  value={rule.target_candidate_feature ?? ""}
                  onChange={(v) => onChange({ ...rule, target_candidate_feature: v || null })}
                  catalog={catalog}
                  consumer={consumer ?? "backtest"}
                  placeholder="pick target feature"
                />
              </div>
            </div>
          ) : null}

          {/* Doctrine warning if exit rule has zero content */}
          {isExit && !hasCondition && !hasLogicalExit ? (
            <div className={cn("rounded border border-danger/40 bg-danger-subtle px-2 py-1 text-[11px] text-danger")}>
              Exit rule has no condition and no logical_exit_rule. Add at least one or the rule will be rejected.
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

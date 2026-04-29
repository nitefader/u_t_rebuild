import { Plus, Trash2 } from "lucide-react";
import type {
  LogicalExitRule,
  LogicalExitRuleKind,
} from "@/api/schemas/strategyComposer";
import type { StrategyVersionPayload } from "@/api/schemas/strategies";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import {
  emptyLogicalExitRule,
  summarizeLogicalExit,
  SESSION_WINDOW_OPTIONS,
} from "../../conditionUtils";
import type { EditorRule } from "../../SignalRuleEditor";
import { bucketExitRules } from "../editorState";
import { SectionCard } from "./SectionCard";
import type { SectionSeverity } from "./SectionCard";

/**
 * TimeBasedExitSection (#10) — operator-facing UI for the four
 * time-flavor LogicalExitRule kinds:
 *   - bars_since_entry          ("after N bars")
 *   - time_in_position_seconds  ("after N minutes")
 *   - time_of_day_et            ("at HH:MM ET")
 *   - minutes_before_session_close ("N minutes before close")
 *   - session_window            ("during regular / premarket / etc.")
 *
 * Doctrine guard: the visual section is separate from Logical Exit
 * Plan because the operator thinks about clock-driven exits and rule-
 * driven exits separately. The underlying payload is still a single
 * `LogicalExitRule` per `feedback_logical_exit_is_the_only_exit_intent`
 * — there is no top-level `time_exit` intent.
 */
export interface TimeBasedExitSectionProps {
  strategy: StrategyVersionPayload;
  onChange: (next: StrategyVersionPayload) => void;
  warnings?: CoherenceWarning[];
}

const TIME_KIND_OPTIONS: { value: LogicalExitRuleKind; label: string }[] = [
  { value: "bars_since_entry", label: "After N bars" },
  { value: "time_in_position_seconds", label: "After N minutes" },
  { value: "time_of_day_et", label: "At HH:MM ET" },
  { value: "minutes_before_session_close", label: "N minutes before close" },
  { value: "session_window", label: "During session" },
];

export function TimeBasedExitSection(props: TimeBasedExitSectionProps): JSX.Element {
  const { strategy, onChange, warnings } = props;

  const sectionSeverity: SectionSeverity = warnings && warnings.some((w) => w.severity === "error")
    ? "error"
    : warnings && warnings.some((w) => w.severity === "warn" && !w.dismissed)
    ? "warn"
    : "ok";
  const rules = strategy.exit_rules as EditorRule[];
  const buckets = bucketExitRules(rules);
  const visible = buckets.timeBased;

  function setRule(at: number, next: EditorRule): void {
    const nextRules = rules.slice();
    nextRules[at] = next;
    onChange({ ...strategy, exit_rules: nextRules as StrategyVersionPayload["exit_rules"] });
  }
  function removeRule(at: number): void {
    onChange({
      ...strategy,
      exit_rules: rules.filter((_, i) => i !== at) as StrategyVersionPayload["exit_rules"],
    });
  }
  function addRule(): void {
    const next: EditorRule = {
      name: `time_exit_${rules.length + 1}`,
      side: "long",
      intent_type: "exit",
      condition: null,
      logical_exit_rule: emptyLogicalExitRule("bars_since_entry"),
    };
    onChange({
      ...strategy,
      exit_rules: [...rules, next] as StrategyVersionPayload["exit_rules"],
    });
  }

  return (
    <SectionCard
      id="section-time-based-exit"
      number={10}
      title="Time-based exit plan"
      severity={sectionSeverity}
      subtitle="Bars / minutes / time-of-day / minutes-before-close exits. All serialize to logical_exit per spine doctrine."
      trailing={
        <div className="flex items-center gap-2">
          <StatusBadge tone="neutral">{visible.length}</StatusBadge>
          <Button
            type="button"
            size="sm"
            variant="secondary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={addRule}
            data-testid="add-time-exit"
          >
            Add time exit
          </Button>
        </div>
      }
    >
      {warnings && warnings.length > 0 ? (
        <div className="mb-2 space-y-1">
          {warnings.filter((w) => !w.dismissed || w.severity === "error").map((w) => (
            <div key={w.id} className={cn("rounded px-2 py-1 text-[11px]", w.severity === "error" ? "text-danger bg-danger-subtle/30" : "text-warn bg-warn-subtle/30")}>
              {w.message}
            </div>
          ))}
        </div>
      ) : null}
      {visible.length === 0 ? (
        <div className="rounded border border-dashed border-border px-3 py-4 text-center text-[11px] text-fg-muted">
          No time-based exits. Intraday strategies typically need at least one (e.g. flat by 15:55 ET).
        </div>
      ) : (
        <div className="space-y-2">
          {visible.map(({ rule, index }) => (
            <TimeExitRow
              key={index}
              rule={rule}
              onChange={(next) => setRule(index, next)}
              onDelete={() => removeRule(index)}
            />
          ))}
        </div>
      )}
    </SectionCard>
  );
}

interface TimeExitRowProps {
  rule: EditorRule;
  onChange: (next: EditorRule) => void;
  onDelete: () => void;
}

function TimeExitRow(props: TimeExitRowProps): JSX.Element {
  const { rule, onChange, onDelete } = props;
  const exit = (rule.logical_exit_rule ?? emptyLogicalExitRule("bars_since_entry")) as LogicalExitRule;

  function setKind(kind: LogicalExitRuleKind): void {
    onChange({ ...rule, logical_exit_rule: emptyLogicalExitRule(kind) });
  }
  function patch(next: Partial<LogicalExitRule>): void {
    onChange({ ...rule, logical_exit_rule: { ...exit, ...next } as LogicalExitRule });
  }

  return (
    <div className="rounded border border-border bg-bg-raised">
      <div className="flex items-center gap-2 border-b border-border/60 px-3 py-2">
        <input
          type="text"
          value={rule.name}
          onChange={(e) => onChange({ ...rule, name: e.target.value })}
          placeholder="time_exit"
          className="min-w-[12ch] flex-1 rounded border border-transparent bg-transparent px-1 py-0.5 text-sm font-semibold focus:border-accent focus:bg-bg-inset focus:outline-none"
        />
        <StatusBadge tone="warn">exit</StatusBadge>
        <StatusBadge tone="info">{rule.side}</StatusBadge>
        <button
          type="button"
          onClick={onDelete}
          className="rounded p-1 text-fg-subtle hover:bg-bg-subtle hover:text-danger"
          aria-label="Remove rule"
        >
          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      </div>
      <div className="space-y-2 px-3 py-2.5">
        <div className="flex flex-wrap gap-1.5">
          {TIME_KIND_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setKind(opt.value)}
              className={cn(
                "rounded border px-2 py-0.5 text-[11px]",
                exit.kind === opt.value
                  ? "border-accent bg-accent/20 text-accent"
                  : "border-border bg-bg-inset text-fg-muted hover:text-fg",
              )}
              data-testid={`time-exit-kind-${opt.value}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <KindBody exit={exit} onPatch={patch} />
        <div className="text-[11px] text-fg-muted">{summarizeLogicalExit(exit)}</div>
      </div>
    </div>
  );
}

function KindBody({
  exit,
  onPatch,
}: {
  exit: LogicalExitRule;
  onPatch: (next: Partial<LogicalExitRule>) => void;
}): JSX.Element {
  if (exit.kind === "bars_since_entry") {
    return (
      <NumericRow
        label="Bars after entry"
        value={exit.bars}
        suffix="bars"
        min={1}
        onChange={(n) => onPatch({ bars: n })}
        testId="bars-after-entry"
      />
    );
  }
  if (exit.kind === "time_in_position_seconds") {
    const minutes = (exit.seconds ?? 0) / 60;
    return (
      <NumericRow
        label="Minutes after entry"
        value={Number.isFinite(minutes) ? minutes : 0}
        suffix="minutes"
        min={1}
        onChange={(n) => onPatch({ seconds: Math.max(0, Math.round(n * 60)) })}
        testId="minutes-after-entry"
      />
    );
  }
  if (exit.kind === "time_of_day_et") {
    return (
      <div className="flex items-center gap-2">
        <label className="text-[10px] uppercase tracking-wide text-fg-muted">Exit at (ET)</label>
        <input
          type="number"
          min={0}
          max={23}
          value={exit.hour ?? 0}
          onChange={(e) => onPatch({ hour: clampInt(e.target.value, 0, 23) })}
          className="w-14 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-xs focus:border-accent focus:outline-none"
          data-testid="exit-hour"
        />
        <span className="text-fg-muted">:</span>
        <input
          type="number"
          min={0}
          max={59}
          value={exit.minute ?? 0}
          onChange={(e) => onPatch({ minute: clampInt(e.target.value, 0, 59) })}
          className="w-14 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-xs focus:border-accent focus:outline-none"
          data-testid="exit-minute"
        />
        <span className="text-[11px] text-fg-subtle">America/New_York</span>
      </div>
    );
  }
  if (exit.kind === "minutes_before_session_close") {
    return (
      <NumericRow
        label="Before close"
        value={exit.minutes_before_close}
        suffix="min before close"
        min={1}
        onChange={(n) => onPatch({ minutes_before_close: n })}
        testId="minutes-before-close"
      />
    );
  }
  if (exit.kind === "session_window") {
    return (
      <div className="flex items-center gap-2">
        <label className="text-[10px] uppercase tracking-wide text-fg-muted">Exit during</label>
        <select
          value={exit.session ?? "regular"}
          onChange={(e) => onPatch({ session: e.target.value })}
          className="rounded border border-border bg-bg-inset px-1.5 py-0.5 text-xs focus:border-accent focus:outline-none"
          data-testid="exit-session"
        >
          {SESSION_WINDOW_OPTIONS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
    );
  }
  return <div className="text-[11px] text-fg-muted">Unsupported time-exit kind {String(exit.kind)}.</div>;
}

function NumericRow({
  label,
  value,
  suffix,
  min,
  onChange,
  testId,
}: {
  label: string;
  value: number | null | undefined;
  suffix: string;
  min?: number;
  onChange: (n: number) => void;
  testId: string;
}): JSX.Element {
  return (
    <div className="flex items-center gap-2">
      <label className="text-[10px] uppercase tracking-wide text-fg-muted">{label}</label>
      <input
        type="number"
        min={min}
        value={value ?? 0}
        onChange={(e) => {
          const n = Number(e.target.value);
          onChange(Number.isFinite(n) ? n : 0);
        }}
        className="w-20 rounded border border-border bg-bg-inset px-1.5 py-0.5 font-mono text-xs focus:border-accent focus:outline-none"
        data-testid={testId}
      />
      <span className="text-[11px] text-fg-subtle">{suffix}</span>
    </div>
  );
}

function clampInt(raw: string, min: number, max: number): number {
  const n = Math.round(Number(raw));
  if (!Number.isFinite(n)) return min;
  return Math.max(min, Math.min(max, n));
}

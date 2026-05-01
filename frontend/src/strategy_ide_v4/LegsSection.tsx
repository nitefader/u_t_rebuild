/**
 * LegsSection — trade legs with size-summary bar, add/remove, and auto-balance.
 */

import type { CSSProperties } from "react";
import type { StrategyLegV4Draft, OnFillActionV4Draft } from "@/api/schemas/strategiesV4";
import { LegRow } from "./LegRow";
import { autoBalance, redistributeOnRemove, appendLegEvenly, validateLegs } from "./legAutoBalance";

const SUM_TOLERANCE = 1e-6;

/**
 * Leg-summary segment colours rotate through semantic theme tokens (--ut-* RGB triplets).
 */
const BAR_TOKEN_VARS = [
  "--ut-accent",
  "--ut-ok",
  "--ut-ai",
  "--ut-warn",
  "--ut-info",
  "--ut-danger",
  "--ut-fg-muted",
] as const;

function barFillStyle(index: number): CSSProperties {
  const v = BAR_TOKEN_VARS[index % BAR_TOKEN_VARS.length];
  return { backgroundColor: `rgb(var(${v}) / 0.75)` };
}

function barLabelColor(index: number): string {
  const v = BAR_TOKEN_VARS[index % BAR_TOKEN_VARS.length];
  return `rgb(var(${v}))`;
}

function newLegId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function defaultOnFill(): OnFillActionV4Draft {
  return { kind: "be_exact" };
}

export interface LegsSectionProps {
  legs: StrategyLegV4Draft[];
  onChange: (legs: StrategyLegV4Draft[]) => void;
}

export function LegsSection({ legs, onChange }: LegsSectionProps): JSX.Element {
  const { errors } = validateLegs(legs);
  const total = legs.reduce((acc, l) => acc + l.size_pct, 0);
  const isBalanced = Math.abs(total - 1.0) <= SUM_TOLERANCE;
  const hasRunner = legs.some((l) => l.kind === "runner");

  function handleAddTarget(): void {
    const base = {
      id: newLegId(),
      kind: "target" as const,
      target_type: "%" as const,
      target_value: 1.0,
      on_fill_action: defaultOnFill(),
    };
    onChange(appendLegEvenly(legs, base));
  }

  function handleAddRunner(): void {
    if (hasRunner) return;
    const base = {
      id: newLegId(),
      kind: "runner" as const,
      target_type: "%" as const,
      target_value: 1.0,
      on_fill_action: defaultOnFill(),
    };
    onChange(appendLegEvenly(legs, base));
  }

  function handleAutoBalance(): void {
    onChange(autoBalance(legs));
  }

  function handleChange(index: number, updated: StrategyLegV4Draft): void {
    const next = legs.map((l, i) => (i === index ? updated : l));
    onChange(next);
  }

  function handleRemove(index: number): void {
    onChange(redistributeOnRemove(legs, index));
  }

  return (
    <section className="flex flex-col gap-3" aria-label="Trade legs">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-fg">Trade legs</h3>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={handleAutoBalance}
            className="text-xs px-2 py-1 rounded border border-border-strong text-fg-muted hover:text-accent hover:border-accent transition-colors"
          >
            Auto-balance
          </button>
          <button
            type="button"
            onClick={handleAddTarget}
            className="text-xs px-2 py-1 rounded border border-border-strong text-fg-muted hover:text-accent hover:border-accent transition-colors"
          >
            + Add target
          </button>
          <button
            type="button"
            onClick={handleAddRunner}
            disabled={hasRunner}
            className="text-xs px-2 py-1 rounded border border-border-strong text-fg-muted hover:text-ai hover:border-ai transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
          >
            + Add runner
          </button>
        </div>
      </div>

      {/* Size-summary bar */}
      <SizeSummaryBar legs={legs} total={total} isBalanced={isBalanced} />

      {errors.length > 0 ? (
        <ul className="rounded border border-danger/40 bg-danger-subtle px-3 py-2 text-xs text-danger list-disc list-inside">
          {errors.map((err) => (
            <li key={err}>{err}</li>
          ))}
        </ul>
      ) : null}

      {legs.map((leg, i) => (
        <LegRow
          key={leg.id}
          leg={leg}
          index={i}
          totalLegs={legs.length}
          onChange={(updated) => handleChange(i, updated)}
          onRemove={() => handleRemove(i)}
        />
      ))}
    </section>
  );
}

interface SizeSummaryBarProps {
  legs: StrategyLegV4Draft[];
  total: number;
  isBalanced: boolean;
}

function SizeSummaryBar({ legs, total, isBalanced }: SizeSummaryBarProps): JSX.Element {
  // Segment fills use semantic theme RGB tokens via barFillStyle / barLabelColor.
  return (
    <div aria-label="Size summary bar" className="flex flex-col gap-1">
      <div className="relative h-5 w-full overflow-hidden rounded bg-bg-inset border border-border">
        {legs.map((leg, i) => {
          const widthPct = Math.min(leg.size_pct * 100, 100);
          const leftPct = legs
            .slice(0, i)
            .reduce((acc, l) => acc + Math.min(l.size_pct * 100, 100), 0);
          return (
            <div
              key={leg.id}
              title={`Leg ${leg.position} — ${(leg.size_pct * 100).toFixed(2)}%`}
              style={{
                position: "absolute",
                left: `${leftPct}%`,
                width: `${widthPct}%`,
                height: "100%",
                ...barFillStyle(i),
              }}
            />
          );
        })}
        {/* 100% marker line */}
        <div
          className="bg-fg/30"
          style={{
            position: "absolute",
            left: "100%",
            top: 0,
            bottom: 0,
            width: 2,
          }}
        />
        {/* Over/under-fill indicator */}
        {!isBalanced ? (
          <div
            aria-label={total > 1.0 ? "Over-fill" : "Under-fill"}
            className="bg-danger"
            style={{
              position: "absolute",
              right: 4,
              top: 2,
              bottom: 2,
              width: 6,
              borderRadius: 2,
            }}
          />
        ) : null}
      </div>
      <div className="flex items-center gap-2 text-[10px] text-fg-subtle">
        {legs.map((leg, i) => (
          <span key={leg.id} style={{ color: barLabelColor(i) }}>
            L{leg.position}: {(leg.size_pct * 100).toFixed(1)}%
          </span>
        ))}
        <span className={isBalanced ? "ml-auto text-ok" : "ml-auto text-danger"}>
          Total: {(total * 100).toFixed(2)}%
        </span>
      </div>
    </div>
  );
}

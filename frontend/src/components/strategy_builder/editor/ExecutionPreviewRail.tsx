import { useMemo } from "react";
import type {
  BracketRunnerOverrides,
  BracketStopTargetOverrides,
  ExecutionStylePresetValue,
  MultiTargetScaleOutOverrides,
} from "../ExecutionStylePresetRow";
import { cn } from "@/lib/cn";

/**
 * ExecutionPreviewRail — schematic of the active execution preset's
 * entry / stop / target plan, drawn as horizontal price levels around
 * a 100% entry baseline.
 *
 * The rail is informational; it derives every level from the preset
 * overrides already validated by ExecutionStylePresetRow.validatePreset.
 * Direction is assumed long for visual orientation (stop below, target
 * above) — short trades mirror in operator's mental model. The rail
 * does not render for presets without a stop/target leg.
 *
 * Each line is annotated with its percent distance from entry so the
 * operator can verify the values match their intent at a glance.
 */

export interface ExecutionPreviewRailProps {
  preset: ExecutionStylePresetValue;
}

interface PriceLevel {
  id: string;
  label: string;
  pct: number; // signed % from entry (target positive, stop negative)
  kind: "entry" | "stop" | "target" | "runner";
  detail?: string;
}

export function ExecutionPreviewRail(props: ExecutionPreviewRailProps): JSX.Element | null {
  const { preset } = props;
  const levels = useMemo(() => computeLevels(preset), [preset]);
  if (!levels) return null;

  // Vertical scale: stretch to fit the largest absolute pct so the chart
  // never collapses when values are small. Entry is always at the centre.
  const span = Math.max(
    1,
    ...levels.map((l) => Math.abs(l.pct)),
  );
  const HEIGHT = 140;
  const PADDING_Y = 18;
  const usableHeight = HEIGHT - 2 * PADDING_Y;
  const entryY = HEIGHT / 2;

  function yFor(pct: number): number {
    // Targets are positive (above entry, smaller y); stops negative (below).
    const ratio = pct / span; // -1..1
    return entryY - ratio * (usableHeight / 2);
  }

  return (
    <section
      className="rounded border border-border bg-bg-subtle px-3 py-2"
      data-testid="execution-preview-rail"
      aria-label="Execution preset preview"
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[10.5px] font-semibold uppercase tracking-wide text-fg-muted">
          Execution preview
        </span>
        <span className="text-[10.5px] text-fg-muted">{kindLabel(preset.kind)}</span>
      </div>
      <div className="flex gap-3">
        <svg
          viewBox={`0 0 240 ${HEIGHT}`}
          width="240"
          height={HEIGHT}
          className="shrink-0"
          role="img"
          aria-label="Entry / stop / target levels relative to entry price"
        >
          {/* axis */}
          <line
            x1="20"
            x2="220"
            y1={entryY}
            y2={entryY}
            className="stroke-border"
            strokeWidth="1"
            strokeDasharray="2 3"
          />
          {levels.map((level) => {
            const y = yFor(level.pct);
            const stroke = strokeFor(level.kind);
            return (
              <g
                key={level.id}
                data-testid={`exec-preview-level-${level.id}`}
                data-kind={level.kind}
                data-pct={level.pct.toFixed(2)}
              >
                <line x1="20" x2="200" y1={y} y2={y} className={stroke} strokeWidth="1.5" />
                <circle cx="200" cy={y} r="2.5" className={fillFor(level.kind)} />
                <text
                  x="206"
                  y={y + 3}
                  className="fill-fg text-[9px]"
                  fontFamily="ui-monospace, monospace"
                >
                  {formatPct(level.pct)}
                </text>
              </g>
            );
          })}
          <text
            x="20"
            y={entryY - 4}
            className="fill-fg-muted text-[9px]"
            fontFamily="ui-monospace, monospace"
          >
            entry
          </text>
        </svg>
        <ul
          className="flex flex-col justify-center gap-1 text-[11px]"
          data-testid="execution-preview-legend"
        >
          {levels.map((level) => (
            <li key={level.id} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className={cn("inline-block h-2 w-2 rounded-full", legendDotFor(level.kind))}
              />
              <span className="font-medium text-fg">{level.label}</span>
              <span className="font-mono text-fg-muted">{formatPct(level.pct)}</span>
              {level.detail ? (
                <span className="text-fg-muted">· {level.detail}</span>
              ) : null}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// derivation
// ---------------------------------------------------------------------------

export function computeLevels(preset: ExecutionStylePresetValue): PriceLevel[] | null {
  const entry: PriceLevel = { id: "entry", label: "Entry", pct: 0, kind: "entry" };

  if (preset.kind === "market_entry_market_exit" || preset.kind === "stop_entry_market_exit") {
    return null;
  }

  if (preset.kind === "bracket_stop_target") {
    const o = preset.overrides as BracketStopTargetOverrides;
    return [
      { id: "target", label: "Target", pct: o.target_pct, kind: "target" },
      entry,
      { id: "stop", label: "Stop", pct: -o.stop_pct, kind: "stop" },
    ];
  }

  if (preset.kind === "bracket_runner") {
    const o = preset.overrides as BracketRunnerOverrides;
    const slicePct = Math.round(o.first_slice_pct * 100);
    return [
      { id: "runner", label: "Runner", pct: o.first_target_pct + o.trail_pct, kind: "runner", detail: `trail ${o.trail_pct}%` },
      { id: "target-1", label: "First target", pct: o.first_target_pct, kind: "target", detail: `${slicePct}% slice` },
      entry,
      { id: "stop", label: "Trailing stop", pct: -o.trail_pct, kind: "stop" },
    ];
  }

  if (preset.kind === "multi_target_scale_out") {
    const o = preset.overrides as MultiTargetScaleOutOverrides;
    const tiers = o.targets.map((tier, i) => {
      const slicePct = Math.round(tier.slice_pct * 100);
      return {
        id: `target-${i + 1}`,
        label: `Target ${i + 1}`,
        pct: tier.target_pct,
        kind: "target" as const,
        detail: `${slicePct}% slice`,
      };
    });
    const stopLevel: PriceLevel | null =
      o.stop_pct !== null && o.stop_pct !== undefined && o.stop_pct > 0
        ? { id: "stop", label: "Stop", pct: -o.stop_pct, kind: "stop" }
        : null;
    return [
      ...tiers.slice().reverse(),
      entry,
      ...(stopLevel ? [stopLevel] : []),
    ];
  }

  return null;
}

function kindLabel(kind: ExecutionStylePresetValue["kind"]): string {
  switch (kind) {
    case "market_entry_market_exit":
      return "Market in / market out";
    case "stop_entry_market_exit":
      return "Stop entry / market exit";
    case "bracket_stop_target":
      return "Bracket: stop + target";
    case "bracket_runner":
      return "Bracket + runner";
    case "multi_target_scale_out":
      return "Multi-target scale-out";
  }
}

function formatPct(pct: number): string {
  if (pct === 0) return "0.00%";
  const sign = pct > 0 ? "+" : "−";
  return `${sign}${Math.abs(pct).toFixed(2)}%`;
}

function strokeFor(kind: PriceLevel["kind"]): string {
  switch (kind) {
    case "entry":
      return "stroke-fg-muted";
    case "stop":
      return "stroke-danger";
    case "target":
      return "stroke-ok";
    case "runner":
      return "stroke-accent";
  }
}

function fillFor(kind: PriceLevel["kind"]): string {
  switch (kind) {
    case "entry":
      return "fill-fg-muted";
    case "stop":
      return "fill-danger";
    case "target":
      return "fill-ok";
    case "runner":
      return "fill-accent";
  }
}

function legendDotFor(kind: PriceLevel["kind"]): string {
  switch (kind) {
    case "entry":
      return "bg-fg-muted";
    case "stop":
      return "bg-danger";
    case "target":
      return "bg-ok";
    case "runner":
      return "bg-accent";
  }
}

import { useMemo } from "react";
import { cn } from "@/lib/cn";

/**
 * Sparkline — inline SVG line for an equity curve, drawdown, or any
 * numeric series. Operator design: dense, always-visible, no axis
 * chrome. Taller variant accepts up to ~600 points before density
 * matters; for a real backtest equity curve over a year of bars this
 * is more than enough.
 *
 * The curve is rendered against [min..max] of the supplied values,
 * with optional shaded "underwater" region (used by drawdown).
 */
export interface SparklineProps {
  values: number[];
  height?: number;
  className?: string;
  /** "ok" green (equity), "danger" red (drawdown), "neutral" muted. */
  tone?: "ok" | "danger" | "neutral";
  /** Shade the area under the line. */
  fill?: boolean;
  /** Force a baseline at zero (default true for drawdown semantics). */
  baselineAtZero?: boolean;
  /** Render an empty placeholder instead of the curve. */
  empty?: boolean;
  emptyMessage?: string;
  ariaLabel?: string;
}

const TONE_STROKE: Record<NonNullable<SparklineProps["tone"]>, string> = {
  ok: "rgb(56 196 130)",
  danger: "rgb(232 86 86)",
  neutral: "rgb(167 176 184)",
};

const TONE_FILL: Record<NonNullable<SparklineProps["tone"]>, string> = {
  ok: "rgba(56, 196, 130, 0.18)",
  danger: "rgba(232, 86, 86, 0.20)",
  neutral: "rgba(167, 176, 184, 0.12)",
};

export function Sparkline({
  values,
  height = 96,
  className,
  tone = "ok",
  fill = true,
  baselineAtZero = false,
  empty,
  emptyMessage,
  ariaLabel,
}: SparklineProps): JSX.Element {
  const { path, area, viewBox, hasPoints } = useMemo(() => {
    const finite = values.filter((v) => Number.isFinite(v));
    if (finite.length < 2) {
      return { path: "", area: "", viewBox: "0 0 100 40", hasPoints: false };
    }
    const w = 600;
    const h = 100;
    const lo = baselineAtZero ? Math.min(0, ...finite) : Math.min(...finite);
    const hi = Math.max(...finite, baselineAtZero ? 0 : -Infinity);
    const range = hi - lo || 1;
    const stepX = w / Math.max(1, finite.length - 1);
    const points = finite.map((v, i) => {
      const x = i * stepX;
      const y = h - ((v - lo) / range) * h;
      return [x, y] as const;
    });
    const lineD = points
      .map(([x, y], i) => `${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`)
      .join(" ");
    const last = points[points.length - 1];
    const first = points[0];
    const areaD = `${lineD} L ${last[0].toFixed(2)} ${h} L ${first[0].toFixed(2)} ${h} Z`;
    return { path: lineD, area: areaD, viewBox: `0 0 ${w} ${h}`, hasPoints: true };
  }, [values, baselineAtZero]);

  if (empty || !hasPoints) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded border border-dashed border-border/70 bg-bg-inset text-[11px] text-fg-subtle",
          className,
        )}
        style={{ height }}
        aria-label={ariaLabel}
      >
        {emptyMessage ?? "no data"}
      </div>
    );
  }

  const stroke = TONE_STROKE[tone];
  const areaFill = TONE_FILL[tone];

  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      viewBox={viewBox}
      preserveAspectRatio="none"
      className={cn("block w-full", className)}
      style={{ height }}
    >
      {fill ? <path d={area} fill={areaFill} stroke="none" /> : null}
      <path d={path} stroke={stroke} strokeWidth={1.5} fill="none" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

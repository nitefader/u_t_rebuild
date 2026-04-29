import { useMemo } from "react";
import { cn } from "@/lib/cn";

/**
 * Sparkline — tiny inline SVG line for ScreenerResultRow's last-30-bars
 * trail. Per the chart-first research-visualizations doctrine, each row in
 * the Screener results table renders a sparkline alongside the numeric
 * metrics so the operator can see what's happening at a glance — a wall of
 * raw numbers loses every "is this trending or chopping" signal.
 *
 * Tone derives from the trail itself: green when up, red when down, muted
 * when flat / empty.
 */
export interface SparklineProps {
  values: readonly number[];
  width?: number;
  height?: number;
  className?: string;
}

export function Sparkline(props: SparklineProps): JSX.Element {
  const { values, width = 80, height = 22, className } = props;
  const points = useMemo(() => buildPoints(values, width, height), [values, width, height]);
  if (values.length < 2) {
    return (
      <span
        className={cn("inline-block text-[10px] text-fg-subtle", className)}
        style={{ width, height }}
        aria-hidden="true"
      >
        —
      </span>
    );
  }
  const first = values[0]!;
  const last = values[values.length - 1]!;
  const tone = last > first ? "stroke-ok" : last < first ? "stroke-danger" : "stroke-fg-subtle";
  return (
    <svg
      role="img"
      aria-label={`sparkline last ${values.length} values, ${last >= first ? "up" : "down"} ${formatPct(first, last)}`}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className={cn("inline-block align-middle", className)}
    >
      <polyline
        points={points}
        fill="none"
        strokeWidth={1.25}
        className={tone}
      />
    </svg>
  );
}

function buildPoints(values: readonly number[], width: number, height: number): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const padding = 2;
  return values
    .map((v, i) => {
      const x = i * step;
      const norm = (v - min) / range;
      const y = padding + (1 - norm) * (height - padding * 2);
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function formatPct(first: number, last: number): string {
  if (first === 0) return "—";
  const pct = ((last - first) / first) * 100;
  const sign = pct > 0 ? "+" : "";
  return `${sign}${pct.toFixed(1)}%`;
}

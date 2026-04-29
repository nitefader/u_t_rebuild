import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import type { OptimizationHeatmap } from "@/api/schemas/researchRuns";

/**
 * LandscapeHeatmap.
 *
 * 2D heatmap of candidate scores, with X = first parameter values, Y = second
 * parameter values, cell colour saturation = score within [score_min,
 * score_max]. Empty cells render muted. The recommended row in the candidate
 * table corresponds to the brightest cell here — operators see at a glance
 * whether the winner sits on a plateau (good) or a spike (suspicious).
 */
export function LandscapeHeatmap({
  heatmap,
}: {
  heatmap: OptimizationHeatmap | null | undefined;
}): JSX.Element | null {
  if (!heatmap || !heatmap.cells.length) return null;
  const { min, max } = bounds(heatmap.cells);
  const range = Math.max(max - min, 1e-9);
  return (
    <Card>
      <CardHeader>
        <CardTitle>
          Landscape heatmap — {heatmap.x_field} × {heatmap.y_field}
        </CardTitle>
        <span className="text-[11px] text-fg-muted">
          score range {fmt(min)} → {fmt(max)}
        </span>
      </CardHeader>
      <CardBody>
        <div className="text-[11px] text-fg-subtle mb-2">
          Cell colour intensity is the best score at that parameter coordinate. Brighter cells
          beat dimmer ones; an isolated bright spot (vs a flat plateau) is a fragility signal —
          validate with Walk-Forward before trusting it.
        </div>
        <div
          role="grid"
          className="grid gap-px bg-border rounded overflow-hidden"
          style={{
            gridTemplateColumns: `auto repeat(${heatmap.x_values.length}, minmax(48px, 1fr))`,
          }}
        >
          {/* Top-left empty cell + X-axis labels */}
          <div className="bg-bg-inset px-2 py-1 text-[10px] font-medium text-fg-muted">
            {heatmap.y_field} ↓ / {heatmap.x_field} →
          </div>
          {heatmap.x_values.map((x, i) => (
            <div
              key={`x-${i}`}
              className="bg-bg-inset px-2 py-1 text-center text-[10px] font-mono text-fg-muted"
            >
              {String(x)}
            </div>
          ))}
          {/* Rows */}
          {heatmap.y_values.map((y, rowIndex) => (
            <Row
              key={`row-${rowIndex}`}
              y={String(y)}
              cells={heatmap.cells[rowIndex]}
              min={min}
              range={range}
            />
          ))}
        </div>
      </CardBody>
    </Card>
  );
}

function Row({
  y,
  cells,
  min,
  range,
}: {
  y: string;
  cells: Array<number | null>;
  min: number;
  range: number;
}): JSX.Element {
  return (
    <>
      <div className="bg-bg-inset px-2 py-1 text-[10px] font-mono text-fg-muted">{y}</div>
      {cells.map((cell, i) => {
        const intensity = cell == null ? 0 : Math.max(0, Math.min(1, (cell - min) / range));
        const bg = cell == null ? "bg-bg" : intensityToBg(intensity);
        return (
          <div
            key={`cell-${i}`}
            role="gridcell"
            className={`px-2 py-1 text-center text-[10px] tabular ${bg}`}
            title={cell == null ? "no candidate at this coord" : `score ${fmt(cell)}`}
          >
            {cell == null ? "—" : fmt(cell)}
          </div>
        );
      })}
    </>
  );
}

function intensityToBg(intensity: number): string {
  // Coarse 5-step gradient using accent-tone CSS classes already in the design system.
  if (intensity >= 0.85) return "bg-accent text-accent-fg font-semibold";
  if (intensity >= 0.6) return "bg-accent/70";
  if (intensity >= 0.4) return "bg-accent/45";
  if (intensity >= 0.2) return "bg-accent/25";
  return "bg-accent/10";
}

function bounds(cells: Array<Array<number | null>>): { min: number; max: number } {
  let min = Infinity;
  let max = -Infinity;
  for (const row of cells) {
    for (const v of row) {
      if (v == null || !Number.isFinite(v)) continue;
      if (v < min) min = v;
      if (v > max) max = v;
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: 0, max: 1 };
  return { min, max };
}

function fmt(n: number): string {
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(3);
}

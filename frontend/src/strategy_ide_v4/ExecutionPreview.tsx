/**
 * ExecutionPreview — horizontal stacked rails derived from legs and stops.
 * Shows each leg and the first stop as a % offset bar from entry.
 */

import type { StrategyStopV4Draft, StrategyLegV4Draft } from "@/api/schemas/strategiesV4";

export interface ExecutionPreviewProps {
  legs: StrategyLegV4Draft[];
  stops: StrategyStopV4Draft[];
}

interface RailItem {
  key: string;
  label: string;
  caption: string;
  offsetPct: number | null;
  color: "info" | "ok" | "fg-subtle" | "danger";
  placeholder?: string;
}

function formatPct(n: number): string {
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

function buildRails(legs: StrategyLegV4Draft[], stops: StrategyStopV4Draft[]): RailItem[] {
  const items: RailItem[] = [];

  // Entry anchor
  items.push({
    key: "entry",
    label: "Entry",
    caption: "Entry 0.00%",
    offsetPct: 0,
    color: "fg-subtle",
  });

  // First stop
  const stop = stops[0];
  if (stop) {
    if (stop.mode === "simple" && stop.simple_type === "%" && typeof stop.simple_value === "number") {
      const offset = -Math.abs(stop.simple_value);
      items.push({
        key: `stop-${stop.id}`,
        label: formatPct(offset),
        caption: `Trailing stop ${formatPct(offset)}`,
        offsetPct: offset,
        color: "danger",
      });
    } else if (stop.mode === "expression") {
      items.push({
        key: `stop-${stop.id}`,
        label: "expr",
        caption: "Expression stop — dynamic",
        offsetPct: null,
        color: "danger",
        placeholder: "expression stop",
      });
    } else if (stop.mode === "simple" && stop.simple_type && stop.simple_type !== "%" && typeof stop.simple_value === "number") {
      // ATR / $ / R — we cannot translate to % without runtime data
      items.push({
        key: `stop-${stop.id}`,
        label: `${stop.simple_value} ${stop.simple_type}`,
        caption: `Stop ${stop.simple_value} ${stop.simple_type} — runtime value`,
        offsetPct: null,
        color: "danger",
        placeholder: `${stop.simple_type} stop`,
      });
    }
  }

  // Legs
  for (const leg of legs) {
    const tt = leg.target_type;
    const tv = leg.target_value;

    if (tt === "feature" || tv === null || tv === undefined) {
      items.push({
        key: `leg-${leg.id}`,
        label: "feature",
        caption: `${leg.kind === "runner" ? "Runner" : `Target L${leg.position}`} — feature target`,
        offsetPct: null,
        color: leg.kind === "runner" ? "info" : "ok",
        placeholder: "feature target",
      });
      continue;
    }

    if (tt === "%" || tt === "ATR" || tt === "$" || tt === "R") {
      const offset = Math.abs(tv);
      const suffix =
        leg.kind === "runner"
          ? `Runner +${tv.toFixed(2)}${tt} · trail`
          : `Target L${leg.position} +${tv.toFixed(2)}${tt} · ${(leg.size_pct * 100).toFixed(0)}% slice`;

      items.push({
        key: `leg-${leg.id}`,
        label: tt === "%" ? formatPct(offset) : `+${tv.toFixed(2)} ${tt}`,
        caption: suffix,
        offsetPct: tt === "%" ? offset : null,
        color: leg.kind === "runner" ? "info" : "ok",
      });
    } else if (tt === "trail-ATR" || tt === "trail-%" || tt === "trail-$") {
      const unit = tt.replace("trail-", "");
      items.push({
        key: `leg-${leg.id}`,
        label: `trail ${tv.toFixed(2)}${unit}`,
        caption: `Runner trail ${tv.toFixed(2)} ${unit}`,
        offsetPct: null,
        color: "info",
      });
    }
  }

  return items;
}

const COLOR_CLASSES: Record<RailItem["color"], { text: string; dot: string }> = {
  info: { text: "text-info", dot: "bg-info" },
  ok: { text: "text-ok", dot: "bg-ok" },
  "fg-subtle": { text: "text-fg-subtle", dot: "bg-fg-subtle" },
  danger: { text: "text-danger", dot: "bg-danger" },
};

export function ExecutionPreview({ legs, stops }: ExecutionPreviewProps): JSX.Element {
  const rails = buildRails(legs, stops);

  // Compute scale from max absolute %
  const pctValues = rails
    .map((r) => r.offsetPct)
    .filter((v): v is number => v !== null);
  const maxAbs = pctValues.length > 0 ? Math.max(...pctValues.map(Math.abs), 0.01) : 5;

  return (
    <section
      aria-label="Execution preview"
      className="flex flex-col gap-1.5 rounded-lg border border-border bg-bg-subtle px-4 py-3"
    >
      <h4 className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle mb-1">
        Execution preview
      </h4>
      {rails.map((item) => {
        const colors = COLOR_CLASSES[item.color];
        const widthPct =
          item.offsetPct !== null ? (Math.abs(item.offsetPct) / maxAbs) * 100 : 0;

        return (
          <div key={item.key} className="flex items-center gap-2">
            {/* Bar */}
            <div className="relative h-4 w-32 shrink-0 overflow-visible">
              {/* Center line */}
              <div
                className="absolute top-1/2 -translate-y-1/2 bg-border"
                style={{ left: item.offsetPct !== null && item.offsetPct < 0 ? `${100 - widthPct}%` : "0%", width: item.offsetPct !== null ? `${widthPct}%` : "0%" }}
              />
              {/* Dot at position */}
              <div
                className={`absolute top-1/2 -translate-y-1/2 h-2.5 w-2.5 rounded-full ${colors.dot}`}
                style={{
                  left:
                    item.offsetPct !== null
                      ? item.offsetPct < 0
                        ? `${100 - widthPct}%`
                        : `${widthPct}%`
                      : "50%",
                  transform: "translate(-50%, -50%)",
                }}
              />
            </div>

            {/* Label */}
            <span className={`w-20 shrink-0 text-[11px] font-mono font-semibold ${colors.text}`}>
              {item.placeholder ? (
                <span className="italic text-fg-subtle">{item.placeholder}</span>
              ) : (
                item.label
              )}
            </span>

            {/* Caption */}
            <span className="text-[10px] text-fg-muted">{item.caption}</span>
          </div>
        );
      })}
    </section>
  );
}

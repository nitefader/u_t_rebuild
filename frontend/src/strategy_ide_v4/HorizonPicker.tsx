/**
 * HorizonPicker — 4-button horizon toggle + adjacent base-timeframe select.
 * UX-only filters; do NOT touch StrategyVersionV4Draft.
 * These drive the StarterStrategyPanel filter via props.
 */

export type Horizon = "scalping" | "intraday" | "swing" | "position";
export type BaseTimeframe = "1m" | "5m" | "15m" | "1h" | "1d";

const HORIZON_OPTIONS: Array<{ value: Horizon; label: string }> = [
  { value: "scalping", label: "Scalping" },
  { value: "intraday", label: "Intraday" },
  { value: "swing", label: "Swing" },
  { value: "position", label: "Position" },
];

const TIMEFRAME_OPTIONS: BaseTimeframe[] = ["1m", "5m", "15m", "1h", "1d"];

export interface HorizonPickerProps {
  horizon: Horizon | null;
  onHorizonChange: (horizon: Horizon | null) => void;
  timeframe: BaseTimeframe;
  onTimeframeChange: (tf: BaseTimeframe) => void;
}

export function HorizonPicker({
  horizon,
  onHorizonChange,
  timeframe,
  onTimeframeChange,
}: HorizonPickerProps): JSX.Element {
  return (
    <div className="flex items-center gap-2">
      <div
        role="group"
        aria-label="Horizon"
        className="flex overflow-hidden rounded border border-border-strong"
      >
        {HORIZON_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            aria-pressed={horizon === opt.value}
            onClick={() =>
              onHorizonChange(horizon === opt.value ? null : opt.value)
            }
            className={`px-3 py-1 text-xs font-medium transition-colors focus:outline-none ${
              horizon === opt.value
                ? "bg-accent text-fg"
                : "bg-bg-raised text-fg-muted hover:text-fg"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <select
        value={timeframe}
        onChange={(e) => onTimeframeChange(e.target.value as BaseTimeframe)}
        aria-label="Base timeframe"
        className="rounded border border-border bg-bg-inset px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
      >
        {TIMEFRAME_OPTIONS.map((tf) => (
          <option key={tf} value={tf}>
            {tf}
          </option>
        ))}
      </select>
    </div>
  );
}

/**
 * DirectionToggle — 3-button toggle for trade direction.
 * Replaces a Select so the operator can see all options at a glance.
 */

export type Direction = "long" | "short" | "both";

const OPTIONS: Array<{ value: Direction; label: string }> = [
  { value: "long", label: "Long only" },
  { value: "short", label: "Short only" },
  { value: "both", label: "Both" },
];

export interface DirectionToggleProps {
  value: Direction;
  onChange: (direction: Direction) => void;
}

export function DirectionToggle({ value, onChange }: DirectionToggleProps): JSX.Element {
  return (
    <div
      role="group"
      aria-label="Direction"
      className="flex overflow-hidden rounded border border-border-strong"
    >
      {OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          aria-pressed={value === opt.value}
          onClick={() => onChange(opt.value)}
          className={`px-3 py-1 text-xs font-medium transition-colors focus:outline-none ${
            value === opt.value
              ? "bg-accent text-fg"
              : "bg-bg-raised text-fg-muted hover:text-fg"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

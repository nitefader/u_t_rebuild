/**
 * StopsSection — list of StopRow components.
 * Enforces at-least-one stop. Surfaces validateStops errors inline.
 */

import type { StrategyStopV4Draft } from "@/api/schemas/strategiesV4";
import { StopRow } from "./StopRow";
import { validateStops } from "./legAutoBalance";

export interface StopsSectionProps {
  stops: StrategyStopV4Draft[];
  legCount: number;
  onChange: (stops: StrategyStopV4Draft[]) => void;
  variableNames?: string[];
  timeframeVariableNames?: string[];
}

function newStopId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function StopsSection({
  stops,
  legCount,
  onChange,
  variableNames,
  timeframeVariableNames = [],
}: StopsSectionProps): JSX.Element {
  const { errors } = validateStops(stops);

  function handleAdd(): void {
    const newStop: StrategyStopV4Draft = {
      id: newStopId(),
      mode: "simple",
      scope: "all",
      simple_type: "%",
      simple_value: 1.0,
    };
    onChange([...stops, newStop]);
  }

  function handleChange(index: number, updated: StrategyStopV4Draft): void {
    const next = stops.map((s, i) => (i === index ? updated : s));
    onChange(next);
  }

  function handleRemove(index: number): void {
    onChange(stops.filter((_, i) => i !== index));
  }

  return (
    <section className="flex flex-col gap-3" aria-label="Stops">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-fg">Stops</h3>
        <button
          type="button"
          onClick={handleAdd}
          className="text-xs px-2 py-1 rounded border border-border-strong text-fg-muted hover:text-accent hover:border-accent transition-colors"
        >
          + Add stop
        </button>
      </div>

      {errors.length > 0 ? (
        <ul className="rounded border border-danger/40 bg-danger-subtle px-3 py-2 text-xs text-danger list-disc list-inside">
          {errors.map((err) => (
            <li key={err}>{err}</li>
          ))}
        </ul>
      ) : null}

      {stops.map((stop, i) => (
        <StopRow
          key={stop.id}
          stop={stop}
          legCount={legCount}
          onChange={(updated) => handleChange(i, updated)}
          onRemove={() => handleRemove(i)}
          variableNames={variableNames}
          timeframeVariableNames={timeframeVariableNames}
        />
      ))}
    </section>
  );
}

/**
 * CoverageChips — five pill chips showing IDE field completion status.
 * Entry, Stop, Target, Runner, Exit.
 */

import { Check } from "lucide-react";
import type { StrategyStopV4Draft, StrategyLegV4Draft } from "@/api/schemas/strategiesV4";
import type { ExitsSectionValue } from "./ExitsSection";

export interface CoverageChipsProps {
  entryLong: string;
  entryShort: string;
  stops: StrategyStopV4Draft[];
  legs: StrategyLegV4Draft[];
  logicalExits: ExitsSectionValue;
}

interface ChipDef {
  label: string;
  satisfied: boolean;
  informational?: boolean;
}

export function CoverageChips({
  entryLong,
  entryShort,
  stops,
  legs,
  logicalExits,
}: CoverageChipsProps): JSX.Element {
  const chips: ChipDef[] = [
    {
      label: "Entry",
      satisfied: Boolean(entryLong.trim() || entryShort.trim()),
    },
    {
      label: "Stop",
      satisfied: stops.length >= 1,
    },
    {
      label: "Target",
      satisfied: legs.some((l) => l.kind === "target"),
    },
    {
      label: "Runner",
      satisfied: legs.some((l) => l.kind === "runner"),
      informational: true,
    },
    {
      label: "Exit",
      satisfied: logicalExits.long.length > 0 || logicalExits.short.length > 0,
      informational: true,
    },
  ];

  return (
    <div className="flex items-center gap-1.5" aria-label="Coverage status">
      {chips.map((chip) => (
        <span
          key={chip.label}
          title={
            chip.informational
              ? `${chip.label}: ${chip.satisfied ? "configured" : "not configured (optional)"}`
              : `${chip.label}: ${chip.satisfied ? "configured" : "required"}`
          }
          className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
            chip.satisfied
              ? "bg-ok-subtle border-ok/40 text-ok"
              : "bg-bg-raised border-border text-fg-subtle"
          }`}
          aria-label={`${chip.label} ${chip.satisfied ? "satisfied" : "not configured"}`}
        >
          {chip.satisfied ? (
            <Check className="h-2.5 w-2.5 shrink-0" aria-hidden="true" />
          ) : null}
          {chip.label}
        </span>
      ))}
    </div>
  );
}

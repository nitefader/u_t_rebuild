/**
 * ExitsSection — two-column logical exit editor for long and short sides.
 */

import { ExitColumn } from "./ExitColumn";
import type { ExitBlockData } from "./ExitBlock";

export interface ExitsSectionValue {
  long: ExitBlockData[];
  short: ExitBlockData[];
}

export interface ExitsSectionProps {
  value: ExitsSectionValue;
  onChange: (value: ExitsSectionValue) => void;
}

function cloneBlocksWithFreshIds(blocks: ExitBlockData[]): ExitBlockData[] {
  return blocks.map((b) => ({ ...b, id: crypto.randomUUID(), params: { ...b.params } }));
}

export function ExitsSection({ value, onChange }: ExitsSectionProps): JSX.Element {
  function handleLongChange(blocks: ExitBlockData[]): void {
    onChange({ ...value, long: blocks });
  }

  function handleShortChange(blocks: ExitBlockData[]): void {
    onChange({ ...value, short: blocks });
  }

  function handleCopyLongToShort(): void {
    if (
      value.short.length > 0 &&
      !window.confirm(
        "Replace short exits with a copy of long exits? Current short exits will be lost.",
      )
    ) {
      return;
    }
    onChange({ ...value, short: cloneBlocksWithFreshIds(value.long) });
  }

  function handleCopyShortToLong(): void {
    if (
      value.long.length > 0 &&
      !window.confirm(
        "Replace long exits with a copy of short exits? Current long exits will be lost.",
      )
    ) {
      return;
    }
    onChange({ ...value, long: cloneBlocksWithFreshIds(value.short) });
  }

  return (
    <section aria-label="Logical exits">
      <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-fg-subtle">
        Logical exits
      </h3>
      <div className="grid grid-cols-2 gap-4">
        <ExitColumn
          side="long"
          blocks={value.long}
          onChange={handleLongChange}
          onCopyToOther={handleCopyLongToShort}
        />
        <ExitColumn
          side="short"
          blocks={value.short}
          onChange={handleShortChange}
          onCopyToOther={handleCopyShortToLong}
        />
      </div>
    </section>
  );
}

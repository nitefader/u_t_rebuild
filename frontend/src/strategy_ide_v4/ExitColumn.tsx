/**
 * ExitColumn — drag-drop target column for one side (long or short) of logical exits.
 */

import React, { useState } from "react";
import { ExitBlock } from "./ExitBlock";
import type { ExitBlockData } from "./ExitBlock";
import { EXIT_DRAG_MIME, tryParseExitDrag } from "./exitDragPayload";
import { defaultParamsFor } from "./exitTemplates";

export interface ExitColumnProps {
  side: "long" | "short";
  blocks: ExitBlockData[];
  onChange: (blocks: ExitBlockData[]) => void;
  onCopyToOther: () => void;
}

export function ExitColumn({ side, blocks, onChange, onCopyToOther }: ExitColumnProps): JSX.Element {
  const [dragOver, setDragOver] = useState(false);

  const otherLabel = side === "long" ? "short" : "long";
  const headerLabel = side === "long" ? "Long exits" : "Short exits";
  // Semantic accent colours for the column left border — long=ok, short=danger
  const accentClass = side === "long" ? "border-l-ok" : "border-l-danger";
  const dotClass = side === "long" ? "bg-ok" : "bg-danger";

  function handleDragOver(e: React.DragEvent<HTMLDivElement>): void {
    if (e.dataTransfer.types.includes(EXIT_DRAG_MIME)) {
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      setDragOver(true);
    }
  }

  function handleDragLeave(): void {
    setDragOver(false);
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>): void {
    setDragOver(false);
    const raw = e.dataTransfer.getData(EXIT_DRAG_MIME);
    const payload = tryParseExitDrag(raw);
    if (!payload) return;
    e.preventDefault();

    const newBlock: ExitBlockData = {
      id: crypto.randomUUID(),
      template_id: payload.template_id,
      params: defaultParamsFor(payload.template_id),
    };
    onChange([...blocks, newBlock]);
  }

  function handleBlockChange(id: string, updated: ExitBlockData): void {
    onChange(blocks.map((b) => (b.id === id ? updated : b)));
  }

  function handleBlockRemove(id: string): void {
    onChange(blocks.filter((b) => b.id !== id));
  }

  return (
    <div
      className={`flex flex-col overflow-hidden rounded-lg border border-border bg-bg-subtle border-l-[3px] ${accentClass}`}
      aria-label={`${headerLabel} column`}
    >
      {/* Header */}
      <div className="flex shrink-0 items-center gap-2 border-b border-border px-3 py-2">
        <span
          className={`h-2.5 w-2.5 rounded-full shrink-0 ${dotClass}`}
          aria-hidden="true"
        />
        <span className="flex-1 text-xs font-semibold text-fg">{headerLabel}</span>
        <span className="text-xs text-fg-subtle">{blocks.length}</span>
        <button
          type="button"
          onClick={onCopyToOther}
          disabled={blocks.length === 0}
          className="ml-1 rounded border border-border-strong bg-transparent px-2 py-0.5 text-[10px] font-medium text-ai hover:bg-ai-subtle disabled:cursor-not-allowed disabled:opacity-40 focus:outline-none"
          aria-label={`Copy ${headerLabel} to ${otherLabel} side`}
          title={`Copy to ${otherLabel}`}
        >
          Copy to {otherLabel}
        </button>
      </div>

      {/* Drop zone + block list */}
      <div
        className={`flex flex-1 flex-col gap-2 overflow-y-auto p-3 transition-colors ${
          dragOver ? "bg-accent/5" : ""
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        role="list"
        aria-label={`${headerLabel} drop zone`}
      >
        {blocks.length === 0 ? (
          <p className="py-4 text-center text-xs text-fg-subtle">
            Drop exit blocks from the palette.
          </p>
        ) : (
          blocks.map((block) => (
            <div key={block.id} role="listitem">
              <ExitBlock
                block={block}
                onChange={(updated) => handleBlockChange(block.id, updated)}
                onRemove={() => handleBlockRemove(block.id)}
              />
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/**
 * ExitBlock — a single logical exit block with collapsible param editor.
 */

import { useState } from "react";
import { getExitTemplate } from "./exitTemplates";
import type { ExitTemplateId, ExitTemplateParamSpec } from "./exitTemplates";

export interface ExitBlockData {
  id: string;
  template_id: ExitTemplateId;
  params: Record<string, number | string | boolean>;
}

export interface ExitBlockProps {
  block: ExitBlockData;
  onChange: (block: ExitBlockData) => void;
  onRemove: () => void;
}

function clamp(value: number, min?: number, max?: number): number {
  let v = value;
  if (min !== undefined && v < min) v = min;
  if (max !== undefined && v > max) v = max;
  return v;
}

function ParamInput({
  spec,
  value,
  onChange,
}: {
  spec: ExitTemplateParamSpec;
  value: number | string | boolean;
  onChange: (v: number | string | boolean) => void;
}): JSX.Element {
  if (spec.type === "boolean") {
    return (
      <label className="flex items-center gap-2 text-xs text-fg-muted">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
          className="h-3.5 w-3.5 accent-accent"
          aria-label={spec.label}
        />
        {spec.label}
      </label>
    );
  }

  if (spec.type === "number") {
    return (
      <label className="flex flex-col gap-0.5">
        <span className="text-[10px] text-fg-subtle uppercase tracking-wider">{spec.label}</span>
        <input
          type="number"
          value={typeof value === "number" ? value : Number(value)}
          min={spec.min}
          max={spec.max}
          step="any"
          onChange={(e) => {
            const raw = parseFloat(e.target.value);
            if (!Number.isNaN(raw)) {
              onChange(clamp(raw, spec.min, spec.max));
            }
          }}
          className="w-full rounded border border-border bg-bg-inset px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
          aria-label={spec.label}
        />
      </label>
    );
  }

  // string — for bars_since.event use a select; generic strings use a text input
  if (spec.name === "event") {
    return (
      <label className="flex flex-col gap-0.5">
        <span className="text-[10px] text-fg-subtle uppercase tracking-wider">{spec.label}</span>
        <select
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          className="w-full rounded border border-border bg-bg-inset px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
          aria-label={spec.label}
        >
          <option value="entry">entry</option>
          <option value="last_target">last_target</option>
        </select>
      </label>
    );
  }

  return (
    <label className="flex flex-col gap-0.5">
      <span className="text-[10px] text-fg-subtle uppercase tracking-wider">{spec.label}</span>
      <input
        type="text"
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border border-border bg-bg-inset px-2 py-1 text-xs text-fg focus:border-accent focus:outline-none"
        aria-label={spec.label}
      />
    </label>
  );
}

export function ExitBlock({ block, onChange, onRemove }: ExitBlockProps): JSX.Element {
  const template = getExitTemplate(block.template_id);
  const [collapsed, setCollapsed] = useState(false);

  function handleParamChange(name: string, value: number | string | boolean): void {
    onChange({ ...block, params: { ...block.params, [name]: value } });
  }

  return (
    <div
      className="rounded-lg border border-border-strong bg-bg-raised overflow-hidden"
      data-testid="exit-block"
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2">
        <button
          type="button"
          className="flex-1 text-left text-xs font-semibold text-accent hover:text-accent/80 focus:outline-none"
          onClick={() => setCollapsed((c) => !c)}
          aria-expanded={!collapsed}
          aria-label={`${template.label} — toggle params`}
        >
          {template.label}
          {template.params.length > 0 ? (
            <span className="ml-1 text-[10px] text-fg-subtle">{collapsed ? "▼" : "▲"}</span>
          ) : null}
        </button>
        <button
          type="button"
          onClick={onRemove}
          className="flex h-5 w-5 items-center justify-center rounded text-fg-subtle hover:bg-danger-subtle hover:text-danger focus:outline-none"
          aria-label={`Remove ${template.label}`}
          title="Remove"
        >
          x
        </button>
      </div>

      {/* Param body */}
      {!collapsed && template.params.length > 0 ? (
        <div className="flex flex-col gap-2 border-t border-border px-3 pb-3 pt-2">
          {template.params.map((spec) => (
            <ParamInput
              key={spec.name}
              spec={spec}
              value={block.params[spec.name] ?? spec.default}
              onChange={(v) => handleParamChange(spec.name, v)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

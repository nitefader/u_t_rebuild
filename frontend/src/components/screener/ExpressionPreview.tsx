import type { ScreenerCriterion } from "@/api/schemas/screener";
import { StatusBadge, type StatusTone } from "@/components/badges/StatusBadge";

interface ExpressionNodeShape {
  kind?: string;
  criterion?: ScreenerCriterion | null;
  children?: ExpressionNodeShape[];
}

export function ExpressionPreview({
  expression,
  title = "Compiled expression",
}: {
  expression: unknown;
  title?: string;
}): JSX.Element {
  return (
    <div className="rounded border border-border bg-bg-inset/40 p-2">
      <div className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
        {title}
      </div>
      <ExpressionNode node={expression as ExpressionNodeShape | null} depth={0} />
    </div>
  );
}

function ExpressionNode({
  node,
  depth,
}: {
  node: ExpressionNodeShape | null;
  depth: number;
}): JSX.Element {
  if (!node || typeof node !== "object") {
    return <div className="text-[11px] text-fg-muted">No expression compiled.</div>;
  }

  if (node.kind === "criterion" && node.criterion) {
    return (
      <div className="rounded border border-border/60 bg-bg-raised px-2 py-1 text-[11px]">
        {criterionLabel(node.criterion)}
      </div>
    );
  }

  const kind = normalizeKind(node.kind);
  const children = node.children ?? [];
  return (
    <div className={depth === 0 ? "space-y-1.5" : "ml-3 space-y-1.5 border-l border-border pl-2"}>
      <div className="flex items-center gap-1">
        <StatusBadge tone={toneForKind(kind)} size="sm">
          {kind}
        </StatusBadge>
        <span className="text-[11px] text-fg-muted">
          {children.length} {children.length === 1 ? "child" : "children"}
        </span>
      </div>
      {children.length ? (
        children.map((child, idx) => (
          <ExpressionNode key={`${kind}-${idx}`} node={child} depth={depth + 1} />
        ))
      ) : (
        <div className="text-[11px] text-fg-muted">No child rules.</div>
      )}
    </div>
  );
}

function normalizeKind(kind: string | undefined): "ALL" | "ANY" | "NOT" | "EXPR" {
  if (kind === "all") return "ALL";
  if (kind === "any") return "ANY";
  if (kind === "not") return "NOT";
  return "EXPR";
}

function toneForKind(kind: "ALL" | "ANY" | "NOT" | "EXPR"): StatusTone {
  if (kind === "ALL") return "ok";
  if (kind === "ANY") return "info";
  if (kind === "NOT") return "warn";
  return "neutral";
}

function criterionLabel(c: ScreenerCriterion): string {
  const value = c.operator === "between" ? `${String(c.value)} to ${String(c.value_max)}` : String(c.value);
  return c.label || `${c.metric} ${c.operator} ${value}`;
}

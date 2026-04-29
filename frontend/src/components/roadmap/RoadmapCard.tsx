import { useState } from "react";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { Button } from "@/components/ui/Button";

/**
 * RoadmapCard.
 *
 * Surfaces the explicitly-out-of-scope items from a slice's plan as a
 * forward-looking note. Status enum:
 *   - shipped     — already in production (close the loop on prior promises)
 *   - in_design   — design exists; not yet coding
 *   - planned     — committed; not yet designed
 *   - parked      — named but not currently scheduled (operator visibility only)
 *
 * Rendered as collapsible by default so it doesn't compete with primary
 * content; expand when operator wants the forward view.
 */
export type RoadmapItemStatus = "shipped" | "in_design" | "planned" | "parked";

export interface RoadmapItem {
  title: string;
  status: RoadmapItemStatus;
  description: string;
  category?: string;
}

export function RoadmapCard({
  surface,
  items,
  defaultOpen = false,
}: {
  surface: string;
  items: RoadmapItem[];
  defaultOpen?: boolean;
}): JSX.Element | null {
  const [open, setOpen] = useState<boolean>(defaultOpen);
  if (!items.length) return null;
  const counts = items.reduce<Record<RoadmapItemStatus, number>>(
    (acc, item) => {
      acc[item.status] = (acc[item.status] ?? 0) + 1;
      return acc;
    },
    { shipped: 0, in_design: 0, planned: 0, parked: 0 },
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Roadmap — {surface}</CardTitle>
        <span className="flex items-center gap-2 text-[11px]">
          {counts.shipped ? <StatusBadge tone="ok">{counts.shipped} shipped</StatusBadge> : null}
          {counts.in_design ? <StatusBadge tone="warn">{counts.in_design} in design</StatusBadge> : null}
          {counts.planned ? <StatusBadge tone="info">{counts.planned} planned</StatusBadge> : null}
          {counts.parked ? <StatusBadge tone="muted">{counts.parked} parked</StatusBadge> : null}
          <Button size="sm" variant="ghost" onClick={() => setOpen(!open)}>
            {open ? "Hide" : "Show"}
          </Button>
        </span>
      </CardHeader>
      {open ? (
        <CardBody className="space-y-3 text-xs">
          <p className="text-fg-subtle">
            Forward-looking surface — items that were explicitly out-of-scope of the slice
            that built this page, plus shipped follow-ups. Not promises; visibility into
            what's coming and what's deferred.
          </p>
          {Object.entries(groupByCategory(items)).map(([category, rows]) => (
            <div key={category}>
              {category !== "_default" ? (
                <div className="mb-2 text-[11px] uppercase tracking-wider text-fg-muted">{category}</div>
              ) : null}
              <ul className="space-y-2">
                {rows.map((item) => (
                  <li key={item.title} className="rounded border border-border p-2">
                    <div className="mb-1 flex items-center gap-2">
                      <StatusBadge tone={statusTone(item.status)}>{statusLabel(item.status)}</StatusBadge>
                      <span className="font-medium">{item.title}</span>
                    </div>
                    <p className="text-fg-muted leading-relaxed">{item.description}</p>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </CardBody>
      ) : null}
    </Card>
  );
}

function groupByCategory(items: RoadmapItem[]): Record<string, RoadmapItem[]> {
  const groups: Record<string, RoadmapItem[]> = {};
  for (const item of items) {
    const key = item.category ?? "_default";
    (groups[key] ??= []).push(item);
  }
  return groups;
}

function statusTone(status: RoadmapItemStatus): "ok" | "warn" | "info" | "muted" {
  switch (status) {
    case "shipped":
      return "ok";
    case "in_design":
      return "warn";
    case "planned":
      return "info";
    case "parked":
      return "muted";
  }
}

function statusLabel(status: RoadmapItemStatus): string {
  return status.replace("_", " ");
}

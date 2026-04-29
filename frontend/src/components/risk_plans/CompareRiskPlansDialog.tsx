import { useEffect, useMemo, useState } from "react";
import { useQueries } from "@tanstack/react-query";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { RiskPlansApi } from "@/api/riskPlans";
import type { RiskPlanDetail, RiskPlanSummary } from "@/api/schemas/riskPlans";
import { Banner } from "@/components/ui/Banner";
import { Select } from "@/components/ui/Select";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { cn } from "@/lib/cn";

/**
 * CompareRiskPlansDialog — pick two Risk Plans, render a side-by-side
 * field diff with highlighting and signed `(±N)` deltas on numeric fields.
 *
 * Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §9.2 actions: Compare.
 */
export interface CompareRiskPlansDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  plans: RiskPlanSummary[];
  initial: { a: string; b: string } | null;
}

interface ComparisonRow {
  group: string;
  field: string;
  label: string;
  a: unknown;
  b: unknown;
  diff: boolean;
  numericDelta?: { delta: number; positive: boolean };
}

const FIELD_GROUPS: Array<{
  group: string;
  fields: Array<{ key: string; label: string; numeric?: boolean; topLevel?: boolean }>;
}> = [
  {
    group: "Identity",
    fields: [
      { key: "risk_score", label: "Risk score", topLevel: true, numeric: true },
      { key: "risk_tier", label: "Risk tier", topLevel: true },
      { key: "status", label: "Status", topLevel: true },
      { key: "source", label: "Source", topLevel: true },
    ],
  },
  {
    group: "Sizing",
    fields: [
      { key: "sizing_method", label: "Sizing method" },
      { key: "fixed_shares", label: "Fixed shares", numeric: true },
      { key: "fixed_notional", label: "Fixed notional", numeric: true },
      { key: "risk_per_trade_pct", label: "Risk per trade (%)", numeric: true },
      { key: "account_allocation_pct", label: "Account allocation (%)", numeric: true },
      { key: "max_trade_notional", label: "Max trade notional", numeric: true },
      { key: "min_trade_notional", label: "Min trade notional", numeric: true },
    ],
  },
  {
    group: "Exposure limits",
    fields: [
      { key: "max_position_notional", label: "Max position notional", numeric: true },
      { key: "max_position_pct_of_equity", label: "Max position % equity", numeric: true },
      { key: "max_symbol_exposure_pct", label: "Max symbol exposure (%)", numeric: true },
      { key: "max_sector_exposure_pct", label: "Max sector exposure (%)", numeric: true },
      { key: "max_gross_exposure_pct", label: "Max gross exposure (%)", numeric: true },
      { key: "max_net_exposure_pct", label: "Max net exposure (%)", numeric: true },
      { key: "max_open_positions", label: "Max open positions", numeric: true },
      { key: "max_open_risk_pct", label: "Max open risk (%)", numeric: true },
    ],
  },
  {
    group: "Loss limits",
    fields: [
      { key: "max_daily_loss_pct", label: "Max daily loss (%)", numeric: true },
      { key: "max_drawdown_pct", label: "Max drawdown (%)", numeric: true },
      { key: "max_trades_per_day", label: "Max trades / day", numeric: true },
      { key: "cooldown_after_loss_minutes", label: "Cooldown after loss (min)", numeric: true },
    ],
  },
  {
    group: "Quantity rules",
    fields: [
      { key: "fractional_quantity_allowed", label: "Fractional allowed" },
      { key: "whole_share_rounding", label: "Whole-share rounding" },
      { key: "min_quantity", label: "Min quantity", numeric: true },
      { key: "max_quantity", label: "Max quantity", numeric: true },
    ],
  },
  {
    group: "Position rules",
    fields: [
      { key: "stop_required", label: "Stop required" },
      { key: "reject_if_no_stop", label: "Reject if no stop" },
      { key: "default_stop_policy", label: "Default stop policy" },
      { key: "target_required", label: "Target required" },
      { key: "runner_allowed", label: "Runner allowed" },
      { key: "allow_scale_in", label: "Allow scale-in" },
      { key: "allow_scale_out", label: "Allow scale-out" },
      { key: "allow_short", label: "Allow short" },
      { key: "allow_extended_hours", label: "Allow extended hours" },
    ],
  },
  {
    group: "Restrictions",
    fields: [
      { key: "symbol_restrictions", label: "Symbol restrictions" },
      { key: "asset_class_restrictions", label: "Asset class restrictions" },
      { key: "account_mode_restrictions", label: "Account mode restrictions" },
    ],
  },
];

function getValue(detail: RiskPlanDetail | undefined, key: string, topLevel?: boolean): unknown {
  if (!detail) return undefined;
  if (topLevel) {
    return (detail as unknown as Record<string, unknown>)[key];
  }
  return (detail.active_version?.config as unknown as Record<string, unknown> | undefined)?.[key];
}

function format(value: unknown): string {
  if (value == null) return "—";
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  return String(value);
}

export function CompareRiskPlansDialog({
  open,
  onOpenChange,
  plans,
  initial,
}: CompareRiskPlansDialogProps): JSX.Element | null {
  const [a, setA] = useState<string>("");
  const [b, setB] = useState<string>("");

  useEffect(() => {
    if (!open) return;
    setA(initial?.a ?? plans[0]?.risk_plan_id ?? "");
    setB(initial?.b ?? plans[1]?.risk_plan_id ?? plans[0]?.risk_plan_id ?? "");
  }, [open, initial, plans]);

  const queries = useQueries({
    queries: [a, b]
      .filter(Boolean)
      .map((id) => ({
        queryKey: ["risk-plans", "detail", id],
        queryFn: () => RiskPlansApi.get(id),
        enabled: open && Boolean(id),
      })),
  });

  const detailA = a ? (queries[0]?.data as RiskPlanDetail | undefined) : undefined;
  const detailB = b ? (queries[a === b ? 0 : 1]?.data as RiskPlanDetail | undefined) : undefined;
  const loading = queries.some((q) => q.isLoading);

  const rows: ComparisonRow[] = useMemo(() => {
    const out: ComparisonRow[] = [];
    for (const grp of FIELD_GROUPS) {
      for (const field of grp.fields) {
        const va = getValue(detailA, field.key, field.topLevel);
        const vb = getValue(detailB, field.key, field.topLevel);
        const equal = JSON.stringify(va) === JSON.stringify(vb);
        let numericDelta: ComparisonRow["numericDelta"];
        if (field.numeric && typeof va === "number" && typeof vb === "number") {
          const d = vb - va;
          numericDelta = { delta: d, positive: d > 0 };
        }
        out.push({
          group: grp.group,
          field: field.key,
          label: field.label,
          a: va,
          b: vb,
          diff: !equal,
          numericDelta,
        });
      }
    }
    return out;
  }, [detailA, detailB]);

  const diffCount = rows.filter((r) => r.diff).length;

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/55 backdrop-blur-sm" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-[min(96vw,72rem)] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded border border-border bg-bg-raised shadow-raised">
          <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0">
              <DialogPrimitive.Title className="text-sm font-semibold tracking-tight">
                Compare Risk Plans
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="text-xs text-fg-muted">
                {diffCount === 0
                  ? "No differences across the active version configs."
                  : `${diffCount} field${diffCount === 1 ? "" : "s"} differ between the two active versions.`}
              </DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close
              aria-label="Close compare dialog"
              className="rounded p-1 text-fg-muted hover:bg-bg-subtle hover:text-fg"
            >
              <X className="h-4 w-4" />
            </DialogPrimitive.Close>
          </header>
          <div className="grid grid-cols-2 gap-3 border-b border-border px-4 py-3">
            <Select label="Plan A" value={a} onChange={(e) => setA(e.target.value)}>
              <option value="">—</option>
              {plans.map((p) => (
                <option key={p.risk_plan_id} value={p.risk_plan_id}>
                  {p.name}
                </option>
              ))}
            </Select>
            <Select label="Plan B" value={b} onChange={(e) => setB(e.target.value)}>
              <option value="">—</option>
              {plans.map((p) => (
                <option key={p.risk_plan_id} value={p.risk_plan_id}>
                  {p.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="max-h-[70vh] overflow-auto px-4 py-3 text-xs">
            {!a || !b ? (
              <Banner severity="info" title="Pick two Risk Plans" message="Choose Plan A and Plan B above to render the diff." />
            ) : loading ? (
              <LoadingState title="Loading Risk Plans" />
            ) : (
              <CompareTable rows={rows} aName={detailA?.name ?? "—"} bName={detailB?.name ?? "—"} />
            )}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function CompareTable({
  rows,
  aName,
  bName,
}: {
  rows: ComparisonRow[];
  aName: string;
  bName: string;
}): JSX.Element {
  let lastGroup = "";
  return (
    <table className="w-full table-fixed text-xs">
      <thead className="sticky top-0 bg-bg-raised text-fg-muted">
        <tr>
          <th className="w-1/4 px-2 py-1.5 text-left font-medium">Field</th>
          <th className="w-1/3 px-2 py-1.5 text-left font-medium">{aName}</th>
          <th className="w-1/3 px-2 py-1.5 text-left font-medium">{bName}</th>
          <th className="w-12 px-2 py-1.5 text-left font-medium">Δ</th>
        </tr>
      </thead>
      <tbody>
        {rows.flatMap((row) => {
          const showGroup = row.group !== lastGroup;
          lastGroup = row.group;
          const out: JSX.Element[] = [];
          if (showGroup) {
            out.push(
              <tr key={`${row.group}-header`} className="bg-bg-subtle">
                <td
                  colSpan={4}
                  className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-fg-subtle"
                >
                  {row.group}
                </td>
              </tr>,
            );
          }
          out.push(
            <tr
              key={`${row.group}-${row.field}`}
              className={cn(row.diff ? "bg-warn-subtle/40" : "")}
            >
              <td className="px-2 py-1 text-fg-muted">{row.label}</td>
              <td className="px-2 py-1 font-mono text-fg">{format(row.a)}</td>
              <td className="px-2 py-1 font-mono text-fg">{format(row.b)}</td>
              <td className="px-2 py-1">
                {row.numericDelta && row.diff ? (
                  <StatusBadge size="sm" tone={row.numericDelta.positive ? "warn" : "ok"}>
                    {row.numericDelta.positive ? "+" : ""}
                    {row.numericDelta.delta.toFixed(4)}
                  </StatusBadge>
                ) : row.diff ? (
                  <StatusBadge size="sm" tone="warn">
                    Δ
                  </StatusBadge>
                ) : null}
              </td>
            </tr>,
          );
          return out;
        })}
      </tbody>
    </table>
  );
}

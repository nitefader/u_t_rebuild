import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import { StrategyControlsApi } from "@/api/strategyControls";
import { ExecutionPlansApi } from "@/api/executionPlans";

/**
 * DefaultsSection — Compose v4 selectors for the two component types
 * a Strategy carries default IDs for: StrategyControls and Execution Plan.
 *
 * Doctrine (operator-stated, plan file `strategy-builder-must-only-abundant-allen.md`):
 *   "Strategy Builder must only edit strategy signal logic. Risk Plan,
 *   Execution Plan, and Strategy Control are linked component selectors,
 *   not embedded strategy fields."
 *
 * These are *defaults* — the actual binding happens at Deployment time
 * (see memory: feedback_deployment_is_the_binder.md). Pinning a default
 * version on the Strategy reduces per-Deployment configuration burden
 * but never overrides the Deployment's own pin.
 *
 * Risk Plan is intentionally NOT here. Per memory feedback_four_layer_ownership.md,
 * Risk Plan lives at the Account+Governor layer and StrategyVersionV4Draft has no
 * `default_risk_plan_version_id` field. Risk Plan binding is operator-set on the
 * Account or the Deployment.
 *
 * Each row: [▼ select existing version] [Open editor →]. Selectors only —
 * inline editing of the linked entity violates the doctrine.
 */
export interface DefaultsSectionProps {
  defaultStrategyControlsVersionId: string | null;
  onDefaultStrategyControlsChange: (id: string | null) => void;
  defaultExecutionPlanVersionId: string | null;
  onDefaultExecutionPlanChange: (id: string | null) => void;
  /** When true, render a compact horizontal strip; otherwise a stacked block. */
  compact?: boolean;
}

export function DefaultsSection({
  defaultStrategyControlsVersionId,
  onDefaultStrategyControlsChange,
  defaultExecutionPlanVersionId,
  onDefaultExecutionPlanChange,
  compact = false,
}: DefaultsSectionProps): JSX.Element {
  const controlsList = useQuery({
    queryKey: ["strategy-controls", "list"],
    queryFn: () => StrategyControlsApi.list(),
    staleTime: 30_000,
  });
  const plansList = useQuery({
    queryKey: ["execution-plans", "list"],
    queryFn: () => ExecutionPlansApi.list(),
    staleTime: 30_000,
  });

  const controlsOptions = (controlsList.data?.libraries ?? []).filter(
    (lib) => lib.head_version_id != null,
  );
  const plansOptions = (plansList.data?.libraries ?? []).filter(
    (lib) => lib.head_version_id != null,
  );

  const wrapperClass = compact
    ? "flex flex-wrap items-end gap-3 border-b border-border bg-bg-raised px-4 py-2"
    : "grid grid-cols-1 gap-3 rounded border border-border bg-bg-raised p-3 md:grid-cols-2";

  return (
    <div className={wrapperClass}>
      <DefaultRow
        label="Default Strategy Controls"
        value={defaultStrategyControlsVersionId}
        onChange={onDefaultStrategyControlsChange}
        loading={controlsList.isLoading}
        options={controlsOptions.map((lib) => ({
          value: lib.head_version_id as string,
          label: `${lib.name} · v${lib.head_version_number}${lib.is_default ? " (library default)" : ""}`,
        }))}
        editorPath={editorPathFromControls(defaultStrategyControlsVersionId, controlsOptions)}
        editorListPath="/controls"
        listLabel="controls"
      />
      <DefaultRow
        label="Default Execution Plan"
        value={defaultExecutionPlanVersionId}
        onChange={onDefaultExecutionPlanChange}
        loading={plansList.isLoading}
        options={plansOptions.map((lib) => ({
          value: lib.head_version_id as string,
          label: `${lib.name} · v${lib.head_version_number}${lib.is_default ? " (library default)" : ""}`,
        }))}
        editorPath={editorPathFromPlans(defaultExecutionPlanVersionId, plansOptions)}
        editorListPath="/execution-plans"
        listLabel="execution plans"
      />
    </div>
  );
}

function DefaultRow({
  label,
  value,
  onChange,
  loading,
  options,
  editorPath,
  editorListPath,
  listLabel,
}: {
  label: string;
  value: string | null;
  onChange: (id: string | null) => void;
  loading: boolean;
  options: Array<{ value: string; label: string }>;
  editorPath: string;
  editorListPath: string;
  listLabel: string;
}): JSX.Element {
  return (
    <div className="flex items-end gap-2">
      <label className="block min-w-0 flex-1 text-xs">
        <span className="text-fg-muted">{label}</span>
        <select
          value={value ?? ""}
          disabled={loading}
          onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
          aria-label={label}
          className="mt-1 block w-full rounded border border-border bg-bg-inset px-2 py-1.5 text-sm focus:border-accent focus:outline-none disabled:opacity-60"
        >
          <option value="">{loading ? "Loading…" : "— None (Deployment binds) —"}</option>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      <Link
        to={value ? editorPath : editorListPath}
        className="inline-flex shrink-0 items-center gap-1 rounded border border-border bg-bg-inset px-2 py-1.5 text-xs text-accent hover:border-accent"
        aria-label={value ? `Open ${label} in editor` : `Open ${listLabel} list`}
        title={value ? `Open ${label} in editor` : `Open ${listLabel} list`}
      >
        <ExternalLink className="h-3 w-3" aria-hidden="true" />
        {value ? "Open editor" : `Open ${listLabel}`}
      </Link>
    </div>
  );
}

function editorPathFromControls(
  versionId: string | null,
  options: Array<{ strategy_controls_id: string; head_version_id?: string }>,
): string {
  if (!versionId) return "/controls";
  const lib = options.find((o) => o.head_version_id === versionId);
  return lib ? `/controls/${lib.strategy_controls_id}/edit` : "/controls";
}

function editorPathFromPlans(
  versionId: string | null,
  options: Array<{ execution_plan_id: string; head_version_id?: string }>,
): string {
  if (!versionId) return "/execution-plans";
  const lib = options.find((o) => o.head_version_id === versionId);
  return lib ? `/execution-plans/${lib.execution_plan_id}/edit` : "/execution-plans";
}

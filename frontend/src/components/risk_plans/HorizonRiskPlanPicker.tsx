import { Select } from "@/components/ui/Select";
import { TRADING_HORIZON_LABELS, type TradingHorizon } from "@/api/schemas/risk";
import type { RiskPlanSummary } from "@/api/schemas/riskPlans";

/**
 * HorizonRiskPlanPicker — a labeled `<Select>` for one horizon slot.
 *
 * Renders the RiskPlans that have an active version as options. The operator
 * can also pick "— None —" to clear the mapping for this horizon.
 *
 * Slice B adversarial fixes:
 * - F-BUG-1: when the saved version_id is not in the available options
 *   (plan archived, version deprecated, etc.), render an explicit
 *   "⚠ Archived plan — re-select" hint so the operator knows the map row
 *   is stale and trades will be silently rejected.
 * - F-RISK-2: rely on the wrapping `<label>` for accessibility (no
 *   double-labeling via aria-label); accept aria-describedby so the parent
 *   can link the explainer banner.
 * - F-NIT-1: tighten resolveVersionId to never use `!`; the filter at line
 *   34 already guarantees the value, but a typed accessor is safer if the
 *   schema evolves.
 */
export interface HorizonRiskPlanPickerProps {
  horizon: TradingHorizon;
  selectedRiskPlanVersionId: string | null;
  availableRiskPlans: RiskPlanSummary[];
  onChange: (riskPlanVersionId: string | null) => void;
  disabled?: boolean;
  describedById?: string;
}

export function HorizonRiskPlanPicker({
  horizon,
  selectedRiskPlanVersionId,
  availableRiskPlans,
  onChange,
  disabled = false,
  describedById,
}: HorizonRiskPlanPickerProps): JSX.Element {
  // Slice B fix F-RISK-2: the wrapping `<label>` element provides the
  // accessible name; we explicitly include "risk plan" so the label text is
  // self-describing for screen readers without needing a second aria-label.
  const label = `${TRADING_HORIZON_LABELS[horizon]} risk plan`;

  // Build the options list. Each entry carries the chosen version id and the
  // display label so we can compute "is the saved value still selectable?"
  // without re-walking the plan list later.
  const options = availableRiskPlans.flatMap((plan) => {
    const versionId = resolveVersionId(plan);
    if (versionId === null) return [];
    const versionSuffix = plan.active_version?.version != null ? ` (v${plan.active_version.version})` : "";
    return [{ key: plan.risk_plan_id, versionId, label: `${plan.name}${versionSuffix}` }];
  });

  const savedValueIsStale =
    selectedRiskPlanVersionId !== null &&
    !options.some((o) => o.versionId === selectedRiskPlanVersionId);

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>): void {
    const val = e.target.value;
    onChange(val === "" ? null : val);
  }

  return (
    <div className="space-y-1">
      <Select
        label={label}
        value={savedValueIsStale ? "" : selectedRiskPlanVersionId ?? ""}
        onChange={handleChange}
        disabled={disabled}
        aria-describedby={describedById}
      >
        <option value="">— None —</option>
        {savedValueIsStale ? (
          // Slice B F-BUG-1: surface the dangling map row so the operator
          // re-selects instead of silently letting the Governor reject every
          // SignalPlan for this Account-horizon pair.
          <option value="" disabled>
            ⚠ Archived plan — re-select
          </option>
        ) : null}
        {options.map((o) => (
          <option key={o.key} value={o.versionId}>
            {o.label}
          </option>
        ))}
      </Select>
      {savedValueIsStale ? (
        <div
          className="text-warn text-[11px]"
          data-testid={`horizon-stale-${horizon}`}
        >
          ⚠ The mapped RiskPlan is no longer available. Re-select to keep
          trading on this horizon.
        </div>
      ) : null}
    </div>
  );
}

function resolveVersionId(plan: RiskPlanSummary): string | null {
  // Prefer the explicit top-level field; fall back to the nested active_version
  // object. Returns null if neither is present, which is filtered out before
  // it can reach the option list.
  return (
    plan.active_version_id ??
    plan.active_version?.risk_plan_version_id ??
    null
  );
}

import { useState } from "react";
import { Save } from "lucide-react";
import { Button, type ButtonVariant } from "@/components/ui/Button";
import type { RiskPlanSource } from "@/api/schemas/riskPlans";
import { RiskPlanDrawer } from "./RiskPlanDrawer";
import type { RiskPlanFormState } from "./riskPlanForm";

/**
 * SaveAsRiskPlanButton.
 *
 * Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §13: AI / research surfaces
 * cannot silently mint a Risk Plan. The button opens the Create drawer pre-filled
 * with the recommended parameters; the operator must review and click Save.
 *
 * Used by the Walk-Forward `RecommendedRiskPlanCard` (source=walk_forward_recommended)
 * and the Optimization winner card (source=optimization_generated).
 */
export interface SaveAsRiskPlanButtonProps {
  /** Recommendation source — pinned on the saved Risk Plan. */
  source: RiskPlanSource;
  /** Pre-fill for the Create drawer. */
  prefill: Partial<RiskPlanFormState>;
  /**
   * Persisted AI summary attached to the saved Risk Plan (`ai_summary`
   * per contract §4.1). Operator can still edit before saving.
   */
  aiSummary?: string | null;
  /**
   * Ephemeral warnings shown in the drawer for review. Not persisted —
   * operator reads, decides, and saves.
   */
  aiWarnings?: readonly string[];
  /** Button label override. */
  label?: string;
  /** Button variant; defaults to primary. */
  variant?: ButtonVariant;
  /** Disable when prefill cannot produce a sensible Risk Plan. */
  disabled?: boolean;
}

export function SaveAsRiskPlanButton({
  source,
  prefill,
  aiSummary,
  aiWarnings,
  label = "Save as Risk Plan",
  variant = "primary",
  disabled,
}: SaveAsRiskPlanButtonProps): JSX.Element {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        size="sm"
        variant={variant}
        leftIcon={<Save className="h-3.5 w-3.5" aria-hidden="true" />}
        disabled={disabled}
        onClick={() => setOpen(true)}
      >
        {label}
      </Button>
      <RiskPlanDrawer
        open={open}
        onOpenChange={setOpen}
        mode="create"
        defaultSource={source}
        prefill={prefill}
        defaultAiSummary={aiSummary ?? null}
        defaultAiWarnings={aiWarnings}
      />
    </>
  );
}

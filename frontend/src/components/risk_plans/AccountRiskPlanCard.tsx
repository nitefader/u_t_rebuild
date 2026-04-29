import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Save, Shield } from "lucide-react";
import { ApiError } from "@/api/client";
import { RiskPlansApi } from "@/api/riskPlans";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { RiskPlanPicker } from "./RiskPlanPicker";

/**
 * AccountRiskPlanCard.
 *
 * Per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §4.5 + §8.2:
 *   GET /api/v1/accounts/{account_id}/risk-plan
 *   PUT /api/v1/accounts/{account_id}/risk-plan
 *
 * Surfaces the Account's default RiskPlan + version. PUT is operator-driven —
 * the runtime spine reads this assignment when sizing every SignalPlan in the
 * paper / live runtime path.
 */
export function AccountRiskPlanCard({ accountId }: { accountId: string }): JSX.Element {
  const queryClient = useQueryClient();
  const assignment = useQuery({
    queryKey: ["accounts", accountId, "risk-plan"],
    queryFn: () => RiskPlansApi.getAccountAssignment(accountId),
    retry: 1,
  });

  const [pendingVersionId, setPendingVersionId] = useState<string | null>(null);

  useEffect(() => {
    if (assignment.data?.risk_plan_version_id !== undefined) {
      setPendingVersionId(assignment.data.risk_plan_version_id ?? null);
    }
  }, [assignment.data?.risk_plan_version_id]);

  // The picker emits a `risk_plan_version_id`; we resolve the matching
  // `risk_plan_id` from the same list query the picker reads, so PUT carries
  // both fields and the backend's `version belongs to plan` check passes.
  const list = useQuery({
    queryKey: ["risk-plans", "list"],
    queryFn: () => RiskPlansApi.list(),
    retry: 1,
  });
  const versionIdToPlanId = new Map<string, string>();
  for (const plan of list.data?.risk_plans ?? []) {
    const versionId = plan.active_version_id ?? plan.active_version?.risk_plan_version_id;
    if (versionId) versionIdToPlanId.set(versionId, plan.risk_plan_id);
  }

  const resolvedRiskPlanId =
    pendingVersionId != null
      ? versionIdToPlanId.get(pendingVersionId) ?? assignment.data?.risk_plan_id ?? null
      : null;

  const save = useMutation({
    mutationFn: () => {
      if (pendingVersionId == null || resolvedRiskPlanId == null) {
        throw new Error("Pick a Risk Plan version before saving");
      }
      return RiskPlansApi.putAccountAssignment(accountId, {
        risk_plan_id: resolvedRiskPlanId,
        risk_plan_version_id: pendingVersionId,
      });
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(["accounts", accountId, "risk-plan"], saved);
    },
  });

  const dirty =
    (assignment.data?.risk_plan_version_id ?? null) !== (pendingVersionId ?? null);
  const canSave = dirty && pendingVersionId != null && resolvedRiskPlanId != null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="flex items-center gap-2">
            <Shield className="h-4 w-4 text-fg-subtle" aria-hidden="true" />
            Default Risk Plan
          </span>
        </CardTitle>
        {assignment.data?.risk_plan ? (
          <StatusBadge tone="ok">{assignment.data.risk_plan.name}</StatusBadge>
        ) : (
          <StatusBadge tone="warn">unassigned</StatusBadge>
        )}
      </CardHeader>
      <CardBody className="space-y-3 text-xs">
        {assignment.isLoading ? (
          <LoadingState title="Loading default Risk Plan" />
        ) : null}
        {assignment.isError ? (
          <Banner
            severity="warning"
            title="Default Risk Plan route not yet registered"
            message={
              assignment.error instanceof ApiError && assignment.error.status === 404
                ? "Operation Turtle Shell ships GET /api/v1/accounts/{id}/risk-plan with the Risk Plan slice. Until then this Account uses the system default."
                : (assignment.error as Error)?.message
            }
          />
        ) : null}

        <RiskPlanPicker
          label="Default Risk Plan version"
          value={pendingVersionId}
          onChange={setPendingVersionId}
          hint="The runtime resolver reads this when sizing every SignalPlan against this Account."
        />

        {save.error ? (
          <Banner
            severity="danger"
            title="Could not save"
            message={
              save.error instanceof ApiError ? save.error.detail || save.error.message : String(save.error)
            }
          />
        ) : null}

        <div className="flex items-center justify-end gap-2">
          <Button
            size="sm"
            variant="primary"
            disabled={!canSave || save.isPending}
            loading={save.isPending}
            leftIcon={<Save className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => save.mutate()}
          >
            Save default
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

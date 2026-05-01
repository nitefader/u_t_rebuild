/**
 * RebindDeploymentDrawer — hot-swap Controls and/or ExecutionPlan on a
 * running Deployment without disrupting open positions.
 *
 * Opens from a Rebind button on an ACTIVE deployment row or from the
 * DeploymentDetail view.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { DeploymentsApi } from "@/api/deployments";
import { StrategyControlsApi } from "@/api/strategyControls";
import { ExecutionPlansApi } from "@/api/executionPlans";
import type { Deployment } from "@/api/schemas/deployments";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";

type EffectiveMode = "now" | "next_session" | "custom";

export function RebindDeploymentDrawer({
  open,
  onOpenChange,
  deployment,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  deployment: Deployment;
}): JSX.Element {
  const qc = useQueryClient();

  const controls = useQuery({
    queryKey: ["strategy-controls", "list"],
    queryFn: () => StrategyControlsApi.list(),
    enabled: open,
    staleTime: 30_000,
  });
  const execPlans = useQuery({
    queryKey: ["execution-plans", "list"],
    queryFn: () => ExecutionPlansApi.list(),
    enabled: open,
    staleTime: 30_000,
  });

  const [controlsId, setControlsId] = useState<string>(
    deployment.strategy_controls_version_id ?? "",
  );
  const [execPlanId, setExecPlanId] = useState<string>(
    deployment.execution_plan_version_id ?? "",
  );
  const [effectiveMode, setEffectiveMode] = useState<EffectiveMode>("now");
  const [customDatetime, setCustomDatetime] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setControlsId(deployment.strategy_controls_version_id ?? "");
    setExecPlanId(deployment.execution_plan_version_id ?? "");
    setEffectiveMode("now");
    setCustomDatetime("");
    setError(null);
  }

  function effectiveValue(): string {
    if (effectiveMode === "custom") return customDatetime.trim();
    return effectiveMode;
  }

  const controlsChanged = controlsId !== (deployment.strategy_controls_version_id ?? "");
  const execPlanChanged = execPlanId !== (deployment.execution_plan_version_id ?? "");
  const anyChange = controlsChanged || execPlanChanged;

  const isCustomValid =
    effectiveMode !== "custom" ||
    (customDatetime.trim().length > 0 && !Number.isNaN(Date.parse(customDatetime.trim())));

  const rebind = useMutation({
    mutationFn: () =>
      DeploymentsApi.rebind(deployment.deployment_id, {
        strategy_controls_version_id: controlsChanged && controlsId ? controlsId : undefined,
        execution_plan_version_id: execPlanChanged && execPlanId ? execPlanId : undefined,
        effective: effectiveValue(),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["deployments"] });
      reset();
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const canSubmit = anyChange && isCustomValid;

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Rebind deployment · {deployment.name}</DrawerTitle>
          <DrawerDescription>
            Hot-swap Strategy Controls and/or Execution Plan without stopping the
            deployment. Open positions continue under their original bindings; only
            new candidate orders use the updated configuration.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-4">
          {error ? <Banner severity="danger" title="Rebind failed" message={error} /> : null}

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <Select
                label="Strategy Controls"
                value={controlsId}
                onChange={(e) => setControlsId(e.target.value)}
              >
                <option value="">— use deployment default —</option>
                {(controls.data?.libraries ?? []).map((lib) => (
                  <option
                    key={lib.strategy_controls_id}
                    value={lib.head_version_id ?? ""}
                    disabled={!lib.head_version_id}
                  >
                    {lib.name} v{lib.head_version_number}
                    {lib.is_default ? " (default)" : ""}
                    {lib.retired_at ? " [retired]" : ""}
                  </option>
                ))}
              </Select>
              {deployment.strategy_controls_version_id ? (
                <div className="mt-1 text-[11px] text-fg-muted">
                  Current: {deployment.strategy_controls_version_id.slice(0, 8)}…
                </div>
              ) : (
                <div className="mt-1 text-[11px] text-fg-muted">Currently unbound</div>
              )}
            </div>

            <div>
              <Select
                label="Execution Plan"
                value={execPlanId}
                onChange={(e) => setExecPlanId(e.target.value)}
              >
                <option value="">— use deployment default —</option>
                {(execPlans.data?.libraries ?? []).map((lib) => (
                  <option
                    key={lib.execution_plan_id}
                    value={lib.head_version_id ?? ""}
                    disabled={!lib.head_version_id}
                  >
                    {lib.name} v{lib.head_version_number}
                    {lib.is_default ? " (default)" : ""}
                    {lib.retired_at ? " [retired]" : ""}
                  </option>
                ))}
              </Select>
              {deployment.execution_plan_version_id ? (
                <div className="mt-1 text-[11px] text-fg-muted">
                  Current: {deployment.execution_plan_version_id.slice(0, 8)}…
                </div>
              ) : (
                <div className="mt-1 text-[11px] text-fg-muted">Currently unbound</div>
              )}
            </div>
          </div>

          <div>
            <div className="mb-1 text-xs font-medium text-fg-muted">Effective when</div>
            <div className="flex flex-wrap gap-3">
              {(["now", "next_session", "custom"] as const).map((mode) => (
                <label key={mode} className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="radio"
                    name="effective"
                    value={mode}
                    checked={effectiveMode === mode}
                    onChange={() => setEffectiveMode(mode)}
                  />
                  {mode === "now" ? "Now" : mode === "next_session" ? "Next session" : "Custom"}
                </label>
              ))}
            </div>
            {effectiveMode === "custom" ? (
              <div className="mt-2">
                <TextField
                  label="Effective datetime (ISO 8601)"
                  value={customDatetime}
                  onChange={(e) => setCustomDatetime(e.target.value)}
                  hint="Example: 2026-05-01T09:30:00+00:00"
                />
                {customDatetime.trim().length > 0 &&
                  Number.isNaN(Date.parse(customDatetime.trim())) ? (
                  <div className="mt-1 text-xs text-red-500">Invalid datetime format.</div>
                ) : null}
              </div>
            ) : null}
          </div>

          {!anyChange ? (
            <Banner
              severity="warning"
              title="No changes"
              message="Select a different Controls or Execution Plan version to enable rebind."
            />
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!canSubmit}
            loading={rebind.isPending}
            onClick={() => rebind.mutate()}
          >
            Rebind
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

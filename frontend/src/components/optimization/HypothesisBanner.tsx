import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { WalkForwardApi } from "@/api/researchRuns";
import { WalkForwardRunRequestSchema } from "@/api/schemas/researchRuns";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";

/**
 * HypothesisBanner.
 *
 * Doctrinal warning at the top of every Optimization detail page:
 * "this is curve-fit until WF validates it." One-click "Validate with
 * Walk-Forward" button POSTs the pre-baked follow_up_walk_forward_request
 * payload to the WF endpoint and navigates to the new run.
 */
export function HypothesisBanner({
  walkForwardHandoff,
  onWalkForwardCreated,
}: {
  walkForwardHandoff: Record<string, unknown> | null | undefined;
  onWalkForwardCreated?: (runId: string) => void;
}): JSX.Element {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const handoff = useMutation({
    mutationFn: () => {
      if (!walkForwardHandoff) {
        throw new Error("no walk-forward handoff payload available");
      }
      return WalkForwardApi.create(WalkForwardRunRequestSchema.parse(walkForwardHandoff));
    },
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["walk-forward", "runs"] });
      setError(null);
      onWalkForwardCreated?.((run as { run_id: string }).run_id);
    },
    onError: (err) => setError((err as Error).message),
  });

  return (
    <Banner
      severity="warning"
      title="Hypothesis only — validate with Walk-Forward before deploying"
      message={
        <span>
          Optimization output is the best parameter set on this single window —
          curve-fit until proven otherwise. The recommended workflow is{" "}
          <strong>Backtest → Optimization → Walk-Forward → Sim Lab → Deploy</strong>.
          Skipping Walk-Forward is your call; this banner is the only gate.
          {error ? (
            <span className="mt-2 block text-danger">Walk-Forward handoff failed: {error}</span>
          ) : null}
        </span>
      }
      action={
        walkForwardHandoff ? (
          <Button size="sm" onClick={() => handoff.mutate()} disabled={handoff.isPending}>
            {handoff.isPending ? "Launching…" : "Validate with Walk-Forward →"}
          </Button>
        ) : undefined
      }
    />
  );
}

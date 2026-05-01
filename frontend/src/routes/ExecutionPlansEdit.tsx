import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { ExecutionPlansApi } from "@/api/executionPlans";
import type {
  ExecutionPlanDraft,
  ExecutionPlanLibrary,
  OrderRetryPolicy,
  OrderCancelPolicy,
} from "@/api/schemas/executionPlans";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { TextField } from "@/components/ui/TextField";
import { Select } from "@/components/ui/Select";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { relativeTime } from "@/lib/format";

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.detail || e.message : String(e);
}

function buildDraft(library: ExecutionPlanLibrary): ExecutionPlanDraft {
  const p = library.head.payload;
  return {
    name: p.name,
    entry_order_type: p.entry_order_type,
    exit_order_type: p.exit_order_type,
    time_in_force: p.time_in_force,
    entry_limit_offset_bps: p.entry_limit_offset_bps ?? null,
    cancel_after_bars: p.cancel_after_bars ?? null,
    bracket: p.bracket ?? { enabled: false },
    execution_mode: p.execution_mode,
    trailing_stop_enabled: p.trailing_stop_enabled,
    scale_out_enabled: p.scale_out_enabled,
    order_retry_policy: p.order_retry_policy ?? "none",
    order_cancel_policy: p.order_cancel_policy ?? "hold",
    order_retry_max_attempts: p.order_retry_max_attempts ?? null,
    order_retry_offset_bps: p.order_retry_offset_bps ?? null,
    feature_refs: p.feature_refs ?? [],
    preset: p.preset ?? null,
  };
}

export function ExecutionPlansEdit(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const detail = useQuery({
    queryKey: ["execution-plans", "detail", id],
    queryFn: () => ExecutionPlansApi.get(id!),
    enabled: id != null,
  });

  const usedBy = useQuery({
    queryKey: ["execution-plans", "used-by", id],
    queryFn: () => ExecutionPlansApi.usedBy(id!),
    enabled: id != null,
  });

  const [draft, setDraft] = useState<ExecutionPlanDraft | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (detail.data && !draft) {
      setDraft(buildDraft(detail.data));
    }
  }, [detail.data, draft]);

  const save = useMutation({
    mutationFn: () => {
      if (!id || !draft) throw new Error("Not ready");
      return ExecutionPlansApi.edit(id, draft);
    },
    onSuccess: () => {
      setSaveError(null);
      void qc.invalidateQueries({ queryKey: ["execution-plans"] });
      navigate("/execution-plans");
    },
    onError: (e) => setSaveError(errorText(e)),
  });

  function patch<K extends keyof ExecutionPlanDraft>(
    key: K,
    value: ExecutionPlanDraft[K],
  ): void {
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  if (detail.isLoading || !draft) {
    return <LoadingState title="Loading execution profile" />;
  }
  if (detail.isError) {
    return (
      <ErrorState
        title="Could not load profile"
        detail={(detail.error as Error)?.message}
        onRetry={() => detail.refetch()}
      />
    );
  }

  const library = detail.data!;

  return (
    <div className="mx-auto max-w-5xl space-y-4 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-bold">{library.name}</h1>
          <div className="flex flex-wrap gap-1.5 mt-1">
            <StatusBadge tone="neutral">v{library.head.payload.version}</StatusBadge>
            {library.is_default ? <StatusBadge tone="ok">Default</StatusBadge> : null}
            {library.retired_at ? <StatusBadge tone="muted">Retired</StatusBadge> : null}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={() => navigate("/execution-plans")}>
            Cancel
          </Button>
          <Button
            size="sm"
            variant="primary"
            loading={save.isPending}
            onClick={() => save.mutate()}
          >
            Save (new version)
          </Button>
        </div>
      </div>

      {saveError ? (
        <Banner severity="danger" title="Save failed" message={saveError} />
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1fr_280px]">
        {/* Left: editor sections */}
        <div className="space-y-4">
          {/* Identity */}
          <Card>
            <CardHeader>
              <CardTitle>Identity</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <TextField
                label="Name"
                value={draft.name}
                onChange={(e) => patch("name", e.target.value)}
              />
            </CardBody>
          </Card>

          {/* Entry order shape */}
          <Card>
            <CardHeader>
              <CardTitle>Entry Order Shape</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <Select
                label="Entry order type"
                value={draft.entry_order_type}
                onChange={(e) =>
                  patch(
                    "entry_order_type",
                    e.target.value as ExecutionPlanDraft["entry_order_type"],
                  )
                }
              >
                <option value="market">Market</option>
                <option value="limit">Limit</option>
                <option value="stop">Stop</option>
                <option value="stop_limit">Stop Limit</option>
              </Select>
              <Select
                label="Time in force"
                value={draft.time_in_force}
                onChange={(e) =>
                  patch(
                    "time_in_force",
                    e.target.value as ExecutionPlanDraft["time_in_force"],
                  )
                }
              >
                <option value="day">Day</option>
                <option value="gtc">GTC</option>
                <option value="ioc">IOC</option>
                <option value="fok">FOK</option>
              </Select>
              <TextField
                label="Entry limit offset (bps)"
                type="number"
                value={draft.entry_limit_offset_bps ?? ""}
                onChange={(e) =>
                  patch(
                    "entry_limit_offset_bps",
                    e.target.value ? parseFloat(e.target.value) : null,
                  )
                }
                placeholder="e.g. 5"
              />
              <TextField
                label="Cancel after bars"
                type="number"
                value={draft.cancel_after_bars ?? ""}
                onChange={(e) =>
                  patch(
                    "cancel_after_bars",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 3"
              />
            </CardBody>
          </Card>

          {/* Exit order */}
          <Card>
            <CardHeader>
              <CardTitle>Exit Order</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <Select
                label="Exit order type"
                value={draft.exit_order_type}
                onChange={(e) =>
                  patch(
                    "exit_order_type",
                    e.target.value as ExecutionPlanDraft["exit_order_type"],
                  )
                }
              >
                <option value="market">Market</option>
                <option value="limit">Limit</option>
                <option value="stop">Stop</option>
                <option value="stop_limit">Stop Limit</option>
              </Select>
            </CardBody>
          </Card>

          {/* Bracket placement */}
          <Card>
            <CardHeader>
              <CardTitle>Bracket Placement</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <Select
                label="Execution mode"
                value={draft.execution_mode}
                onChange={(e) =>
                  patch(
                    "execution_mode",
                    e.target.value as ExecutionPlanDraft["execution_mode"],
                  )
                }
              >
                <option value="post_fill_bracket">Post-fill bracket (synthetic OCO)</option>
                <option value="native_alpaca_bracket">Native Alpaca bracket</option>
              </Select>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.bracket.enabled}
                  onChange={(e) =>
                    patch("bracket", { ...draft.bracket, enabled: e.target.checked })
                  }
                />
                Enable bracket
              </label>
              {draft.bracket.enabled ? (
                <>
                  <TextField
                    label="Take profit (R-multiple)"
                    type="number"
                    value={draft.bracket.take_profit_r_multiple ?? ""}
                    onChange={(e) =>
                      patch("bracket", {
                        ...draft.bracket,
                        take_profit_r_multiple: e.target.value
                          ? parseFloat(e.target.value)
                          : null,
                      })
                    }
                    placeholder="e.g. 2.0"
                  />
                  <TextField
                    label="Stop loss (R-multiple)"
                    type="number"
                    value={draft.bracket.stop_loss_r_multiple ?? ""}
                    onChange={(e) =>
                      patch("bracket", {
                        ...draft.bracket,
                        stop_loss_r_multiple: e.target.value
                          ? parseFloat(e.target.value)
                          : null,
                      })
                    }
                    placeholder="e.g. 1.0"
                  />
                </>
              ) : null}
            </CardBody>
          </Card>

          {/* Runner mechanic */}
          <Card>
            <CardHeader>
              <CardTitle>Runner Mechanic</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.trailing_stop_enabled}
                  onChange={(e) => patch("trailing_stop_enabled", e.target.checked)}
                />
                Trailing stop enabled
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.scale_out_enabled}
                  onChange={(e) => patch("scale_out_enabled", e.target.checked)}
                />
                Scale-out enabled
              </label>
            </CardBody>
          </Card>

          {/* Order retry & cancel */}
          <Card>
            <CardHeader>
              <CardTitle>Order Retry &amp; Cancel</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <Select
                label="Order retry policy"
                value={draft.order_retry_policy}
                onChange={(e) =>
                  patch(
                    "order_retry_policy",
                    e.target.value as OrderRetryPolicy,
                  )
                }
              >
                <option value="none">None (no retry)</option>
                <option value="reprice_once">Reprice once</option>
                <option value="reprice_until_filled">Reprice until filled</option>
              </Select>
              <Select
                label="Order cancel policy"
                value={draft.order_cancel_policy}
                onChange={(e) =>
                  patch(
                    "order_cancel_policy",
                    e.target.value as OrderCancelPolicy,
                  )
                }
              >
                <option value="hold">Hold (keep working)</option>
                <option value="cancel_on_opposite_signal">Cancel on opposite signal</option>
                <option value="cancel_after_bars">Cancel after bars</option>
              </Select>
              {draft.order_retry_policy !== "none" ? (
                <>
                  <TextField
                    label="Max retry attempts"
                    type="number"
                    value={draft.order_retry_max_attempts ?? ""}
                    onChange={(e) =>
                      patch(
                        "order_retry_max_attempts",
                        e.target.value ? parseInt(e.target.value, 10) : null,
                      )
                    }
                    placeholder="e.g. 3"
                  />
                  <TextField
                    label="Retry offset (bps)"
                    type="number"
                    value={draft.order_retry_offset_bps ?? ""}
                    onChange={(e) =>
                      patch(
                        "order_retry_offset_bps",
                        e.target.value ? parseFloat(e.target.value) : null,
                      )
                    }
                    placeholder="e.g. 5"
                  />
                </>
              ) : null}
            </CardBody>
          </Card>

          {/* Feature refs */}
          <Card>
            <CardHeader>
              <CardTitle>Feature Refs</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <TextField
                label="Feature refs (comma-separated)"
                value={draft.feature_refs.join(", ")}
                onChange={(e) =>
                  patch(
                    "feature_refs",
                    e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  )
                }
                placeholder="e.g. 5m.ema(9), 1d.vix_close"
              />
            </CardBody>
          </Card>
        </div>

        {/* Right rail */}
        <div className="space-y-4">
          {/* Ownership reference panel */}
          <Card>
            <CardHeader>
              <CardTitle>What this profile owns</CardTitle>
            </CardHeader>
            <CardBody>
              <ul className="space-y-1 text-xs text-fg-muted">
                <li className="font-medium text-fg">Owns:</li>
                <li>Entry order type &amp; time-in-force</li>
                <li>Bracket placement mode &amp; R-multiples</li>
                <li>Runner / scale-out flags</li>
                <li>Slippage &amp; fill handling</li>
                <li className="mt-2 font-medium text-fg">Does NOT own:</li>
                <li>Entry conditions (StrategyVersion)</li>
                <li>Stops as logic (StrategyVersion)</li>
                <li>Leg sizing (StrategyVersion)</li>
                <li>Session &amp; timing rules (StrategyControls)</li>
              </ul>
            </CardBody>
          </Card>

          {/* Where this is used */}
          <Card>
            <CardHeader>
              <CardTitle>Where this is used</CardTitle>
              <StatusBadge tone="neutral">
                {usedBy.data?.deployment_ids.length ?? 0}
              </StatusBadge>
            </CardHeader>
            <CardBody>
              {usedBy.isLoading ? (
                <div className="text-xs text-fg-muted">Loading...</div>
              ) : usedBy.data && usedBy.data.deployment_ids.length > 0 ? (
                <ul className="space-y-1">
                  {usedBy.data.deployment_ids.map((did) => (
                    <li key={did} className="text-xs font-mono text-fg-muted">
                      {did}
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="text-xs text-fg-muted">Not bound to any deployment.</div>
              )}
            </CardBody>
          </Card>

          {/* Version history */}
          <Card>
            <CardHeader>
              <CardTitle>Version history</CardTitle>
            </CardHeader>
            <CardBody className="p-0">
              <table className="ut-table">
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Saved</th>
                  </tr>
                </thead>
                <tbody>
                  {[...library.history].reverse().map((h) => (
                    <tr key={h.version_id}>
                      <td className="tabular">v{h.version}</td>
                      <td className="text-fg-muted text-xs">{relativeTime(h.saved_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { StrategyControlsApi } from "@/api/strategyControls";
import type {
  StrategyControlsDraft,
  StrategyControlsLibrary,
  Weekday,
} from "@/api/schemas/strategyControls";
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

const ALL_WEEKDAYS: Weekday[] = ["MON", "TUE", "WED", "THU", "FRI"];
const WEEKDAY_LABELS: Record<Weekday, string> = {
  MON: "Mon",
  TUE: "Tue",
  WED: "Wed",
  THU: "Thu",
  FRI: "Fri",
};

function buildDraft(library: StrategyControlsLibrary): StrategyControlsDraft {
  const p = library.head.payload;
  return {
    name: p.name,
    timeframe: p.timeframe,
    allowed_directions: p.allowed_directions,
    higher_timeframe_confirmation_required: p.higher_timeframe_confirmation_required,
    session_preference: p.session_preference,
    session_windows: p.session_windows ?? [],
    avoid_first_minutes: p.avoid_first_minutes ?? null,
    no_new_entries_after: p.no_new_entries_after ?? null,
    force_flat_by: p.force_flat_by ?? null,
    time_based_exit_after_bars: p.time_based_exit_after_bars ?? null,
    time_based_exit_after_minutes: p.time_based_exit_after_minutes ?? null,
    time_based_exit_after_days: p.time_based_exit_after_days ?? null,
    cooldown_bars: p.cooldown_bars ?? null,
    cooldown_minutes: p.cooldown_minutes ?? null,
    max_trades_per_session: p.max_trades_per_session ?? null,
    max_trades_per_day: p.max_trades_per_day ?? null,
    earnings_news_blackout_enabled: p.earnings_news_blackout_enabled,
    max_consecutive_losses_halt: p.max_consecutive_losses_halt ?? null,
    skip_power_hour: p.skip_power_hour ?? false,
    day_of_week_restrictions: (p.day_of_week_restrictions ?? []) as Weekday[],
    feature_refs: p.feature_refs ?? [],
    regime_filter_refs: p.regime_filter_refs ?? [],
  };
}

export function StrategyControlsEdit(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const detail = useQuery({
    queryKey: ["strategy-controls", "detail", id],
    queryFn: () => StrategyControlsApi.get(id!),
    enabled: id != null,
  });

  const usedBy = useQuery({
    queryKey: ["strategy-controls", "used-by", id],
    queryFn: () => StrategyControlsApi.usedBy(id!),
    enabled: id != null,
  });

  const [draft, setDraft] = useState<StrategyControlsDraft | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (detail.data && !draft) {
      setDraft(buildDraft(detail.data));
    }
  }, [detail.data, draft]);

  const save = useMutation({
    mutationFn: () => {
      if (!id || !draft) throw new Error("Not ready");
      return StrategyControlsApi.edit(id, draft);
    },
    onSuccess: () => {
      setSaveError(null);
      void qc.invalidateQueries({ queryKey: ["strategy-controls"] });
      navigate("/controls");
    },
    onError: (e) => setSaveError(errorText(e)),
  });

  function patch<K extends keyof StrategyControlsDraft>(
    key: K,
    value: StrategyControlsDraft[K],
  ): void {
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  if (detail.isLoading || !draft) {
    return <LoadingState title="Loading controls library" />;
  }
  if (detail.isError) {
    return (
      <ErrorState
        title="Could not load library"
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
          <Button size="sm" variant="ghost" onClick={() => navigate("/controls")}>
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
              <TextField
                label="Timeframe"
                value={draft.timeframe}
                onChange={(e) => patch("timeframe", e.target.value)}
                placeholder="5m"
              />
            </CardBody>
          </Card>

          {/* Session window */}
          <Card>
            <CardHeader>
              <CardTitle>Session Window</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <Select
                label="Allowed directions"
                value={draft.allowed_directions}
                onChange={(e) =>
                  patch(
                    "allowed_directions",
                    e.target.value as StrategyControlsDraft["allowed_directions"],
                  )
                }
              >
                <option value="long">Long only</option>
                <option value="short">Short only</option>
                <option value="both">Both</option>
              </Select>
              <Select
                label="Session preference"
                value={draft.session_preference}
                onChange={(e) =>
                  patch(
                    "session_preference",
                    e.target.value as StrategyControlsDraft["session_preference"],
                  )
                }
              >
                <option value="regular_only">Regular only</option>
                <option value="regular_and_extended">Regular + extended</option>
              </Select>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.higher_timeframe_confirmation_required}
                  onChange={(e) =>
                    patch("higher_timeframe_confirmation_required", e.target.checked)
                  }
                />
                Higher timeframe confirmation required
              </label>
              <TextField
                label="Avoid first N minutes"
                type="number"
                value={draft.avoid_first_minutes ?? ""}
                onChange={(e) =>
                  patch(
                    "avoid_first_minutes",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 15"
              />
              <TextField
                label="No new entries after (HH:MM:SS)"
                value={draft.no_new_entries_after ?? ""}
                onChange={(e) =>
                  patch("no_new_entries_after", e.target.value || null)
                }
                placeholder="15:30:00"
              />
              <TextField
                label="Force flat by (HH:MM:SS)"
                value={draft.force_flat_by ?? ""}
                onChange={(e) =>
                  patch("force_flat_by", e.target.value || null)
                }
                placeholder="16:00:00"
              />
            </CardBody>
          </Card>

          {/* Time-based exit */}
          <Card>
            <CardHeader>
              <CardTitle>Time-Based Exit</CardTitle>
              <span className="text-xs text-fg-muted">At most one of bars / minutes / days</span>
            </CardHeader>
            <CardBody className="space-y-3">
              <TextField
                label="Exit after bars"
                type="number"
                value={draft.time_based_exit_after_bars ?? ""}
                onChange={(e) =>
                  patch(
                    "time_based_exit_after_bars",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 10"
              />
              <TextField
                label="Exit after minutes"
                type="number"
                value={draft.time_based_exit_after_minutes ?? ""}
                onChange={(e) =>
                  patch(
                    "time_based_exit_after_minutes",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 60"
              />
              <TextField
                label="Exit after days"
                type="number"
                value={draft.time_based_exit_after_days ?? ""}
                onChange={(e) =>
                  patch(
                    "time_based_exit_after_days",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 5"
              />
            </CardBody>
          </Card>

          {/* Cooldowns */}
          <Card>
            <CardHeader>
              <CardTitle>Cooldowns</CardTitle>
              <span className="text-xs text-fg-muted">At most one of bars / minutes</span>
            </CardHeader>
            <CardBody className="space-y-3">
              <TextField
                label="Cooldown bars"
                type="number"
                value={draft.cooldown_bars ?? ""}
                onChange={(e) =>
                  patch(
                    "cooldown_bars",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 3"
              />
              <TextField
                label="Cooldown minutes"
                type="number"
                value={draft.cooldown_minutes ?? ""}
                onChange={(e) =>
                  patch(
                    "cooldown_minutes",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 15"
              />
            </CardBody>
          </Card>

          {/* Concurrency & caps */}
          <Card>
            <CardHeader>
              <CardTitle>Concurrency &amp; Caps</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <TextField
                label="Max trades per session"
                type="number"
                value={draft.max_trades_per_session ?? ""}
                onChange={(e) =>
                  patch(
                    "max_trades_per_session",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 3"
              />
              <TextField
                label="Max trades per day"
                type="number"
                value={draft.max_trades_per_day ?? ""}
                onChange={(e) =>
                  patch(
                    "max_trades_per_day",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 6"
              />
              <TextField
                label="Max consecutive losses before halt"
                type="number"
                value={draft.max_consecutive_losses_halt ?? ""}
                onChange={(e) =>
                  patch(
                    "max_consecutive_losses_halt",
                    e.target.value ? parseInt(e.target.value, 10) : null,
                  )
                }
                placeholder="e.g. 3 (leave blank to disable)"
              />
            </CardBody>
          </Card>

          {/* Trading day filters */}
          <Card>
            <CardHeader>
              <CardTitle>Trading Day Filters</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.skip_power_hour}
                  onChange={(e) => patch("skip_power_hour", e.target.checked)}
                />
                Skip power hour (15:00–16:00)
              </label>
              <fieldset>
                <legend className="text-sm font-medium text-fg mb-1">
                  Days to skip (deny-list; unchecked = allowed)
                </legend>
                <div className="flex flex-wrap gap-3">
                  {ALL_WEEKDAYS.map((day) => (
                    <label key={day} className="flex items-center gap-1 text-sm">
                      <input
                        type="checkbox"
                        checked={(draft.day_of_week_restrictions ?? []).includes(day)}
                        onChange={(e) => {
                          const current = draft.day_of_week_restrictions ?? [];
                          const next = e.target.checked
                            ? [...current, day]
                            : current.filter((d) => d !== day);
                          patch("day_of_week_restrictions", next as Weekday[]);
                        }}
                      />
                      {WEEKDAY_LABELS[day]}
                    </label>
                  ))}
                </div>
              </fieldset>
            </CardBody>
          </Card>

          {/* Earnings/news blackout */}
          <Card>
            <CardHeader>
              <CardTitle>Earnings / News Blackout</CardTitle>
            </CardHeader>
            <CardBody>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.earnings_news_blackout_enabled}
                  onChange={(e) =>
                    patch("earnings_news_blackout_enabled", e.target.checked)
                  }
                />
                Enable earnings and news blackout
              </label>
            </CardBody>
          </Card>

          {/* Regime filter */}
          <Card>
            <CardHeader>
              <CardTitle>Regime Filter</CardTitle>
            </CardHeader>
            <CardBody className="space-y-3">
              <TextField
                label="Regime filter refs (comma-separated)"
                value={draft.regime_filter_refs.join(", ")}
                onChange={(e) =>
                  patch(
                    "regime_filter_refs",
                    e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  )
                }
                placeholder="e.g. regime.bull, regime.neutral"
              />
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

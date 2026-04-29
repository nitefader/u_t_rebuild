import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, CalendarClock, History, Pause, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { ApiError } from "@/api/client";
import { DiscoverySchedulesApi } from "@/api/discoverySchedules";
import type {
  DiscoverySchedule,
  DiscoveryScheduleCadence,
  DiscoveryScheduleExecution,
  DiscoveryScheduleWriteRequest,
} from "@/api/schemas/discoverySchedules";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
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
import { StatusBadge } from "@/components/badges/StatusBadge";
import { formatTimestamp, relativeTime } from "@/lib/format";

type Target =
  | {
      targetKind: "screener_run";
      targetName: string;
      screenerId: string;
      screenerVersionId: string;
      watchlistId?: never;
    }
  | {
      targetKind: "watchlist_refresh";
      targetName: string;
      watchlistId: string;
      screenerId?: never;
      screenerVersionId?: never;
    };

export function DiscoveryScheduleControls(props: Target): JSX.Element {
  const qc = useQueryClient();
  const schedulesQuery = useQuery({
    queryKey: ["discovery-schedules", "list"],
    queryFn: () => DiscoverySchedulesApi.list(),
    refetchInterval: 15_000,
  });
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<DiscoverySchedule | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const schedules = useMemo(() => {
    const all = schedulesQuery.data?.schedules ?? [];
    return all.filter((schedule) => {
      if (props.targetKind === "screener_run") {
        return (
          schedule.target_kind === "screener_run" &&
          schedule.screener_id === props.screenerId &&
          schedule.screener_version_id === props.screenerVersionId
        );
      }
      return schedule.target_kind === "watchlist_refresh" && schedule.watchlist_id === props.watchlistId;
    });
  }, [
    props.targetKind,
    props.screenerId,
    props.screenerVersionId,
    props.watchlistId,
    schedulesQuery.data?.schedules,
  ]);

  const runNow = useMutation({
    mutationFn: (scheduleId: string) => DiscoverySchedulesApi.runNow(scheduleId),
    onSuccess: () => {
      setActionError(null);
      invalidate(qc);
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const pause = useMutation({
    mutationFn: (scheduleId: string) => DiscoverySchedulesApi.pause(scheduleId),
    onSuccess: () => {
      setActionError(null);
      invalidate(qc);
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const resume = useMutation({
    mutationFn: (scheduleId: string) => DiscoverySchedulesApi.resume(scheduleId),
    onSuccess: () => {
      setActionError(null);
      invalidate(qc);
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const archive = useMutation({
    mutationFn: (scheduleId: string) => DiscoverySchedulesApi.archive(scheduleId),
    onSuccess: () => {
      setActionError(null);
      invalidate(qc);
    },
    onError: (e) => setActionError(errorText(e)),
  });
  const remove = useMutation({
    mutationFn: (scheduleId: string) => DiscoverySchedulesApi.delete(scheduleId),
    onSuccess: () => {
      setActionError(null);
      invalidate(qc);
    },
    onError: (e) => setActionError(errorText(e)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="h-4 w-4 text-accent" aria-hidden="true" />
          Schedules
        </CardTitle>
        <Button
          size="sm"
          variant="secondary"
          leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={() => {
            setEditing(null);
            setDrawerOpen(true);
          }}
        >
          New schedule
        </Button>
      </CardHeader>
      <CardBody className="space-y-2">
        {actionError ? <Banner severity="danger" title="Schedule action failed" message={actionError} /> : null}
        {schedules.length === 0 ? (
          <div className="rounded border border-dashed border-border px-3 py-2 text-[11px] text-fg-muted">
            No schedules for {props.targetName}.
          </div>
        ) : (
          schedules.map((schedule) => (
            <div key={schedule.schedule_id} className="rounded border border-border bg-bg-inset/40 px-3 py-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium">{schedule.name}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <StatusBadge tone={schedule.status === "active" ? "ok" : schedule.status === "paused" ? "warn" : "muted"} size="sm">
                      {schedule.status}
                    </StatusBadge>
                    <StatusBadge tone="neutral" size="sm">
                      {cadenceText(schedule)}
                    </StatusBadge>
                    <StatusBadge tone={schedule.approval_policy === "auto_snapshot" ? "warn" : "info"} size="sm">
                      {schedule.approval_policy === "auto_snapshot" ? "auto snapshot" : "operator review"}
                    </StatusBadge>
                  </div>
                  <div className="mt-1 text-[11px] text-fg-muted">
                    Last: {schedule.last_attempt_at ? relativeTime(schedule.last_attempt_at) : "never"} / Next:{" "}
                    {schedule.next_run_at ? formatTimestamp(schedule.next_run_at) : "-"}
                  </div>
                  <div className="mt-1 text-[11px] text-fg-muted">
                    Timezone: {readableTimezone(schedule.timezone_name)}
                  </div>
                  <div className="mt-1 text-[11px] text-fg-muted">
                    Days: {weekdaysText(schedule.weekdays)}
                  </div>
                  {schedule.last_error ? (
                    <div className="mt-1 text-[11px] text-danger">{schedule.last_error}</div>
                  ) : null}
                </div>
                <div className="flex flex-wrap justify-end gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
                    loading={runNow.isPending}
                    onClick={() => runNow.mutate(schedule.schedule_id)}
                    disabled={schedule.status === "archived"}
                  >
                    Run schedule now
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    leftIcon={<Pencil className="h-3.5 w-3.5" aria-hidden="true" />}
                    onClick={() => {
                      setEditing(schedule);
                      setDrawerOpen(true);
                    }}
                    disabled={schedule.status === "archived"}
                  >
                    Edit
                  </Button>
                  {schedule.status === "active" ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      leftIcon={<Pause className="h-3.5 w-3.5" aria-hidden="true" />}
                      loading={pause.isPending}
                      onClick={() => pause.mutate(schedule.schedule_id)}
                    >
                      Pause
                    </Button>
                  ) : schedule.status === "paused" ? (
                    <Button size="sm" variant="ghost" loading={resume.isPending} onClick={() => resume.mutate(schedule.schedule_id)}>
                      Resume
                    </Button>
                  ) : null}
                  {schedule.execution_count === 0 ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      leftIcon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />}
                      loading={remove.isPending}
                      onClick={() => remove.mutate(schedule.schedule_id)}
                    >
                      Delete
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="ghost"
                      leftIcon={<Archive className="h-3.5 w-3.5" aria-hidden="true" />}
                      loading={archive.isPending}
                      onClick={() => archive.mutate(schedule.schedule_id)}
                      disabled={schedule.status === "archived"}
                    >
                      Archive
                    </Button>
                  )}
                </div>
              </div>
              <ScheduleExecutionHistory schedule={schedule} />
            </div>
          ))
        )}
      </CardBody>
      <ScheduleDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        target={props}
        editing={editing}
        onSaved={() => {
          setEditing(null);
          invalidate(qc);
        }}
      />
    </Card>
  );
}

function ScheduleDrawer({
  open,
  onOpenChange,
  target,
  editing,
  onSaved,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  target: Target;
  editing: DiscoverySchedule | null;
  onSaved: () => void;
}): JSX.Element {
  const [form, setForm] = useState<DiscoveryScheduleWriteRequest>(() => defaultForm(target));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setForm(editing ? formFromSchedule(editing) : defaultForm(target));
  }, [
    open,
    editing,
    target.targetKind,
    target.targetName,
    target.screenerId,
    target.screenerVersionId,
    target.watchlistId,
  ]);

  const save = useMutation({
    mutationFn: () => {
      if (editing) {
        return DiscoverySchedulesApi.patch(editing.schedule_id, {
          name: form.name,
          cadence: form.cadence,
          interval_minutes: form.interval_minutes ?? null,
          time_of_day: form.time_of_day ?? null,
          weekdays: form.weekdays,
          timezone_name: form.timezone_name,
          session_start: form.session_start ?? null,
          session_end: form.session_end ?? null,
          approval_policy: form.approval_policy,
          enabled: form.enabled,
        });
      }
      return DiscoverySchedulesApi.create(form);
    },
    onSuccess: () => {
      onSaved();
      onOpenChange(false);
    },
    onError: (e) => setError(errorText(e)),
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-w-xl">
        <DrawerHeader>
          <DrawerTitle>{editing ? "Edit schedule" : "New schedule"}</DrawerTitle>
          <DrawerDescription>
            {target.targetKind === "screener_run"
              ? "Runs this exact Screener version and stores immutable discovery evidence."
              : "Refreshes this Watchlist as entry-universe evidence only."}
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not save schedule" message={error} /> : null}
          <TextField label="Schedule name" value={form.name} onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))} />
          <Select
            label="Cadence"
            value={form.cadence}
            onChange={(e) => {
              const cadence = e.target.value as DiscoveryScheduleCadence;
              setForm((prev) => ({
                ...prev,
                cadence,
                interval_minutes: cadence === "every_n_minutes" ? prev.interval_minutes ?? 15 : prev.interval_minutes,
              }));
            }}
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="every_n_minutes">Every N minutes</option>
          </Select>
          {form.cadence === "every_n_minutes" ? (
            <TextField
              label="Interval minutes"
              type="number"
              value={String(form.interval_minutes ?? 15)}
              onChange={(e) => setForm((prev) => ({ ...prev, interval_minutes: Number(e.target.value || 15) }))}
            />
          ) : (
            <TextField
              label="Time of day"
              value={form.time_of_day ?? "09:15"}
              onChange={(e) => setForm((prev) => ({ ...prev, time_of_day: e.target.value }))}
              placeholder="09:15"
            />
          )}
          <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
            <TextField
              label="Session start"
              value={form.session_start ?? ""}
              onChange={(e) => setForm((prev) => ({ ...prev, session_start: e.target.value || null }))}
              placeholder="04:00"
            />
            <TextField
              label="Session end"
              value={form.session_end ?? ""}
              onChange={(e) => setForm((prev) => ({ ...prev, session_end: e.target.value || null }))}
              placeholder="10:30"
            />
          </div>
          <TextField
            label="Timezone"
            value={form.timezone_name}
            onChange={(e) => setForm((prev) => ({ ...prev, timezone_name: e.target.value || "America/New_York" }))}
            placeholder="America/New_York"
          />
          <WeekdayPicker
            value={form.weekdays}
            onChange={(weekdays) => setForm((prev) => ({ ...prev, weekdays }))}
          />
          {target.targetKind === "watchlist_refresh" ? (
            <Select
              label="Approval policy"
              value={form.approval_policy}
              onChange={(e) =>
                setForm((prev) => ({
                  ...prev,
                  approval_policy: e.target.value as DiscoveryScheduleWriteRequest["approval_policy"],
                }))
              }
            >
              <option value="operator_review">Operator review when active deployments reference it</option>
              <option value="auto_snapshot">Auto snapshot, auditable</option>
            </Select>
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" loading={save.isPending} disabled={!form.name.trim()} onClick={() => save.mutate()}>
            Save schedule
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function ScheduleExecutionHistory({ schedule }: { schedule: DiscoverySchedule }): JSX.Element {
  const executionsQuery = useQuery({
    queryKey: ["discovery-schedules", "executions", schedule.schedule_id],
    queryFn: () => DiscoverySchedulesApi.executions(schedule.schedule_id),
    enabled: schedule.execution_count > 0,
    refetchInterval: schedule.status === "active" ? 15_000 : false,
  });
  const executions = executionsQuery.data?.executions ?? [];
  if (schedule.execution_count === 0) {
    return (
      <div className="mt-2 border-t border-border pt-2 text-[11px] text-fg-muted">
        Execution history: no runs yet.
      </div>
    );
  }
  return (
    <div className="mt-2 border-t border-border pt-2">
      <div className="mb-1 flex items-center gap-1 text-[11px] font-medium text-fg-muted">
        <History className="h-3.5 w-3.5" aria-hidden="true" />
        Execution history
      </div>
      {executionsQuery.isError ? (
        <div className="text-[11px] text-danger">Could not load schedule execution history.</div>
      ) : executions.length === 0 ? (
        <div className="text-[11px] text-fg-muted">Loading execution history...</div>
      ) : (
        <div className="space-y-1">
          {executions.slice(0, 3).map((execution) => (
            <ExecutionRow key={execution.execution_id} execution={execution} />
          ))}
        </div>
      )}
    </div>
  );
}

function ExecutionRow({ execution }: { execution: DiscoveryScheduleExecution }): JSX.Element {
  return (
    <div className="rounded border border-border/70 bg-bg px-2 py-1.5 text-[11px]">
      <div className="flex flex-wrap items-center justify-between gap-1">
        <div className="flex flex-wrap items-center gap-1">
          <StatusBadge tone={executionTone(execution.status)} size="sm">
            {execution.status}
          </StatusBadge>
          <span className="text-fg-muted">
            {execution.trigger === "run_now" ? "Run now" : "Scheduled"} at {formatTimestamp(execution.started_at)}
          </span>
        </div>
        <span className="text-fg-subtle" title={executionDebugId(execution)}>
          {executionTargetLabel(execution)}
        </span>
      </div>
      {execution.watchlist_snapshot_id ? (
        <div className="mt-1 text-fg-muted">
          Snapshot diff: +{execution.added_symbols.length} / -{execution.removed_symbols.length} / =
          {execution.stayed_symbols.length}
        </div>
      ) : null}
      {execution.error ? <div className="mt-1 text-danger">{execution.error}</div> : null}
    </div>
  );
}

function defaultForm(target: Target): DiscoveryScheduleWriteRequest {
  const base = {
    name: `${target.targetName} schedule`,
    cadence: "daily" as const,
    interval_minutes: null,
    time_of_day: "09:15",
    weekdays: [0, 1, 2, 3, 4],
    timezone_name: "America/New_York",
    session_start: null,
    session_end: null,
    approval_policy: "operator_review" as const,
    enabled: true,
  };
  if (target.targetKind === "screener_run") {
    return {
      ...base,
      target_kind: "screener_run",
      screener_id: target.screenerId,
      screener_version_id: target.screenerVersionId,
      watchlist_id: null,
    };
  }
  return {
    ...base,
    target_kind: "watchlist_refresh",
    screener_id: null,
    screener_version_id: null,
    watchlist_id: target.watchlistId,
  };
}

function formFromSchedule(schedule: DiscoverySchedule): DiscoveryScheduleWriteRequest {
  return {
    name: schedule.name,
    target_kind: schedule.target_kind,
    screener_id: schedule.screener_id ?? null,
    screener_version_id: schedule.screener_version_id ?? null,
    watchlist_id: schedule.watchlist_id ?? null,
    cadence: schedule.cadence,
    interval_minutes: schedule.interval_minutes ?? null,
    time_of_day: schedule.time_of_day ?? null,
    weekdays: schedule.weekdays,
    timezone_name: schedule.timezone_name,
    session_start: schedule.session_start ?? null,
    session_end: schedule.session_end ?? null,
    approval_policy: schedule.approval_policy,
    enabled: schedule.enabled,
  };
}

function cadenceText(schedule: DiscoverySchedule): string {
  if (schedule.cadence === "every_n_minutes") return `every ${schedule.interval_minutes ?? "?"}m`;
  if (schedule.cadence === "weekly") return `weekly ${schedule.time_of_day ?? ""}`;
  return `daily ${schedule.time_of_day ?? ""}`;
}

const WEEKDAYS = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
];

function WeekdayPicker({
  value,
  onChange,
}: {
  value: number[];
  onChange: (weekdays: number[]) => void;
}): JSX.Element {
  const selected = new Set(value);
  function toggle(day: number): void {
    const next = selected.has(day)
      ? value.filter((item) => item !== day)
      : [...value, day].sort((a, b) => a - b);
    onChange(next.length ? next : [day]);
  }
  return (
    <div>
      <div className="mb-1 text-xs text-fg-muted">Weekdays</div>
      <div className="flex flex-wrap gap-1">
        {WEEKDAYS.map((day) => {
          const active = selected.has(day.value);
          return (
            <button
              key={day.value}
              type="button"
              onClick={() => toggle(day.value)}
              className={
                active
                  ? "rounded border border-accent bg-accent/20 px-2 py-1 text-xs text-accent"
                  : "rounded border border-border bg-bg-raised px-2 py-1 text-xs text-fg-muted hover:text-fg"
              }
            >
              {day.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function weekdaysText(value: number[]): string {
  const normalized = [...new Set(value)].sort((a, b) => a - b);
  const key = normalized.join(",");
  if (key === "0,1,2,3,4") return "Mon-Fri";
  if (key === "0,1,2,3,4,5,6") return "Every day";
  return normalized
    .map((day) => WEEKDAYS.find((item) => item.value === day)?.label)
    .filter(Boolean)
    .join(", ");
}

function executionTone(status: DiscoveryScheduleExecution["status"]): "ok" | "warn" | "danger" | "info" | "muted" {
  if (status === "completed") return "ok";
  if (status === "blocked") return "warn";
  if (status === "failed") return "danger";
  return "info";
}

function executionTargetLabel(execution: DiscoveryScheduleExecution): string {
  if (execution.screener_run_id) return "Screener run evidence recorded";
  if (execution.watchlist_snapshot_id) return "Watchlist snapshot recorded";
  return execution.target_kind === "screener_run" ? "Screener run evidence pending" : "Watchlist snapshot pending";
}

function executionDebugId(execution: DiscoveryScheduleExecution): string | undefined {
  if (execution.screener_run_id) return `Screener run id: ${execution.screener_run_id}`;
  if (execution.watchlist_snapshot_id) return `Watchlist snapshot id: ${execution.watchlist_snapshot_id}`;
  return undefined;
}

function readableTimezone(value: string): string {
  return value === "America/New_York" ? "America/New_York (market time)" : value;
}

function invalidate(qc: ReturnType<typeof useQueryClient>): void {
  void qc.invalidateQueries({ queryKey: ["discovery-schedules"] });
  void qc.invalidateQueries({ queryKey: ["screeners"] });
  void qc.invalidateQueries({ queryKey: ["watchlists"] });
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.detail || e.message : String(e);
}

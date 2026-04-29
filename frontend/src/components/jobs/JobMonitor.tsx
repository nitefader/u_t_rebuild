import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, X } from "lucide-react";
import { ResearchJobsApi } from "@/api/researchJobs";
import type { ResearchJobSummary } from "@/api/schemas/researchJobs";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/badges/StatusBadge";

/**
 * JobMonitor.
 *
 * Compact pulse-dot + counter that lives in each research page's header.
 * Click expands a popover listing active + recent jobs with their progress
 * bars, links to result runs when complete, and per-job cancel buttons.
 *
 * Polls every 2s when active jobs are present; backs off to 15s when
 * everything is terminal so we don't spam the backend.
 */
export function JobMonitor({ kind }: { kind?: "backtest" | "walk_forward" | "optimization" }): JSX.Element {
  const [open, setOpen] = useState(false);
  const queryClient = useQueryClient();
  const list = useQuery({
    queryKey: ["research-jobs", kind ?? "all"],
    queryFn: () => ResearchJobsApi.list({ kind, limit: 25 }),
    refetchInterval: (query) => {
      const data = query.state.data as { jobs?: ResearchJobSummary[] } | undefined;
      const active = (data?.jobs ?? []).some(
        (j) => j.status === "queued" || j.status === "running",
      );
      return active ? 2_000 : 15_000;
    },
  });

  const cancel = useMutation({
    mutationFn: (jobId: string) => ResearchJobsApi.cancel(jobId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["research-jobs", kind ?? "all"] }),
  });

  const jobs = list.data?.jobs ?? [];
  const counts = useMemo(() => {
    const acc = { queued: 0, running: 0, completed: 0, failed: 0, canceled: 0 };
    for (const j of jobs) {
      const k = j.status as keyof typeof acc;
      if (k in acc) acc[k] += 1;
    }
    return acc;
  }, [jobs]);
  const activeCount = counts.queued + counts.running;

  return (
    <div className="relative">
      <Button
        size="sm"
        variant={activeCount > 0 ? "primary" : "ghost"}
        leftIcon={<Activity className={`h-3.5 w-3.5 ${activeCount > 0 ? "animate-pulse" : ""}`} aria-hidden="true" />}
        onClick={() => setOpen(!open)}
        title={activeCount > 0 ? `${activeCount} active job(s)` : "Recent research jobs"}
      >
        Jobs {activeCount > 0 ? `· ${activeCount}` : ""}
      </Button>
      {open ? (
        <div className="absolute right-0 z-30 mt-2 w-[420px] rounded border border-border bg-bg-elevated shadow-lg">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-xs font-semibold">
              Research jobs
              {kind ? <span className="ml-2 text-fg-muted">· {kind.replace("_", " ")}</span> : null}
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-fg-muted hover:text-fg"
              aria-label="Close"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <div className="max-h-[60vh] overflow-y-auto p-2">
            {list.isLoading ? (
              <div className="p-3 text-xs text-fg-muted">Loading…</div>
            ) : null}
            {!list.isLoading && jobs.length === 0 ? (
              <div className="p-3 text-xs text-fg-muted">
                No research jobs yet. Run a backtest, walk-forward, or optimization to see
                progress here.
              </div>
            ) : null}
            <ul className="space-y-2">
              {jobs.map((job) => (
                <JobRow key={job.job_id} job={job} onCancel={() => cancel.mutate(job.job_id)} />
              ))}
            </ul>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function JobRow({
  job,
  onCancel,
}: {
  job: ResearchJobSummary;
  onCancel: () => void;
}): JSX.Element {
  const tone = statusTone(job.status);
  const isActive = job.status === "queued" || job.status === "running";
  const pct = job.progress_total > 0 ? Math.min(100, (job.progress_current / job.progress_total) * 100) : 0;
  return (
    <li className="rounded border border-border p-2 text-xs">
      <div className="mb-1 flex items-center gap-2">
        <StatusBadge tone={tone}>{job.status}</StatusBadge>
        <span className="font-mono text-[10px] text-fg-muted">{job.kind}</span>
        <span className="ml-auto text-[10px] text-fg-subtle" title={job.created_at}>
          {fmtRel(job.created_at)}
        </span>
      </div>
      <div className="mb-1 text-fg-muted">
        {job.progress_label || "—"}
        {job.progress_total > 0
          ? ` · ${job.progress_current} / ${job.progress_total}`
          : ""}
      </div>
      <div className="h-1.5 w-full rounded bg-bg-inset overflow-hidden">
        <div
          className={`h-full ${progressBg(job.status)}`}
          style={{ width: isActive ? `${pct}%` : "100%" }}
        />
      </div>
      {job.error ? (
        <div className="mt-1 text-[10px] text-danger break-all">{job.error}</div>
      ) : null}
      <div className="mt-2 flex items-center justify-between">
        <span className="text-[10px] font-mono text-fg-subtle">{job.job_id.slice(0, 8)}</span>
        {isActive ? (
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : job.result_run_id ? (
          <span className="text-[10px] text-fg-muted">→ run {job.result_run_id.slice(0, 8)}</span>
        ) : null}
      </div>
    </li>
  );
}

function statusTone(status: string): "ok" | "warn" | "danger" | "info" | "muted" {
  switch (status) {
    case "completed":
      return "ok";
    case "running":
      return "info";
    case "queued":
      return "warn";
    case "failed":
      return "danger";
    case "canceled":
      return "muted";
    default:
      return "muted";
  }
}

function progressBg(status: string): string {
  switch (status) {
    case "completed":
      return "bg-ok";
    case "running":
      return "bg-info animate-pulse";
    case "queued":
      return "bg-warn";
    case "failed":
      return "bg-danger";
    case "canceled":
      return "bg-fg-muted";
    default:
      return "bg-fg-muted";
  }
}

function fmtRel(iso: string): string {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return iso;
  const delta = Date.now() - t;
  if (delta < 60_000) return `${Math.max(1, Math.round(delta / 1000))}s ago`;
  if (delta < 3_600_000) return `${Math.round(delta / 60_000)}m ago`;
  if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h ago`;
  return `${Math.round(delta / 86_400_000)}d ago`;
}

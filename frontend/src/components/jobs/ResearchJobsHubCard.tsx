import { useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Activity } from "lucide-react";
import { ResearchJobsApi } from "@/api/researchJobs";
import type { ResearchJobSummary } from "@/api/schemas/researchJobs";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatusBadge } from "@/components/badges/StatusBadge";

/**
 * ResearchJobsHubCard.
 *
 * Dashboard hub mirror of the per-research-page JobMonitor — shows the most
 * recent N research jobs (across all kinds) with progress bars + per-row
 * cancel + click-through to the originating research surface so the operator
 * sees recent runs without having to navigate to a research page first.
 */
export function ResearchJobsHubCard({ limit = 10 }: { limit?: number }): JSX.Element | null {
  const queryClient = useQueryClient();
  const list = useQuery({
    queryKey: ["research-jobs", "dashboard"],
    queryFn: () => ResearchJobsApi.list({ limit }),
    refetchInterval: (query) => {
      const data = query.state.data as { jobs?: ResearchJobSummary[] } | undefined;
      const hasActive = (data?.jobs ?? []).some(
        (j) => j.status === "queued" || j.status === "running",
      );
      return hasActive ? 2_000 : 15_000;
    },
  });
  const cancel = useMutation({
    mutationFn: (jobId: string) => ResearchJobsApi.cancel(jobId),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["research-jobs"] }),
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
    <Card>
      <CardHeader>
        <CardTitle>
          <span className="inline-flex items-center gap-2">
            <Activity
              className={`h-3.5 w-3.5 ${activeCount > 0 ? "animate-pulse text-info" : "text-fg-muted"}`}
              aria-hidden="true"
            />
            Recent research runs
          </span>
        </CardTitle>
        <span className="flex items-center gap-2 text-[11px]">
          {activeCount > 0 ? (
            <StatusBadge tone="info">{activeCount} active</StatusBadge>
          ) : null}
          {counts.completed > 0 ? (
            <StatusBadge tone="ok">{counts.completed} done</StatusBadge>
          ) : null}
          {counts.failed > 0 ? (
            <StatusBadge tone="danger">{counts.failed} failed</StatusBadge>
          ) : null}
          {counts.canceled > 0 ? (
            <StatusBadge tone="muted">{counts.canceled} canceled</StatusBadge>
          ) : null}
        </span>
      </CardHeader>
      <CardBody className="p-0">
        {list.isLoading && jobs.length === 0 ? (
          <div className="p-4 text-xs text-fg-muted">Loading research jobs…</div>
        ) : null}
        {!list.isLoading && jobs.length === 0 ? (
          <div className="p-4 text-xs text-fg-muted">
            No research jobs yet. Run a backtest, walk-forward, or optimization to see
            progress here.
          </div>
        ) : null}
        {jobs.length > 0 ? (
          <table className="ut-table">
            <thead>
              <tr>
                <th>Started</th>
                <th>Kind</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Result</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <Row key={job.job_id} job={job} onCancel={() => cancel.mutate(job.job_id)} />
              ))}
            </tbody>
          </table>
        ) : null}
      </CardBody>
    </Card>
  );
}

function Row({
  job,
  onCancel,
}: {
  job: ResearchJobSummary;
  onCancel: () => void;
}): JSX.Element {
  const tone = statusTone(job.status);
  const isActive = job.status === "queued" || job.status === "running";
  const pct =
    job.progress_total > 0 ? Math.min(100, (job.progress_current / job.progress_total) * 100) : 0;
  const path = surfacePath(job.kind);
  return (
    <tr>
      <td className="text-fg-muted text-xs" title={job.created_at}>
        {fmtRel(job.created_at)}
      </td>
      <td className="text-xs font-mono text-fg-muted">{job.kind.replace(/_/g, " ")}</td>
      <td>
        <StatusBadge tone={tone}>{job.status}</StatusBadge>
      </td>
      <td className="min-w-[160px]">
        <div className="text-[10px] text-fg-muted mb-0.5">
          {job.progress_label || "—"}
          {job.progress_total > 0 ? ` · ${job.progress_current}/${job.progress_total}` : ""}
        </div>
        <div className="h-1.5 w-full rounded bg-bg-inset overflow-hidden">
          <div
            className={`h-full ${progressBg(job.status)}`}
            style={{ width: isActive ? `${pct}%` : "100%" }}
          />
        </div>
      </td>
      <td className="text-xs">
        {job.result_run_id ? (
          <Link to={path} className="text-accent underline hover:no-underline">
            run {job.result_run_id.slice(0, 8)} →
          </Link>
        ) : job.error ? (
          <span className="text-danger" title={job.error}>
            {job.error.slice(0, 40)}
            {job.error.length > 40 ? "…" : ""}
          </span>
        ) : (
          <span className="text-fg-subtle">—</span>
        )}
      </td>
      <td className="text-right">
        {isActive ? (
          <Button size="sm" variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : (
          <Link to={path} className="text-xs text-accent underline hover:no-underline">
            Open
          </Link>
        )}
      </td>
    </tr>
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

function surfacePath(kind: string): string {
  switch (kind) {
    case "backtest":
      return "/backtests";
    case "walk_forward":
      return "/walk-forward";
    case "optimization":
      return "/optimization";
    default:
      return "/";
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

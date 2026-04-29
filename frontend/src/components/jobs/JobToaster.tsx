import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { CheckCircle, XCircle, AlertCircle, X } from "lucide-react";
import { ResearchJobsApi } from "@/api/researchJobs";
import type { ResearchJobSummary } from "@/api/schemas/researchJobs";

/**
 * JobToaster.
 *
 * Mounted once at app shell level. Polls the research-jobs list at the same
 * cadence the JobMonitor does (2s when active jobs exist, 15s when terminal)
 * and fires a toast whenever a job transitions from active → terminal that
 * the operator did NOT just submit on the current page.
 *
 * Toast classification:
 * - completed → success tone, "View result" link to the right research surface
 * - canceled  → muted tone, no link (operator already knows; banner just confirms)
 * - failed    → danger tone, error preview + "View" link
 *
 * The toaster persists no state across reloads — a refresh clears unseen
 * notifications. Operators who miss a toast can still see the run on the
 * list page and the job in the JobMonitor history.
 */
export function JobToaster(): JSX.Element {
  const [active, setActive] = useState<ToastEvent[]>([]);
  const seenTerminal = useRef<Set<string>>(new Set());
  const initialized = useRef<boolean>(false);

  const list = useQuery({
    queryKey: ["research-jobs", "global"],
    queryFn: () => ResearchJobsApi.list({ limit: 50 }),
    refetchInterval: (query) => {
      const data = query.state.data as { jobs?: ResearchJobSummary[] } | undefined;
      const hasActive = (data?.jobs ?? []).some(
        (j) => j.status === "queued" || j.status === "running",
      );
      return hasActive ? 2_000 : 15_000;
    },
  });

  useEffect(() => {
    // Wait for the first real fetch — if we run before `useQuery` resolves,
    // `list.data` is `undefined` and we'd flip `initialized.current = true`
    // against an empty seed. Then when real data arrives every historical
    // terminal job fires as a "new" toast on page reload (the bug operator
    // hit on 2026-04-28).
    if (list.data === undefined) return;
    const jobs = list.data.jobs ?? [];
    if (!initialized.current) {
      // Seed seenTerminal with everything currently terminal so we don't
      // toast historical jobs the moment the page loads.
      for (const job of jobs) {
        if (isTerminal(job.status)) {
          seenTerminal.current.add(job.job_id);
        }
      }
      initialized.current = true;
      return;
    }
    const fresh: ToastEvent[] = [];
    for (const job of jobs) {
      if (!isTerminal(job.status)) continue;
      if (seenTerminal.current.has(job.job_id)) continue;
      seenTerminal.current.add(job.job_id);
      fresh.push(toToastEvent(job));
    }
    if (fresh.length > 0) {
      setActive((prev) => [...prev, ...fresh]);
    }
  }, [list.data]);

  return (
    <ToastPrimitive.Provider swipeDirection="right" duration={8_000}>
      {active.map((evt) => (
        <ToastPrimitive.Root
          key={evt.id}
          duration={evt.severity === "danger" ? 12_000 : 8_000}
          onOpenChange={(open) => {
            if (!open) {
              setActive((prev) => prev.filter((e) => e.id !== evt.id));
            }
          }}
          className={`pointer-events-auto rounded border bg-bg-elevated shadow-lg ${
            severityBorder(evt.severity)
          } data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:slide-in-from-bottom-2`}
        >
          <div className="flex items-start gap-3 p-3">
            <span className={`mt-0.5 ${severityIconClass(evt.severity)}`} aria-hidden="true">
              {evt.severity === "ok" ? (
                <CheckCircle className="h-4 w-4" />
              ) : evt.severity === "danger" ? (
                <XCircle className="h-4 w-4" />
              ) : (
                <AlertCircle className="h-4 w-4" />
              )}
            </span>
            <div className="min-w-0 flex-1">
              <ToastPrimitive.Title className={`text-sm font-semibold ${severityTextClass(evt.severity)}`}>
                {evt.title}
              </ToastPrimitive.Title>
              {evt.description ? (
                <ToastPrimitive.Description className="mt-0.5 text-xs text-fg-muted break-all">
                  {evt.description}
                </ToastPrimitive.Description>
              ) : null}
              {evt.linkTo ? (
                <ToastPrimitive.Action altText="View result" asChild>
                  <Link
                    to={evt.linkTo}
                    onClick={() =>
                      setActive((prev) => prev.filter((e) => e.id !== evt.id))
                    }
                    className="mt-2 inline-block text-xs text-accent underline hover:no-underline"
                  >
                    {evt.linkLabel ?? "View result"}
                  </Link>
                </ToastPrimitive.Action>
              ) : null}
            </div>
            <ToastPrimitive.Close
              className="ml-2 text-fg-muted hover:text-fg"
              aria-label="Close"
            >
              <X className="h-3.5 w-3.5" />
            </ToastPrimitive.Close>
          </div>
        </ToastPrimitive.Root>
      ))}
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[60] flex w-[380px] max-w-[calc(100vw-2rem)] flex-col gap-2" />
    </ToastPrimitive.Provider>
  );
}

interface ToastEvent {
  id: string;
  severity: "ok" | "warn" | "danger";
  title: string;
  description?: string;
  linkTo?: string;
  linkLabel?: string;
}

function toToastEvent(job: ResearchJobSummary): ToastEvent {
  const kindLabel = job.kind.replace(/_/g, " ");
  if (job.status === "completed") {
    return {
      id: job.job_id,
      severity: "ok",
      title: `${capitalize(kindLabel)} completed`,
      description: job.progress_label
        ? `${job.progress_label}${
            job.progress_total > 0 ? ` · ${job.progress_current}/${job.progress_total}` : ""
          }`
        : undefined,
      linkTo: surfacePath(job.kind),
      linkLabel: "View results →",
    };
  }
  if (job.status === "canceled") {
    return {
      id: job.job_id,
      severity: "warn",
      title: `${capitalize(kindLabel)} canceled`,
      description: job.error ?? "Operator-requested cancel",
    };
  }
  return {
    id: job.job_id,
    severity: "danger",
    title: `${capitalize(kindLabel)} failed`,
    description: job.error ?? "see the JobMonitor for details",
    linkTo: surfacePath(job.kind),
    linkLabel: "Open page →",
  };
}

function isTerminal(status: string): boolean {
  return status === "completed" || status === "failed" || status === "canceled";
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

function severityBorder(severity: "ok" | "warn" | "danger"): string {
  switch (severity) {
    case "ok":
      return "border-ok/40";
    case "warn":
      return "border-warn/40";
    case "danger":
      return "border-danger/40";
  }
}

function severityTextClass(severity: "ok" | "warn" | "danger"): string {
  switch (severity) {
    case "ok":
      return "text-ok";
    case "warn":
      return "text-warn";
    case "danger":
      return "text-danger";
  }
}

function severityIconClass(severity: "ok" | "warn" | "danger"): string {
  switch (severity) {
    case "ok":
      return "text-ok";
    case "warn":
      return "text-warn";
    case "danger":
      return "text-danger";
  }
}

function capitalize(value: string): string {
  return value.length > 0 ? value[0].toUpperCase() + value.slice(1) : value;
}

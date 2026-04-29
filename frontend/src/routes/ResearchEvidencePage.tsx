import { useQuery } from "@tanstack/react-query";
import { ResearchApi } from "@/api/research";
import type { EvidenceTypeValue, ResearchEvidence } from "@/api/schemas/research";
import { Banner } from "@/components/ui/Banner";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { PageHeader } from "./PageHeader";
import { relativeTime } from "@/lib/format";

/**
 * Generic first-class research surface.
 *
 * The Coordinator (Operation Turtle Shell) owns the simulation /
 * backtest / optimization / walk-forward engines. The current
 * read-only API is `/api/v1/operations/research-evidence` filtered
 * by `evidence_type`. This page renders that for one evidence
 * type. New "create run" flows land when the backend exposes
 * `/api/v1/sim-lab`, `/api/v1/backtests`, `/api/v1/optimization`,
 * `/api/v1/walk-forward` per `API_AND_READ_MODEL_GAPS.md`.
 */
export interface ResearchEvidencePageProps {
  title: string;
  subtitle: string;
  evidenceType: EvidenceTypeValue;
  awaitingMessage: string;
  /** Slug into `explainerContent.EXPLAINERS` — opens the per-page Explainer drawer. */
  explainSlug?: string;
}

export function ResearchEvidencePage({
  title,
  subtitle,
  evidenceType,
  awaitingMessage,
  explainSlug,
}: ResearchEvidencePageProps): JSX.Element {
  const list = useQuery({
    queryKey: ["research", evidenceType],
    queryFn: () => ResearchApi.list({ evidence_type: evidenceType }),
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-4">
      <PageHeader title={title} subtitle={subtitle} explainSlug={explainSlug} />

      <Banner
        severity="info"
        title="Read-only V1"
        message={awaitingMessage}
      />

      {list.isLoading ? (
        <LoadingState title="Loading evidence" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load evidence"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : list.data?.evidence.length === 0 ? (
        <EmptyState
          title="No runs yet"
          message="Runs of this type will appear here once produced. The 'create run' surface lands when the corresponding API is wired."
        />
      ) : (
        <EvidenceTable items={list.data?.evidence ?? []} />
      )}
    </div>
  );
}

function EvidenceTable({ items }: { items: ResearchEvidence[] }): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent runs</CardTitle>
        <StatusBadge>{items.length}</StatusBadge>
      </CardHeader>
      <CardBody className="p-0">
        <table className="ut-table">
          <thead>
            <tr>
              <th>Created</th>
              <th>Strategy</th>
              <th>Version</th>
              <th>Status</th>
              <th>Summary</th>
            </tr>
          </thead>
          <tbody>
            {items.map((e, i) => {
              const id = e.evidence_id ?? `e-${i}`;
              const summary = compactSummary(e);
              return (
                <tr key={id}>
                  <td className="text-fg-muted">{e.created_at ? relativeTime(e.created_at) : "—"}</td>
                  <td className="font-mono text-xs">{e.strategy_id ? e.strategy_id.slice(0, 8) : "—"}</td>
                  <td className="font-mono text-xs">
                    {e.strategy_version_id ? e.strategy_version_id.slice(0, 8) : "—"}
                  </td>
                  <td>
                    <StatusBadge tone={e.succeeded === false ? "danger" : e.succeeded === true ? "ok" : "neutral"}>
                      {e.succeeded === false ? "failed" : e.succeeded === true ? "succeeded" : "—"}
                    </StatusBadge>
                  </td>
                  <td className="text-xs text-fg-muted">{summary}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}

function compactSummary(e: ResearchEvidence): string {
  const summary = (e.summary as Record<string, unknown> | undefined) ?? {};
  const metrics = (e.metrics as Record<string, unknown> | undefined) ?? {};
  const merged = { ...summary, ...metrics };
  const entries = Object.entries(merged).slice(0, 3);
  if (entries.length === 0) return e.name ?? "";
  return entries.map(([k, v]) => `${k}=${formatScalar(v)}`).join(" · ");
}

function formatScalar(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    if (Number.isInteger(v)) return v.toString();
    return v.toFixed(4);
  }
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string") return v.length > 24 ? `${v.slice(0, 24)}…` : v;
  return JSON.stringify(v).slice(0, 32);
}

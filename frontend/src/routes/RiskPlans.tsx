import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Sparkles, GitCompare, Copy, Archive, Pencil, Eye, FlaskConical } from "lucide-react";
import { ApiError } from "@/api/client";
import { RiskPlansApi } from "@/api/riskPlans";
import type {
  RiskPlanSource,
  RiskPlanStatus,
  RiskPlanSummary,
  RiskPlanTier,
} from "@/api/schemas/riskPlans";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge, type StatusTone } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { RiskPlanDrawer } from "@/components/risk_plans/RiskPlanDrawer";
import { CompareRiskPlansDialog } from "@/components/risk_plans/CompareRiskPlansDialog";
import { PageHeader } from "./PageHeader";
import { relativeTime } from "@/lib/format";

const TIER_TONE: Record<RiskPlanTier, StatusTone> = {
  conservative: "ok",
  balanced: "info",
  aggressive: "danger",
  custom: "neutral",
};

const STATUS_TONE: Record<RiskPlanStatus, StatusTone> = {
  draft: "info",
  active: "ok",
  archived: "muted",
};

const SOURCE_LABEL: Record<RiskPlanSource, string> = {
  manual: "manual",
  ai_generated: "AI",
  optimization_generated: "Optimization",
  walk_forward_recommended: "Walk-Forward",
};

function scoreTone(score: number): StatusTone {
  if (score <= 2) return "ok";
  if (score <= 4) return "info";
  if (score <= 6) return "neutral";
  if (score <= 8) return "warn";
  return "danger";
}

export function RiskPlans(): JSX.Element {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const list = useQuery({
    queryKey: ["risk-plans", "list"],
    queryFn: () => RiskPlansApi.list(),
    refetchInterval: 30_000,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<string | null>(null);
  const [compareIds, setCompareIds] = useState<{ a: string; b: string } | null>(null);
  const [search, setSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<"" | RiskPlanStatus>("");
  const [tierFilter, setTierFilter] = useState<"" | RiskPlanTier>("");
  const [sourceFilter, setSourceFilter] = useState<"" | RiskPlanSource>("");
  const [minScore, setMinScore] = useState<string>("");
  const [maxScore, setMaxScore] = useState<string>("");

  const editTargetDetail = useQuery({
    queryKey: ["risk-plans", "detail", editTarget],
    queryFn: () => RiskPlansApi.get(editTarget as string),
    enabled: Boolean(editTarget),
  });

  const archive = useMutation({
    mutationFn: (planId: string) => RiskPlansApi.archive(planId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["risk-plans"] });
    },
  });

  const duplicate = useMutation({
    mutationFn: async (sourceId: string) => {
      const detail = await RiskPlansApi.get(sourceId);
      const config = detail.active_version?.config;
      if (!config) throw new Error("source plan has no active version");
      return RiskPlansApi.create({
        name: `${detail.name} (copy)`,
        description: detail.description ?? null,
        risk_score: detail.risk_score,
        risk_tier: detail.risk_tier,
        source: detail.source ?? "manual",
        config,
      });
    },
    onSuccess: (saved) => {
      void queryClient.invalidateQueries({ queryKey: ["risk-plans"] });
      navigate(`/risk-plans/${saved.risk_plan_id}`);
    },
  });

  const filtered = useMemo(() => {
    const all = list.data?.risk_plans ?? [];
    const searchLower = search.trim().toLowerCase();
    const min = minScore.trim() === "" ? null : Number(minScore);
    const max = maxScore.trim() === "" ? null : Number(maxScore);
    return all.filter((plan) => {
      if (statusFilter && plan.status !== statusFilter) return false;
      if (tierFilter && plan.risk_tier !== tierFilter) return false;
      if (sourceFilter && plan.source !== sourceFilter) return false;
      if (min != null && plan.risk_score < min) return false;
      if (max != null && plan.risk_score > max) return false;
      if (searchLower) {
        const hay = `${plan.name} ${plan.description ?? ""}`.toLowerCase();
        if (!hay.includes(searchLower)) return false;
      }
      return true;
    });
  }, [list.data, search, statusFilter, tierFilter, sourceFilter, minScore, maxScore]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Risk Plans"
        subtitle="Reusable risk policy. Pinned to research runs, Account defaults, and the live runtime. Every sized SignalPlan reads from a versioned RiskPlan."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<GitCompare className="h-3.5 w-3.5" aria-hidden="true" />}
              disabled={(list.data?.risk_plans ?? []).length < 2}
              onClick={() => {
                const plans = list.data?.risk_plans ?? [];
                if (plans.length >= 2) {
                  setCompareIds({ a: plans[0].risk_plan_id, b: plans[1].risk_plan_id });
                }
              }}
            >
              Compare
            </Button>
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setAiOpen(true)}
            >
              Generate with AI
            </Button>
            <Button
              size="sm"
              variant="primary"
              leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setCreateOpen(true)}
            >
              New Risk Plan
            </Button>
          </div>
        }
      />

      <Card>
        <div className="grid grid-cols-1 gap-3 px-4 py-3 md:grid-cols-6">
          <TextField
            label="Search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Name or description"
          />
          <Select
            label="Status"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as "" | RiskPlanStatus)}
          >
            <option value="">all</option>
            <option value="draft">draft</option>
            <option value="active">active</option>
            <option value="archived">archived</option>
          </Select>
          <Select
            label="Tier"
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value as "" | RiskPlanTier)}
          >
            <option value="">all</option>
            <option value="conservative">conservative</option>
            <option value="balanced">balanced</option>
            <option value="aggressive">aggressive</option>
            <option value="custom">custom</option>
          </Select>
          <Select
            label="Source"
            value={sourceFilter}
            onChange={(e) => setSourceFilter(e.target.value as "" | RiskPlanSource)}
          >
            <option value="">all</option>
            <option value="manual">manual</option>
            <option value="ai_generated">AI</option>
            <option value="optimization_generated">Optimization</option>
            <option value="walk_forward_recommended">Walk-Forward</option>
          </Select>
          <TextField
            type="number"
            label="Min score"
            min={0}
            max={10}
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
          />
          <TextField
            type="number"
            label="Max score"
            min={0}
            max={10}
            value={maxScore}
            onChange={(e) => setMaxScore(e.target.value)}
          />
        </div>
      </Card>

      {archive.error ? (
        <Banner
          severity="danger"
          title="Could not archive"
          message={
            archive.error instanceof ApiError
              ? archive.error.detail || archive.error.message
              : String(archive.error)
          }
        />
      ) : null}
      {duplicate.error ? (
        <Banner
          severity="danger"
          title="Could not duplicate"
          message={
            duplicate.error instanceof ApiError
              ? duplicate.error.detail || duplicate.error.message
              : String(duplicate.error)
          }
        />
      ) : null}

      {list.isLoading ? (
        <LoadingState title="Loading Risk Plans" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load Risk Plans"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : (list.data?.risk_plans ?? []).length === 0 ? (
        <EmptyState
          title="No Risk Plans yet"
          message="Create one to power Backtest, Walk-Forward, Optimization, Sim Lab, and live Account sizing. Or generate with AI from a plain-English prompt."
          action={
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" onClick={() => setAiOpen(true)}>
                Generate with AI
              </Button>
              <Button size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
                New Risk Plan
              </Button>
            </div>
          }
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="No Risk Plans match these filters"
          message="Loosen the status / tier / source / score filters above."
        />
      ) : (
        <div className="overflow-x-auto rounded border border-border">
          <table className="min-w-full text-xs">
            <thead className="bg-bg-subtle text-fg-muted">
              <tr>
                <th className="px-3 py-2 text-left font-medium">Name</th>
                <th className="px-3 py-2 text-left font-medium">Status</th>
                <th className="px-3 py-2 text-left font-medium">Score</th>
                <th className="px-3 py-2 text-left font-medium">Tier</th>
                <th className="px-3 py-2 text-left font-medium">Sizing</th>
                <th className="px-3 py-2 text-left font-medium">Source</th>
                <th className="px-3 py-2 text-left font-medium">Linked accounts</th>
                <th className="px-3 py-2 text-left font-medium">Last used</th>
                <th className="px-3 py-2 text-left font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border bg-bg-raised">
              {filtered.map((plan) => (
                <RiskPlanRow
                  key={plan.risk_plan_id}
                  plan={plan}
                  onView={() => navigate(`/risk-plans/${plan.risk_plan_id}`)}
                  onEdit={() => setEditTarget(plan.risk_plan_id)}
                  onDuplicate={() => duplicate.mutate(plan.risk_plan_id)}
                  onArchive={() => archive.mutate(plan.risk_plan_id)}
                  onAssign={() => navigate(`/accounts?risk_plan_id=${plan.risk_plan_id}`)}
                  onUseInBacktest={() =>
                    navigate(
                      plan.active_version_id
                        ? `/backtests?risk_plan_version_id=${plan.active_version_id}`
                        : `/risk-plans/${plan.risk_plan_id}`,
                    )
                  }
                  onCompare={() => {
                    const others = (list.data?.risk_plans ?? []).filter(
                      (p) => p.risk_plan_id !== plan.risk_plan_id,
                    );
                    if (others[0]) {
                      setCompareIds({ a: plan.risk_plan_id, b: others[0].risk_plan_id });
                    }
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Create drawer (manual). */}
      <RiskPlanDrawer
        mode="create"
        open={createOpen}
        onOpenChange={setCreateOpen}
        defaultSource="manual"
        onSaved={(saved) => navigate(`/risk-plans/${saved.risk_plan_id}`)}
      />
      {/* Generate-with-AI drawer (same drawer, AI section in focus). */}
      <RiskPlanDrawer
        mode="create"
        open={aiOpen}
        onOpenChange={setAiOpen}
        defaultSource="ai_generated"
        onSaved={(saved) => navigate(`/risk-plans/${saved.risk_plan_id}`)}
      />
      {/* Edit drawer fed by detail fetch. */}
      <RiskPlanDrawer
        mode="edit"
        open={Boolean(editTarget)}
        onOpenChange={(o) => {
          if (!o) setEditTarget(null);
        }}
        plan={editTargetDetail.data ?? null}
      />
      {/* Compare modal. */}
      <CompareRiskPlansDialog
        open={Boolean(compareIds)}
        onOpenChange={(o) => {
          if (!o) setCompareIds(null);
        }}
        plans={list.data?.risk_plans ?? []}
        initial={compareIds}
      />
    </div>
  );
}

function RiskPlanRow({
  plan,
  onView,
  onEdit,
  onDuplicate,
  onArchive,
  onAssign,
  onUseInBacktest,
  onCompare,
}: {
  plan: RiskPlanSummary;
  onView: () => void;
  onEdit: () => void;
  onDuplicate: () => void;
  onArchive: () => void;
  onAssign: () => void;
  onUseInBacktest: () => void;
  onCompare: () => void;
}): JSX.Element {
  const config = plan.active_version?.config;
  return (
    <tr className="hover:bg-bg-subtle/40">
      <td className="px-3 py-2">
        <Link to={`/risk-plans/${plan.risk_plan_id}`} className="font-medium text-fg hover:underline">
          {plan.name}
        </Link>
        {plan.description ? (
          <div className="text-[10px] text-fg-subtle line-clamp-1">{plan.description}</div>
        ) : null}
      </td>
      <td className="px-3 py-2">
        <StatusBadge size="sm" tone={STATUS_TONE[plan.status]}>
          {plan.status}
        </StatusBadge>
      </td>
      <td className="px-3 py-2">
        <StatusBadge size="sm" tone={scoreTone(plan.risk_score)}>
          {plan.risk_score}
        </StatusBadge>
      </td>
      <td className="px-3 py-2">
        <StatusBadge size="sm" tone={TIER_TONE[plan.risk_tier]}>
          {plan.risk_tier}
        </StatusBadge>
      </td>
      <td className="px-3 py-2 text-fg-muted">{config?.sizing_method ?? "—"}</td>
      <td className="px-3 py-2 text-fg-muted">{SOURCE_LABEL[plan.source]}</td>
      <td className="px-3 py-2 text-fg-muted">{plan.linked_account_count ?? 0}</td>
      <td className="px-3 py-2 text-fg-muted">{relativeTime(plan.last_used_at)}</td>
      <td className="px-3 py-2">
        <div className="flex flex-wrap gap-1">
          <IconButton title="View" onClick={onView}>
            <Eye className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton title="Edit draft" onClick={onEdit}>
            <Pencil className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton title="Duplicate" onClick={onDuplicate}>
            <Copy className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton title="Use in Backtest" onClick={onUseInBacktest}>
            <FlaskConical className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton title="Compare" onClick={onCompare}>
            <GitCompare className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton title="Assign to Account" onClick={onAssign}>
            <Plus className="h-3.5 w-3.5" />
          </IconButton>
          <IconButton
            title="Archive"
            onClick={onArchive}
            disabled={plan.status === "archived"}
          >
            <Archive className="h-3.5 w-3.5" />
          </IconButton>
        </div>
      </td>
    </tr>
  );
}

function IconButton({
  title,
  children,
  onClick,
  disabled,
}: {
  title: string;
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
}): JSX.Element {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      disabled={disabled}
      onClick={onClick}
      className="rounded border border-border bg-bg-raised p-1 text-fg-muted hover:bg-bg-subtle hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
    >
      {children}
    </button>
  );
}

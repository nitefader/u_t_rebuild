import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Sparkles } from "lucide-react";
import { ApiError } from "@/api/client";
import { StrategiesApi } from "@/api/strategies";
import type { Strategy } from "@/api/schemas/strategies";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { PageHeader } from "./PageHeader";
import { relativeTime } from "@/lib/format";

export function Strategies(): JSX.Element {
  const list = useQuery({
    queryKey: ["strategies", "list"],
    queryFn: () => StrategiesApi.list(),
    refetchInterval: 30_000,
  });
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Strategies"
        subtitle="Reusable trading logic and execution-plan config. Versions are frozen before they can power a Deployment."
        explainSlug="strategies"
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setCreateOpen(true)}
            >
              New blank strategy
            </Button>
            <Link to="/strategies/compose">
              <Button
                size="sm"
                variant="primary"
                leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
              >
                Compose new strategy
              </Button>
            </Link>
          </div>
        }
      />

      {list.isLoading ? (
        <LoadingState title="Loading strategies" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load strategies"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : (list.data?.strategies.length ?? 0) === 0 ? (
        <EmptyState
          title="No strategies yet"
          message="Compose a Strategy from a plain-English prompt with the AI Composer, or start a blank Strategy and author entry / exit rules in the visual builder. Freeze a version, then point a Deployment at it."
          action={
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
                onClick={() => setCreateOpen(true)}
              >
                New blank strategy
              </Button>
              <Link to="/strategies/compose">
                <Button
                  size="sm"
                  variant="primary"
                  leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
                >
                  Compose new strategy
                </Button>
              </Link>
            </div>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {list.data?.strategies.map((s) => <StrategyCard key={s.strategy_id} strategy={s} />)}
        </div>
      )}

      <CreateStrategyDrawer open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

function StrategyCard({ strategy }: { strategy: Strategy }): JSX.Element {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <div className="min-w-0">
          <div className="font-semibold tracking-tight">{strategy.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge
              tone={
                strategy.status === "deprecated" ? "muted" : strategy.status === "active" ? "ok" : "info"
              }
            >
              {strategy.status}
            </StatusBadge>
            <StatusBadge tone="neutral">{strategy.version_count} versions</StatusBadge>
            {strategy.frozen_version_ids.length > 0 ? (
              <StatusBadge tone="ok">{strategy.frozen_version_ids.length} frozen</StatusBadge>
            ) : (
              <StatusBadge tone="warn">no frozen version</StatusBadge>
            )}
          </div>
        </div>
      </div>
      {strategy.description ? (
        <div className="px-4 py-2 text-xs text-fg-muted">{strategy.description}</div>
      ) : null}
      {strategy.tags.length ? (
        <div className="px-4 pb-2 text-[11px] text-fg-subtle">{strategy.tags.join(" · ")}</div>
      ) : null}
      <div className="flex items-center justify-between border-t border-border/70 px-4 py-2 text-xs text-fg-muted">
        <span>{relativeTime(strategy.created_at)}</span>
        <Link to={`/strategies/${strategy.strategy_id}`}>
          <Button size="sm" variant="secondary">
            Open
          </Button>
        </Link>
      </div>
    </Card>
  );
}

function CreateStrategyDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setName("");
    setDescription("");
    setTags("");
    setError(null);
  }

  const create = useMutation({
    mutationFn: () =>
      StrategiesApi.create({
        name: name.trim(),
        description: description.trim() || null,
        tags: tags
          .split(/[,\s]+/)
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    onSuccess: (resp) => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["strategies", "list"] });
      // Land directly in the full-page builder for the first version so the
      // operator never sees an empty Strategy detail page.
      navigate(`/strategies/${resp.strategy.strategy_id}/builder/new`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

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
          <DrawerTitle>New Strategy</DrawerTitle>
          <DrawerDescription>
            Create a Strategy shell with a display name and optional capability tags. Author the
            first version after creation; freeze it to publish before pointing a Deployment at it.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not create" message={error} /> : null}
          <TextField
            label="Display name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Mean reversion intraday"
          />
          <TextField
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <TextField
            label="Capabilities / tags (comma or space separated)"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="intraday, mean-reversion, equities"
          />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!name.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Create Strategy
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Pencil, Copy, Trash2 } from "lucide-react";
import { listAllHeads, duplicateVersion, deleteStrategy } from "@/api/strategiesV4";
import type { StrategyHeadSummary } from "@/api/strategiesV4";
import { ApiError } from "@/api/client";
import { ROUTE_STRATEGIES_COMPOSE } from "@/strategy_ide_v4/routes";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerDescription,
} from "@/components/ui/Drawer";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { PageHeader } from "./PageHeader";
import { relativeTime } from "@/lib/format";

export function StrategiesV4(): JSX.Element {
  const navigate = useNavigate();
  const list = useQuery({
    queryKey: ["strategies-v4", "heads"],
    queryFn: listAllHeads,
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-4">
      <PageHeader
        title="Strategies"
        subtitle="v4 strategy versions authored in the IDE. Edit, duplicate, or delete strategies here."
        explainSlug="strategies"
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => navigate(ROUTE_STRATEGIES_COMPOSE)}
          >
            New strategy
          </Button>
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
      ) : (list.data?.length ?? 0) === 0 ? (
        <EmptyState
          title="No strategies yet"
          message="Create your first strategy in the IDE."
          action={
            <Button
              size="sm"
              variant="primary"
              leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => navigate(ROUTE_STRATEGIES_COMPOSE)}
            >
              New strategy
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {list.data?.map((s) => <StrategyHeadCard key={s.strategy_v4_id} strategy={s} />)}
        </div>
      )}
    </div>
  );
}

function StrategyHeadCard({ strategy }: { strategy: StrategyHeadSummary }): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deleteMutation = useMutation({
    mutationFn: () => deleteStrategy(strategy.strategy_v4_id),
    onSuccess: () => {
      setDeleteOpen(false);
      void qc.invalidateQueries({ queryKey: ["strategies-v4", "heads"] });
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.detail ?? e.message : String(e)),
  });

  return (
    <>
      <Card>
        <div className="flex items-start justify-between gap-3 px-4 pt-3">
          <div className="min-w-0">
            <div className="font-semibold tracking-tight">{strategy.name}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              <StatusBadge tone="neutral">v{strategy.head_version}</StatusBadge>
              {strategy.total_versions > 1 ? (
                <StatusBadge tone="info">{strategy.total_versions} versions</StatusBadge>
              ) : null}
            </div>
          </div>
        </div>
        {strategy.description ? (
          <div className="px-4 py-2 text-xs text-fg-muted">{strategy.description}</div>
        ) : null}
        <div className="flex items-center justify-between border-t border-border/70 px-4 py-2 text-xs text-fg-muted">
          <span>{relativeTime(strategy.updated_at)}</span>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              aria-label={`Edit strategy ${strategy.name}`}
              leftIcon={<Pencil className="h-3 w-3" aria-hidden="true" />}
              onClick={() =>
                navigate(`${ROUTE_STRATEGIES_COMPOSE}?id=${strategy.head_version_id}`)
              }
            >
              Edit
            </Button>
            <Button
              size="sm"
              variant="secondary"
              aria-label={`Duplicate strategy ${strategy.name}`}
              leftIcon={<Copy className="h-3 w-3" aria-hidden="true" />}
              onClick={() => setDuplicateOpen(true)}
            >
              Duplicate
            </Button>
            <Button
              size="sm"
              variant="danger"
              aria-label={`Delete strategy ${strategy.name}`}
              leftIcon={<Trash2 className="h-3 w-3" aria-hidden="true" />}
              onClick={() => setDeleteOpen(true)}
            >
              Delete
            </Button>
          </div>
        </div>
        {error ? (
          <div className="px-4 pb-3">
            <Banner severity="danger" title="Action failed" message={error} />
          </div>
        ) : null}
      </Card>

      {/* Delete confirmation drawer */}
      <Drawer open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DrawerContent>
          <DrawerHeader>
            <DrawerTitle>Delete strategy</DrawerTitle>
            <DrawerDescription>
              This permanently deletes all versions of <strong>{strategy.name}</strong>. This
              action cannot be undone.
            </DrawerDescription>
          </DrawerHeader>
          <DrawerBody>
            <p className="text-sm text-fg-muted">
              All versions of this strategy will be permanently deleted.
            </p>
          </DrawerBody>
          <DrawerFooter>
            <Button variant="ghost" size="sm" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={deleteMutation.isPending}
              onClick={() => deleteMutation.mutate()}
            >
              Delete permanently
            </Button>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>

      {/* Duplicate drawer */}
      {duplicateOpen ? (
        <DuplicateStrategyDrawer
          sourceVersionId={strategy.head_version_id}
          sourceName={strategy.name}
          open={duplicateOpen}
          onOpenChange={setDuplicateOpen}
        />
      ) : null}
    </>
  );
}

function DuplicateStrategyDrawer({
  sourceVersionId,
  sourceName,
  open,
  onOpenChange,
}: {
  sourceVersionId: string;
  sourceName: string;
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [newName, setNewName] = useState(`${sourceName} (copy)`);
  const [error, setError] = useState<string | null>(null);

  const duplicate = useMutation({
    mutationFn: () => duplicateVersion(sourceVersionId, newName.trim()),
    onSuccess: (version) => {
      void qc.invalidateQueries({ queryKey: ["strategies-v4", "heads"] });
      onOpenChange(false);
      navigate(`${ROUTE_STRATEGIES_COMPOSE}?id=${version.id}`);
    },
    onError: (e) =>
      setError(e instanceof ApiError ? e.detail ?? e.message : String(e)),
  });

  return (
    <Drawer
      open={open}
      onOpenChange={(next) => {
        if (!next) setError(null);
        onOpenChange(next);
      }}
    >
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Duplicate strategy</DrawerTitle>
          <DrawerDescription>
            Creates a new strategy from the head version of <strong>{sourceName}</strong>.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not duplicate" message={error} /> : null}
          <TextField
            label="New strategy name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="Strategy name"
          />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!newName.trim()}
            loading={duplicate.isPending}
            onClick={() => duplicate.mutate()}
          >
            Duplicate
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

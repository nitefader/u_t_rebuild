import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Copy, Archive, Star, Pencil } from "lucide-react";
import { ApiError } from "@/api/client";
import { StrategyControlsApi } from "@/api/strategyControls";
import type { StrategyControlsLibrarySummary } from "@/api/schemas/strategyControls";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { TextField } from "@/components/ui/TextField";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "@/components/ui/Drawer";
import { HoldToArmConfirm } from "@/components/ui/HoldToArmConfirm";
import { PageHeader } from "./PageHeader";

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.detail || e.message : String(e);
}

export function StrategyControls(): JSX.Element {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const list = useQuery({
    queryKey: ["strategy-controls", "list"],
    queryFn: () => StrategyControlsApi.list(),
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [retireTarget, setRetireTarget] = useState<StrategyControlsLibrarySummary | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const duplicate = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      StrategyControlsApi.duplicate(id, `Copy of ${name}`),
    onSuccess: () => {
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["strategy-controls", "list"] });
    },
    onError: (e) => setActionError(errorText(e)),
  });

  const setDefault = useMutation({
    mutationFn: (id: string) => StrategyControlsApi.setDefault(id),
    onSuccess: () => {
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["strategy-controls", "list"] });
    },
    onError: (e) => setActionError(errorText(e)),
  });

  const retire = useMutation({
    mutationFn: (id: string) => StrategyControlsApi.retire(id),
    onSuccess: () => {
      setActionError(null);
      setRetireTarget(null);
      void qc.invalidateQueries({ queryKey: ["strategy-controls", "list"] });
    },
    onError: (e) => {
      setActionError(errorText(e));
      setRetireTarget(null);
    },
  });

  const libraries = list.data?.libraries ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Strategy Controls"
        subtitle="Reusable session, timing, and concurrency rules. Deployments bind a Controls version."
        explainSlug="strategy-controls"
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setCreateOpen(true)}
          >
            New Library
          </Button>
        }
      />

      {actionError ? (
        <Banner severity="danger" title="Action failed" message={actionError} />
      ) : null}

      {list.isLoading ? (
        <LoadingState title="Loading controls libraries" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load controls libraries"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : libraries.length === 0 ? (
        <EmptyState
          title="No controls libraries yet"
          message="Create a Strategy Controls library to configure session windows, cooldowns, and concurrency caps."
          action={
            <Button size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
              New Library
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {libraries.map((lib) => (
            <ControlsCard
              key={lib.strategy_controls_id}
              lib={lib}
              onEdit={() => navigate(`/controls/${lib.strategy_controls_id}/edit`)}
              onDuplicate={() =>
                duplicate.mutate({ id: lib.strategy_controls_id, name: lib.name })
              }
              onSetDefault={() => setDefault.mutate(lib.strategy_controls_id)}
              onRetire={() => setRetireTarget(lib)}
              busy={duplicate.isPending || setDefault.isPending}
            />
          ))}
        </div>
      )}

      <CreateControlsDrawer
        open={createOpen}
        onOpenChange={setCreateOpen}
      />

      <HoldToArmConfirm
        open={retireTarget != null}
        onOpenChange={(open) => {
          if (!open) setRetireTarget(null);
        }}
        title={`Retire "${retireTarget?.name ?? ""}"?`}
        message={
          <span>
            Retiring marks the library as retired. Deployments already bound to a version are
            unaffected. This cannot be undone. Hold two seconds to confirm.
          </span>
        }
        actionLabel="Retire Library"
        tone="danger"
        busy={retire.isPending}
        onConfirm={async () => {
          if (retireTarget) await retire.mutateAsync(retireTarget.strategy_controls_id);
        }}
      />
    </div>
  );
}

function ControlsCard({
  lib,
  onEdit,
  onDuplicate,
  onSetDefault,
  onRetire,
  busy,
}: {
  lib: StrategyControlsLibrarySummary;
  onEdit: () => void;
  onDuplicate: () => void;
  onSetDefault: () => void;
  onRetire: () => void;
  busy: boolean;
}): JSX.Element {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <div className="min-w-0 flex-1">
          <div className="font-semibold tracking-tight">{lib.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge tone="neutral">v{lib.head_version_number}</StatusBadge>
            {lib.is_default ? (
              <StatusBadge tone="ok">Default</StatusBadge>
            ) : null}
            {lib.retired_at ? (
              <StatusBadge tone="muted">Retired</StatusBadge>
            ) : null}
            <StatusBadge tone="neutral">{lib.usage_count} deployments</StatusBadge>
          </div>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5 border-t border-border/70 px-4 py-2">
        <Button
          size="sm"
          variant="secondary"
          leftIcon={<Pencil className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={onEdit}
          disabled={lib.retired_at != null}
        >
          Edit
        </Button>
        <Button
          size="sm"
          variant="ghost"
          leftIcon={<Copy className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={onDuplicate}
          loading={busy}
        >
          Duplicate
        </Button>
        {!lib.is_default && !lib.retired_at ? (
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Star className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={onSetDefault}
            loading={busy}
          >
            Set default
          </Button>
        ) : null}
        {!lib.retired_at ? (
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Archive className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={onRetire}
          >
            Retire
          </Button>
        ) : null}
      </div>
    </Card>
  );
}

function CreateControlsDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [timeframe, setTimeframe] = useState("5m");
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setName("");
    setTimeframe("5m");
    setError(null);
  }

  const create = useMutation({
    mutationFn: () =>
      StrategyControlsApi.create(name.trim(), {
        name: name.trim(),
        timeframe: timeframe.trim(),
        allowed_directions: "long",
        higher_timeframe_confirmation_required: false,
        session_preference: "regular_only",
        session_windows: [],
        earnings_news_blackout_enabled: false,
        skip_power_hour: false,
        day_of_week_restrictions: [],
        feature_refs: [],
        regime_filter_refs: [],
      }),
    onSuccess: (record) => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["strategy-controls", "list"] });
      navigate(`/controls/${record.payload.strategy_controls_id}/edit`);
    },
    onError: (e) => setError(errorText(e)),
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
          <DrawerTitle>New Controls Library</DrawerTitle>
          <DrawerDescription>
            Give the library a name and default timeframe. You can configure all fields on the
            edit screen.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? (
            <Banner severity="danger" title="Could not create" message={error} />
          ) : null}
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <TextField
            label="Timeframe"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            placeholder="5m"
          />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!name.trim() || !timeframe.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Create
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Copy, Archive, Star, Pencil } from "lucide-react";
import { ApiError } from "@/api/client";
import { ExecutionPlansApi } from "@/api/executionPlans";
import type { ExecutionPlanLibrarySummary } from "@/api/schemas/executionPlans";
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

export function ExecutionPlans(): JSX.Element {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const list = useQuery({
    queryKey: ["execution-plans", "list"],
    queryFn: () => ExecutionPlansApi.list(),
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [retireTarget, setRetireTarget] = useState<ExecutionPlanLibrarySummary | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const duplicate = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      ExecutionPlansApi.duplicate(id, `Copy of ${name}`),
    onSuccess: () => {
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["execution-plans", "list"] });
    },
    onError: (e) => setActionError(errorText(e)),
  });

  const setDefault = useMutation({
    mutationFn: (id: string) => ExecutionPlansApi.setDefault(id),
    onSuccess: () => {
      setActionError(null);
      void qc.invalidateQueries({ queryKey: ["execution-plans", "list"] });
    },
    onError: (e) => setActionError(errorText(e)),
  });

  const retire = useMutation({
    mutationFn: (id: string) => ExecutionPlansApi.retire(id),
    onSuccess: () => {
      setActionError(null);
      setRetireTarget(null);
      void qc.invalidateQueries({ queryKey: ["execution-plans", "list"] });
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
        title="Execution Profiles"
        subtitle="Reusable order type, bracket, and runner rules. Deployments bind an Execution Profile version."
        actions={
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setCreateOpen(true)}
          >
            New Profile
          </Button>
        }
      />

      {actionError ? (
        <Banner severity="danger" title="Action failed" message={actionError} />
      ) : null}

      {list.isLoading ? (
        <LoadingState title="Loading execution profiles" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load execution profiles"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : libraries.length === 0 ? (
        <EmptyState
          title="No execution profiles yet"
          message="Create an Execution Profile to configure order types, bracket placement, and runner mechanics."
          action={
            <Button size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
              New Profile
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {libraries.map((lib) => (
            <ExecutionPlanCard
              key={lib.execution_plan_id}
              lib={lib}
              onEdit={() => navigate(`/execution-plans/${lib.execution_plan_id}/edit`)}
              onDuplicate={() =>
                duplicate.mutate({ id: lib.execution_plan_id, name: lib.name })
              }
              onSetDefault={() => setDefault.mutate(lib.execution_plan_id)}
              onRetire={() => setRetireTarget(lib)}
              busy={duplicate.isPending || setDefault.isPending}
            />
          ))}
        </div>
      )}

      <CreateExecutionPlanDrawer
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
            Retiring marks the profile as retired. Deployments already bound to a version are
            unaffected. This cannot be undone. Hold two seconds to confirm.
          </span>
        }
        actionLabel="Retire Profile"
        tone="danger"
        busy={retire.isPending}
        onConfirm={async () => {
          if (retireTarget) await retire.mutateAsync(retireTarget.execution_plan_id);
        }}
      />
    </div>
  );
}

function ExecutionPlanCard({
  lib,
  onEdit,
  onDuplicate,
  onSetDefault,
  onRetire,
  busy,
}: {
  lib: ExecutionPlanLibrarySummary;
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

function CreateExecutionPlanDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setName("");
    setError(null);
  }

  const create = useMutation({
    mutationFn: () =>
      ExecutionPlansApi.create(name.trim(), {
        name: name.trim(),
        entry_order_type: "market",
        exit_order_type: "market",
        time_in_force: "day",
        bracket: { enabled: false },
        execution_mode: "post_fill_bracket",
        trailing_stop_enabled: false,
        scale_out_enabled: false,
        order_retry_policy: "none",
        order_cancel_policy: "hold",
        feature_refs: [],
      }),
    onSuccess: (record) => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["execution-plans", "list"] });
      navigate(`/execution-plans/${record.payload.execution_style_id}/edit`);
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
          <DrawerTitle>New Execution Profile</DrawerTitle>
          <DrawerDescription>
            Give the profile a name. You can configure all fields on the edit screen.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? (
            <Banner severity="danger" title="Could not create" message={error} />
          ) : null}
          <TextField label="Name" value={name} onChange={(e) => setName(e.target.value)} />
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
            Create
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

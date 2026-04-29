import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Database, Plus, RefreshCw, Star, Trash2, Power } from "lucide-react";
import { AIProvidersApi, MarketDataProvidersApi } from "@/api/providers";
import {
  type AIProvider,
  type AIServiceRecord,
  type AIServiceWrite,
  type MarketDataProvider,
  type MarketDataServiceRecord,
} from "@/api/schemas/providers";
import { ApiError } from "@/api/client";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { DangerConfirm } from "@/components/ui/DangerConfirm";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { PageHeader } from "./PageHeader";
import { relativeTime } from "@/lib/format";

export function Providers(): JSX.Element {
  return (
    <div className="space-y-4">
      <PageHeader
        title="Providers"
        subtitle="Two buckets only. Broker Accounts live on Accounts. AI is advisory only."
        explainSlug="providers"
      />
      <Tabs defaultValue="market">
        <TabsList>
          <TabsTrigger value="market">
            <Database className="h-3.5 w-3.5" aria-hidden="true" />
            Market Data Providers
          </TabsTrigger>
          <TabsTrigger value="ai">
            <Brain className="h-3.5 w-3.5" aria-hidden="true" />
            AI Providers
          </TabsTrigger>
        </TabsList>
        <TabsContent value="market">
          <MarketDataProvidersTab />
        </TabsContent>
        <TabsContent value="ai">
          <AIProvidersTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---------- Market Data ----------

function MarketDataProvidersTab(): JSX.Element {
  const list = useQuery({
    queryKey: ["providers", "market-data"],
    queryFn: () => MarketDataProvidersApi.list(),
    refetchInterval: 30_000,
  });
  const [createOpen, setCreateOpen] = useState(false);

  if (list.isLoading) return <LoadingState title="Loading Market Data Providers" />;
  if (list.isError)
    return (
      <ErrorState
        title="Could not load providers"
        detail={(list.error as Error)?.message}
        onRetry={() => list.refetch()}
      />
    );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Market Data Providers</CardTitle>
        <span className="flex items-center gap-2">
          <StatusBadge>{list.data?.services.length ?? 0}</StatusBadge>
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setCreateOpen(true)}
          >
            Add Market Data Provider
          </Button>
        </span>
      </CardHeader>
      <CardBody className={(list.data?.services.length ?? 0) === 0 ? "" : "grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"}>
        {(list.data?.services.length ?? 0) === 0 ? (
          <EmptyState
            title="No Market Data Providers configured"
            message="Add a Market Data Provider — Alpaca for stock streams or Yahoo for historical."
            action={
              <Button size="sm" variant="primary" onClick={() => setCreateOpen(true)}>
                Add Market Data Provider
              </Button>
            }
          />
        ) : (
          list.data?.services.map((s) => <MarketDataProviderCard key={s.id} service={s} />)
        )}
      </CardBody>
      <CreateMarketDataProviderDrawer open={createOpen} onOpenChange={setCreateOpen} />
    </Card>
  );
}

function CreateMarketDataProviderDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [provider, setProvider] = useState<MarketDataProvider>("alpaca");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setName("");
    setProvider("alpaca");
    setApiKey("");
    setApiSecret("");
    setError(null);
  }

  const create = useMutation({
    mutationFn: () =>
      MarketDataProvidersApi.create({
        name: name.trim(),
        provider,
        api_key: apiKey.trim() || null,
        api_secret: apiSecret.trim() || null,
      }),
    onSuccess: () => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["providers", "market-data"] });
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  const credsRequired = provider === "alpaca";
  const formValid = name.trim().length > 0 && (!credsRequired || (apiKey.trim() && apiSecret.trim()));

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
          <DrawerTitle>Add Market Data Provider</DrawerTitle>
          <DrawerDescription>
            Alpaca powers live stock streams (and historical). Yahoo is historical-only.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not create" message={error} /> : null}
          <TextField label="Display name" value={name} onChange={(e) => setName(e.target.value)} />
          <Select label="Provider" value={provider} onChange={(e) => setProvider(e.target.value as MarketDataProvider)}>
            <option value="alpaca">Alpaca (live + historical)</option>
            <option value="yahoo">Yahoo (historical only)</option>
          </Select>
          {credsRequired ? (
            <>
              <TextField label="API Key" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
              <TextField
                label="API Secret"
                type="password"
                autoComplete="off"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
              />
            </>
          ) : (
            <Banner severity="info" title="Yahoo needs no credentials" message="Public historical-only data." />
          )}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!formValid}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Add Provider
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function MarketDataProviderCard({ service }: { service: MarketDataServiceRecord }): JSX.Element {
  const qc = useQueryClient();
  const validate = useMutation({
    mutationFn: () => MarketDataProvidersApi.validate(service.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["providers", "market-data"] }),
  });
  const setDefault = useMutation({
    mutationFn: () => MarketDataProvidersApi.setDefault(service.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["providers", "market-data"] }),
  });
  const disable = useMutation({
    mutationFn: () => MarketDataProvidersApi.disable(service.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["providers", "market-data"] }),
  });
  const enable = useMutation({
    mutationFn: () => MarketDataProvidersApi.enable(service.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["providers", "market-data"] }),
  });

  const isOk = service.validation_status === "valid";
  const isDisabled = service.status === "disabled" || service.disabled_at != null;

  return (
    <Card>
      <div className="flex items-start justify-between gap-2 px-4 pt-3">
        <div>
          <div className="font-semibold tracking-tight">{service.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge tone="info">{service.provider}</StatusBadge>
            {service.is_default ? <StatusBadge tone="ok">Default</StatusBadge> : null}
            {service.default_for.map((p) => (
              <StatusBadge key={p} tone="info">{p.replaceAll("_", " ")}</StatusBadge>
            ))}
            {service.has_api_key ? (
              <StatusBadge tone="ok">Credentials</StatusBadge>
            ) : (
              <StatusBadge tone="warn">No Credentials</StatusBadge>
            )}
            <StatusBadge tone={isOk ? "ok" : isDisabled ? "muted" : "warn"}>
              {service.validation_status ?? "not validated"}
            </StatusBadge>
          </div>
        </div>
      </div>
      <div className="px-4 py-2 text-xs text-fg-muted">
        Last validated: {service.last_validated_at ? relativeTime(service.last_validated_at) : "never"}
      </div>
      {service.validation_message ? (
        <div className="mx-4 mb-2"><Banner severity={isOk ? "info" : "warning"} title={service.validation_message} /></div>
      ) : null}
      <div className="flex flex-wrap gap-1 border-t border-border/70 px-4 py-2">
        <Button
          size="sm"
          variant="secondary"
          leftIcon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />}
          onClick={() => validate.mutate()}
          loading={validate.isPending}
        >
          Validate
        </Button>
        {!service.is_default ? (
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Star className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setDefault.mutate()}
            loading={setDefault.isPending}
          >
            Set Default
          </Button>
        ) : null}
        {!isDisabled ? (
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Power className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => disable.mutate()}
            loading={disable.isPending}
          >
            Disable
          </Button>
        ) : (
          <>
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Power className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => enable.mutate()}
              loading={enable.isPending}
            >
              Enable
            </Button>
            <StatusBadge tone="muted">Disabled</StatusBadge>
          </>
        )}
      </div>
    </Card>
  );
}

// ---------- AI Providers ----------

function AIProvidersTab(): JSX.Element {
  const list = useQuery({
    queryKey: ["providers", "ai"],
    queryFn: () => AIProvidersApi.list(),
    refetchInterval: 30_000,
  });
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI Providers</CardTitle>
        <span className="flex items-center gap-2">
          <StatusBadge tone="ai">Advisory Only</StatusBadge>
          <Button
            size="sm"
            variant="primary"
            leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => setCreateOpen(true)}
          >
            Add AI Provider
          </Button>
        </span>
      </CardHeader>
      <CardBody className={(list.data?.services.length ?? 0) === 0 ? "" : "grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3"}>
        {list.isLoading ? (
          <LoadingState title="Loading AI providers" />
        ) : list.isError ? (
          <ErrorState
            title="Could not load AI providers"
            detail={(list.error as Error)?.message}
            onRetry={() => list.refetch()}
          />
        ) : (list.data?.services.length ?? 0) === 0 ? (
          <EmptyState title="No AI Providers" message="Add an AI Provider to enable advisory features." />
        ) : (
          list.data?.services.map((s) => <AIProviderCard key={s.id} service={s} />)
        )}
      </CardBody>
      <CreateAIProviderDrawer open={createOpen} onOpenChange={setCreateOpen} />
    </Card>
  );
}

function AIProviderCard({ service }: { service: AIServiceRecord }): JSX.Element {
  const qc = useQueryClient();
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const validate = useMutation({
    mutationFn: () => AIProvidersApi.validate(service.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["providers", "ai"] }),
  });
  const setDefault = useMutation({
    mutationFn: () => AIProvidersApi.setDefault(service.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["providers", "ai"] }),
  });
  const disable = useMutation({
    mutationFn: () => AIProvidersApi.disable(service.id),
    onSettled: () => qc.invalidateQueries({ queryKey: ["providers", "ai"] }),
  });
  const remove = useMutation({
    mutationFn: () => AIProvidersApi.delete(service.id, service.name),
    onSettled: () => qc.invalidateQueries({ queryKey: ["providers", "ai"] }),
  });

  const isOk = service.validation_status === "valid";

  return (
    <Card>
      <div className="flex items-start justify-between gap-2 px-4 pt-3">
        <div>
          <div className="font-semibold tracking-tight">{service.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge tone="ai">{service.provider}</StatusBadge>
            <StatusBadge tone="ai">Advisory Only</StatusBadge>
            {service.is_default ? <StatusBadge tone="ok">Default</StatusBadge> : null}
            {service.has_api_key ? (
              <StatusBadge tone="ok">Credentials</StatusBadge>
            ) : (
              <StatusBadge tone="warn">No Credentials</StatusBadge>
            )}
            <StatusBadge tone={isOk ? "ok" : "warn"}>{service.validation_status ?? "not validated"}</StatusBadge>
            <StatusBadge tone="muted">{service.capability_label}</StatusBadge>
          </div>
        </div>
      </div>
      <div className="px-4 py-2 text-xs text-fg-muted">
        Last validated: {service.last_validated_at ? relativeTime(service.last_validated_at) : "never"}
      </div>
      <div className="flex flex-wrap gap-1 border-t border-border/70 px-4 py-2">
        <Button size="sm" variant="secondary" leftIcon={<RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />} onClick={() => validate.mutate()} loading={validate.isPending}>
          Validate
        </Button>
        {!service.is_default ? (
          <Button size="sm" variant="ghost" leftIcon={<Star className="h-3.5 w-3.5" aria-hidden="true" />} onClick={() => setDefault.mutate()} loading={setDefault.isPending}>
            Set Default
          </Button>
        ) : null}
        <Button size="sm" variant="ghost" onClick={() => setEditOpen(true)}>
          Edit
        </Button>
        <Button size="sm" variant="ghost" leftIcon={<Power className="h-3.5 w-3.5" aria-hidden="true" />} onClick={() => disable.mutate()} loading={disable.isPending}>
          Disable
        </Button>
        <Button size="sm" variant="danger" leftIcon={<Trash2 className="h-3.5 w-3.5" aria-hidden="true" />} onClick={() => setDeleteOpen(true)}>
          Delete
        </Button>
      </div>

      <EditAIProviderDrawer open={editOpen} onOpenChange={setEditOpen} service={service} />
      <DangerConfirm
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title={`Delete AI provider "${service.name}"?`}
        message={<span>Type <strong>{service.name}</strong> to confirm.</span>}
        expected={service.name}
        actionLabel="Delete AI Provider"
        tone="danger"
        busy={remove.isPending}
        onConfirm={async () => {
          await remove.mutateAsync();
          setDeleteOpen(false);
        }}
      />
    </Card>
  );
}

function aiServiceWriteFromForm(form: { name: string; provider: AIProvider; apiKey: string; capability: AIServiceWrite["capability_label"] }): AIServiceWrite {
  return {
    name: form.name.trim(),
    provider: form.provider,
    api_key: form.apiKey.trim() ? form.apiKey.trim() : null,
    capability_label: form.capability,
  };
}

function CreateAIProviderDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [provider, setProvider] = useState<AIProvider>("claude");
  const [apiKey, setApiKey] = useState("");
  const [capability, setCapability] = useState<AIServiceWrite["capability_label"]>("reasoning");
  const [error, setError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => AIProvidersApi.create(aiServiceWriteFromForm({ name, provider, apiKey, capability })),
    onSuccess: () => {
      setName("");
      setApiKey("");
      void qc.invalidateQueries({ queryKey: ["providers", "ai"] });
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Add AI Provider</DrawerTitle>
          <DrawerDescription>AI is advisory only. It cannot submit, modify, or override broker truth.</DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not create" message={error} /> : null}
          <TextField label="Display name" value={name} onChange={(e) => setName(e.target.value)} />
          <Select label="Provider" value={provider} onChange={(e) => setProvider(e.target.value as AIProvider)}>
            <option value="claude">Claude (Anthropic)</option>
            <option value="openai">OpenAI</option>
            <option value="groq">Groq</option>
            <option value="codex">Codex</option>
            <option value="future">Future provider</option>
          </Select>
          <Select label="Capability" value={capability} onChange={(e) => setCapability(e.target.value as AIServiceWrite["capability_label"])}>
            <option value="reasoning">reasoning</option>
            <option value="fast">fast</option>
            <option value="coding">coding</option>
            <option value="general">general</option>
            <option value="unknown">unknown</option>
          </Select>
          <TextField label="API Key (optional at create)" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" disabled={!name.trim()} loading={create.isPending} onClick={() => create.mutate()}>
            Create AI Provider
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function EditAIProviderDrawer({
  open,
  onOpenChange,
  service,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  service: AIServiceRecord;
}): JSX.Element {
  const qc = useQueryClient();
  const [name, setName] = useState(service.name);
  const [provider, setProvider] = useState<AIProvider>(service.provider);
  const [apiKey, setApiKey] = useState("");
  const [capability, setCapability] = useState(service.capability_label);
  const [error, setError] = useState<string | null>(null);

  const update = useMutation({
    mutationFn: () => AIProvidersApi.update(service.id, aiServiceWriteFromForm({ name, provider, apiKey, capability })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["providers", "ai"] });
      onOpenChange(false);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Edit AI Provider · {service.name}</DrawerTitle>
          <DrawerDescription>Leave the API key blank to keep the current one.</DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Update failed" message={error} /> : null}
          <TextField label="Display name" value={name} onChange={(e) => setName(e.target.value)} />
          <Select label="Provider" value={provider} onChange={(e) => setProvider(e.target.value as AIProvider)}>
            <option value="claude">Claude (Anthropic)</option>
            <option value="openai">OpenAI</option>
            <option value="groq">Groq</option>
            <option value="codex">Codex</option>
            <option value="future">Future provider</option>
          </Select>
          <Select label="Capability" value={capability} onChange={(e) => setCapability(e.target.value as AIServiceWrite["capability_label"])}>
            <option value="reasoning">reasoning</option>
            <option value="fast">fast</option>
            <option value="coding">coding</option>
            <option value="general">general</option>
            <option value="unknown">unknown</option>
          </Select>
          <TextField label="Replace API Key (optional)" type="password" autoComplete="off" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button variant="primary" size="sm" disabled={!name.trim()} loading={update.isPending} onClick={() => update.mutate()}>
            Save
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

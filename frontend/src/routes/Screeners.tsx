import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Filter, Library, ListFilter, Play, Plus, Sparkles } from "lucide-react";
import { ApiError } from "@/api/client";
import { ScreenerApi } from "@/api/screener";
import type {
  MarketListDefinition,
  Screener,
  ScreenerAIInterpretResponse,
  ScreenerCreateRequest,
  ScreenerTemplate,
} from "@/api/schemas/screener";
import { Banner } from "@/components/ui/Banner";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
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
import { CriteriaEditor } from "@/components/screener/CriteriaEditor";
import { ExpressionPreview } from "@/components/screener/ExpressionPreview";
import { UniverseSourcePicker } from "@/components/screener/UniverseSourcePicker";
import { PageHeader } from "./PageHeader";
import { relativeTime } from "@/lib/format";

/**
 * Screeners list + creation surface.
 *
 * Doctrine guards:
 * - Screeners are discovery only.
 * - Market lists are an Alpaca provider pack, not core architecture.
 * - AI is advisory only and compiles into visible typed rules before create.
 */
export function Screeners(): JSX.Element {
  const list = useQuery({
    queryKey: ["screeners", "list"],
    queryFn: () => ScreenerApi.list(),
    refetchInterval: 30_000,
  });
  const templates = useQuery({
    queryKey: ["screeners", "templates"],
    queryFn: () => ScreenerApi.templates(),
    staleTime: 5 * 60_000,
  });
  const marketLists = useQuery({
    queryKey: ["screeners", "market-lists"],
    queryFn: () => ScreenerApi.marketLists(),
    staleTime: 5 * 60_000,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [screenerQuery, setScreenerQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | Screener["status"]>("all");
  const [sortBy, setSortBy] = useState<"last_run" | "created" | "name">("last_run");
  const screeners = list.data?.screeners ?? [];
  const filteredScreeners = useMemo(() => {
    const text = screenerQuery.trim().toLowerCase();
    return screeners
      .filter((s) => (statusFilter === "all" ? true : s.status === statusFilter))
      .filter((s) => (text ? screenerSearchText(s).includes(text) : true))
      .sort((a, b) => compareScreeners(a, b, sortBy));
  }, [screeners, screenerQuery, statusFilter, sortBy]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Screeners"
        subtitle="Discovery surface. Run Alpaca-first lists, templates, or typed criteria; save entries as Watchlists only when the operator chooses."
        explainSlug="screeners"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Bot className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setAiOpen(true)}
            >
              AI Composer
            </Button>
            <Button
              size="sm"
              variant="primary"
              leftIcon={<Plus className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setCreateOpen(true)}
            >
              New Screener
            </Button>
          </div>
        }
      />

      <div className="grid grid-cols-1 gap-3 xl:grid-cols-[1.25fr_1fr]">
        <MarketListsPanel
          marketLists={marketLists.data?.market_lists ?? []}
          loading={marketLists.isLoading}
          loadError={marketLists.isError ? errorText(marketLists.error) : null}
          onRetry={() => marketLists.refetch()}
        />
        <TemplateLibrary templates={templates.data?.templates ?? []} loading={templates.isLoading} />
      </div>

      <Banner
        severity="info"
        title="Entry discovery only"
        message="Watchlists created here feed entries. Exits still come from Account-owned Positions scoped by deployment."
      />

      {screeners.length > 0 ? (
        <div className="grid grid-cols-1 gap-2 rounded border border-border bg-bg-raised p-3 md:grid-cols-[1fr_12rem_12rem]">
          <TextField
            label="Search saved screeners"
            value={screenerQuery}
            onChange={(event) => setScreenerQuery(event.target.value)}
            placeholder="name, tag, description"
          />
          <Select
            label="Status"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value as typeof statusFilter)}
          >
            <option value="all">All statuses</option>
            <option value="active">Active</option>
            <option value="draft">Draft</option>
            <option value="deprecated">Deprecated</option>
            <option value="archived">Archived</option>
          </Select>
          <Select
            label="Sort"
            value={sortBy}
            onChange={(event) => setSortBy(event.target.value as typeof sortBy)}
          >
            <option value="last_run">Last run</option>
            <option value="created">Created</option>
            <option value="name">Name</option>
          </Select>
          <div className="text-[11px] text-fg-subtle md:col-span-3">
            Showing {filteredScreeners.length} of {screeners.length} saved screeners
          </div>
        </div>
      ) : null}

      {list.isLoading ? (
        <LoadingState title="Loading screeners" />
      ) : list.isError ? (
        <ErrorState
          title="Could not load screeners"
          detail={(list.error as Error)?.message}
          onRetry={() => list.refetch()}
        />
      ) : screeners.length === 0 ? (
        <EmptyState
          title="No saved screeners yet"
          message="Run an Alpaca market list, start from a template, use AI Composer, or create typed criteria manually."
          action={
            <Button
              size="sm"
              variant="primary"
              onClick={() => setCreateOpen(true)}
              leftIcon={<Filter className="h-3.5 w-3.5" aria-hidden="true" />}
            >
              New Screener
            </Button>
          }
        />
      ) : filteredScreeners.length === 0 ? (
        <EmptyState
          title="No screeners match"
          message="Adjust search, status, or sort to bring saved screeners back into view."
        />
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {filteredScreeners.map((s) => <ScreenerCard key={s.id} screener={s} />)}
        </div>
      )}

      <CreateScreenerDrawer open={createOpen} onOpenChange={setCreateOpen} />
      <AiComposerDrawer open={aiOpen} onOpenChange={setAiOpen} />
    </div>
  );
}

function MarketListsPanel({
  marketLists,
  loading,
  loadError,
  onRetry,
}: {
  marketLists: MarketListDefinition[];
  loading: boolean;
  loadError: string | null;
  onRetry: () => void;
}): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const runList = useMutation({
    mutationFn: (key: string) => ScreenerApi.runMarketList(key),
    onSuccess: (resp) => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["screeners"] });
      navigate(`/screeners/${resp.screener.id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ListFilter className="h-4 w-4 text-accent" aria-hidden="true" />
          Alpaca Market Lists
        </CardTitle>
        <StatusBadge tone="info">provider pack</StatusBadge>
      </CardHeader>
      <CardBody className="space-y-2">
        {error ? <Banner severity="danger" title="Market list run failed" message={error} /> : null}
        <div className="text-xs text-fg-muted">
          Premarket/open-hour movers and most-active lists resolve through Alpaca data and asset capability evidence.
        </div>
        {loading ? <LoadingState title="Loading market lists" /> : null}
        {loadError ? (
          <ErrorState
            title="Alpaca market lists unavailable"
            detail={loadError}
            onRetry={onRetry}
          />
        ) : null}
        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
          {marketLists.map((m) => (
            <div key={m.key} className="rounded border border-border bg-bg-inset/40 px-3 py-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="font-medium">{m.label}</div>
                  <div className="mt-0.5 text-[11px] text-fg-muted">{m.description}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    <StatusBadge tone="neutral" size="sm">
                      {m.category}
                    </StatusBadge>
                    <StatusBadge tone="info" size="sm">
                      {m.provider}
                    </StatusBadge>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={runList.isPending}
                  leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
                  onClick={() => runList.mutate(m.key)}
                >
                  Run
                </Button>
              </div>
            </div>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}

function TemplateLibrary({
  templates,
  loading,
}: {
  templates: ScreenerTemplate[];
  loading: boolean;
}): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const filteredTemplates = useMemo(() => {
    const text = query.trim().toLowerCase();
    if (!text) return templates;
    return templates.filter((t) =>
      [t.label, t.description, t.category, ...t.tags].join(" ").toLowerCase().includes(text),
    );
  }, [query, templates]);
  const visibleTemplates = showAll || query.trim() ? filteredTemplates : filteredTemplates.slice(0, 6);
  const create = useMutation({
    mutationFn: (templateKey: string) =>
      ScreenerApi.createFromTemplate({ template_key: templateKey, name: null, tags: [] }),
    onSuccess: (resp) => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["screeners"] });
      navigate(`/screeners/${resp.screener.id}`);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Library className="h-4 w-4 text-accent" aria-hidden="true" />
          Templates
        </CardTitle>
        <StatusBadge tone="neutral">{templates.length}</StatusBadge>
      </CardHeader>
      <CardBody className="space-y-2">
        {error ? <Banner severity="danger" title="Template create failed" message={error} /> : null}
        {loading ? <LoadingState title="Loading templates" /> : null}
        <TextField
          label="Search templates"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="fractionable, momentum, gap"
        />
        {visibleTemplates.map((t) => (
          <div key={t.key} className="flex items-start justify-between gap-2 rounded border border-border bg-bg-inset/40 px-3 py-2">
            <div className="min-w-0">
              <div className="font-medium">{t.label}</div>
              <div className="mt-0.5 text-[11px] text-fg-muted">{t.description}</div>
              <div className="mt-1 flex flex-wrap gap-1">
                <StatusBadge tone="neutral" size="sm">
                  {t.category}
                </StatusBadge>
                {t.tags.slice(0, 2).map((tag) => (
                  <StatusBadge key={tag} tone="muted" size="sm">
                    {tag}
                  </StatusBadge>
                ))}
              </div>
            </div>
            <Button
              size="sm"
              variant="secondary"
              loading={create.isPending}
              onClick={() => create.mutate(t.key)}
            >
              Use
            </Button>
          </div>
        ))}
        {!query.trim() && templates.length > 6 ? (
          <Button size="sm" variant="ghost" onClick={() => setShowAll((current) => !current)}>
            {showAll ? "Show fewer templates" : `Show all ${templates.length} templates`}
          </Button>
        ) : null}
      </CardBody>
    </Card>
  );
}

function ScreenerCard({ screener }: { screener: Screener }): JSX.Element {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <div className="min-w-0">
          <div className="font-semibold tracking-tight">{screener.name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <StatusBadge
              tone={
                screener.status === "archived" || screener.status === "deprecated"
                  ? "muted"
                  : screener.status === "active"
                  ? "ok"
                  : "info"
              }
            >
              {prettyKey(screener.status)}
            </StatusBadge>
            <StatusBadge tone="neutral">{screener.version_count} versions</StatusBadge>
            {screener.last_run_at ? (
              <span title={screener.last_run_at}>
                <StatusBadge tone="info">last run {relativeTime(screener.last_run_at)}</StatusBadge>
              </span>
            ) : (
              <StatusBadge tone="warn">never run</StatusBadge>
            )}
          </div>
        </div>
      </div>
      {screener.description ? (
        <div className="px-4 py-2 text-xs text-fg-muted">{screener.description}</div>
      ) : null}
      {screener.tags.length ? (
        <div className="px-4 pb-2 text-[11px] text-fg-subtle">{screener.tags.join(" / ")}</div>
      ) : null}
      <div className="flex items-center justify-between border-t border-border/70 px-4 py-2 text-xs text-fg-muted">
        <span>{relativeTime(screener.created_at)}</span>
        <Link to={`/screeners/${screener.id}`}>
          <Button size="sm" variant="secondary">
            Open
          </Button>
        </Link>
      </div>
    </Card>
  );
}

function screenerSearchText(screener: Screener): string {
  return [
    screener.name,
    screener.description ?? "",
    screener.status,
    ...screener.tags,
  ].join(" ").toLowerCase();
}

function compareScreeners(a: Screener, b: Screener, sortBy: "last_run" | "created" | "name"): number {
  if (sortBy === "name") return a.name.localeCompare(b.name);
  const aTime = Date.parse(sortBy === "last_run" ? a.last_run_at ?? a.created_at : a.created_at);
  const bTime = Date.parse(sortBy === "last_run" ? b.last_run_at ?? b.created_at : b.created_at);
  return bTime - aTime;
}

function CreateScreenerDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const fields = useQuery({
    queryKey: ["screener", "fields"],
    queryFn: () => ScreenerApi.fields(),
    staleTime: 5 * 60_000,
  });

  const [form, setForm] = useState<ScreenerCreateRequest>(() => emptyCreateForm());
  const [tagsDraft, setTagsDraft] = useState("");
  const [maxResultsDraft, setMaxResultsDraft] = useState(String(emptyCreateForm().max_results));
  const [error, setError] = useState<string | null>(null);

  function reset(): void {
    setForm(emptyCreateForm());
    setTagsDraft("");
    setMaxResultsDraft(String(emptyCreateForm().max_results));
    setError(null);
  }

  const create = useMutation({
    mutationFn: () => ScreenerApi.create(form),
    onSuccess: () => {
      reset();
      onOpenChange(false);
      void qc.invalidateQueries({ queryKey: ["screeners", "list"] });
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
      <DrawerContent className="max-w-3xl">
        <DrawerHeader>
          <DrawerTitle>New Screener</DrawerTitle>
          <DrawerDescription>
            Pick a universe source and visible typed criteria. The Screener remains discovery only.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="Could not create screener" message={error} /> : null}
          <TextField
            label="Display name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Alpaca Fractionable Movers"
          />
          <TextField
            label="Description (optional)"
            value={form.description ?? ""}
            onChange={(e) => setForm({ ...form, description: e.target.value || null })}
            placeholder="Day gainers with broker capability gates"
          />
          <UniverseSourcePicker
            value={form.universe_source}
            onChange={(next) => setForm({ ...form, universe_source: next })}
          />
          <CriteriaEditor
            value={form.criteria}
            onChange={(next) => setForm({ ...form, criteria: next, expression: null })}
            metrics={fields.data?.fields ?? []}
          />
          <details className="rounded border border-border bg-bg-inset/40 p-2">
            <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
              Advanced run settings
            </summary>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              <Select
                label="Timeframe"
                value={form.timeframe}
                onChange={(e) => setForm({ ...form, timeframe: e.target.value })}
              >
                <option value="1m">1 minute</option>
                <option value="5m">5 minutes</option>
                <option value="15m">15 minutes</option>
                <option value="1h">1 hour</option>
                <option value="1d">1 day</option>
              </Select>
              <Select
                label="Source preference"
                value={form.source_preference}
                onChange={(e) =>
                  setForm({
                    ...form,
                    source_preference: e.target.value as ScreenerCreateRequest["source_preference"],
                  })
                }
              >
                <option value="auto">Auto: Alpaca first, Data Center fallback</option>
                <option value="alpaca">Alpaca provider evidence</option>
                <option value="data_center">Data Center cache only</option>
              </Select>
              <Select
                label="Sort metric"
                value={form.sort_metric ?? ""}
                onChange={(e) =>
                  setForm({
                    ...form,
                    sort_metric: (e.target.value || null) as ScreenerCreateRequest["sort_metric"],
                  })
                }
              >
                <option value="">Matched first</option>
                {(fields.data?.fields ?? []).map((field) => (
                  <option key={field.key} value={field.key}>
                    {field.label}
                  </option>
                ))}
              </Select>
              <Select
                label="Sort direction"
                value={form.sort_descending ? "desc" : "asc"}
                onChange={(e) => setForm({ ...form, sort_descending: e.target.value === "desc" })}
              >
                <option value="desc">High to low</option>
                <option value="asc">Low to high</option>
              </Select>
              <TextField
                label="Max results"
                type="number"
                value={maxResultsDraft}
                onChange={(e) => {
                  const value = e.target.value;
                  setMaxResultsDraft(value);
                  if (value.trim()) setForm({ ...form, max_results: Math.max(1, Number(value)) });
                }}
              />
              <TextField
                label="Tags"
                value={tagsDraft}
                onChange={(e) => {
                  setTagsDraft(e.target.value);
                  setForm({ ...form, tags: parseTags(e.target.value) });
                }}
                placeholder="intraday, alpaca"
              />
            </div>
          </details>
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!form.name.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Create Screener
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function AiComposerDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (b: boolean) => void;
}): JSX.Element {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [prompt, setPrompt] = useState("Alpaca day gainers that are tradable and fractionable with relative volume above 1.5");
  const [name, setName] = useState("AI composed Alpaca movers");
  const [draft, setDraft] = useState<ScreenerAIInterpretResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const labels = useMemo(() => (draft ? expressionLabels(draft.expression) : []), [draft]);

  function reset(): void {
    setDraft(null);
    setError(null);
  }

  const interpret = useMutation({
    mutationFn: () => ScreenerApi.interpretAi({ prompt }),
    onSuccess: (resp) => {
      setDraft(resp);
      setError(null);
    },
    onError: (e) => setError(e instanceof ApiError ? e.detail || e.message : String(e)),
  });
  const create = useMutation({
    mutationFn: () => {
      if (!draft) throw new Error("No AI draft has been compiled yet.");
      return ScreenerApi.create({
        ...emptyCreateForm(),
        name: name.trim(),
        description: `AI advisory prompt: ${prompt}`,
        universe_source: draft.universe_source,
        criteria: [],
        expression: draft.expression,
        source_preference: "auto",
      });
    },
    onSuccess: (resp) => {
      void qc.invalidateQueries({ queryKey: ["screeners"] });
      onOpenChange(false);
      reset();
      navigate(`/screeners/${resp.screener.id}`);
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
      <DrawerContent className="max-w-2xl">
        <DrawerHeader>
          <DrawerTitle>AI Composer</DrawerTitle>
          <DrawerDescription>
            AI is advisory only. It compiles the prompt into visible typed rules before anything is saved.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-3">
          {error ? <Banner severity="danger" title="AI composer failed" message={error} /> : null}
          <TextField label="Screener name" value={name} onChange={(e) => setName(e.target.value)} />
          <label className="block text-xs">
            <span className="text-fg-muted">Prompt</span>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={4}
              className="mt-1 block w-full rounded border border-border bg-bg-inset px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
            />
          </label>
          <Button
            size="sm"
            variant="secondary"
            loading={interpret.isPending}
            leftIcon={<Sparkles className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => interpret.mutate()}
            disabled={!prompt.trim()}
          >
            Compile advisory rules
          </Button>
          {draft ? (
            <div className="space-y-2 rounded border border-border bg-bg-inset/40 p-3">
              <div className="flex flex-wrap gap-1">
                <StatusBadge tone="ai">advisory</StatusBadge>
                <StatusBadge tone="neutral">{describeUniverseFromSource(draft.universe_source)}</StatusBadge>
              </div>
              <ExpressionPreview expression={draft.expression} title="Compiled boolean tree" />
              {labels.length ? (
                <div className="text-[11px] text-fg-muted">
                  Rule leaves: {labels.join(" / ")}
                </div>
              ) : null}
              {draft.assumptions.length ? (
                <div className="text-[11px] text-fg-muted">
                  Assumptions: {draft.assumptions.join(" / ")}
                </div>
              ) : null}
              {draft.unsupported_clauses.length ? (
                <Banner
                  severity="warning"
                  title="Unsupported clauses"
                  message={draft.unsupported_clauses.join(" / ")}
                />
              ) : null}
            </div>
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            disabled={!draft || !name.trim()}
            loading={create.isPending}
            onClick={() => create.mutate()}
          >
            Create from compiled rules
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function emptyCreateForm(): ScreenerCreateRequest {
  return {
    name: "",
    description: null,
    tags: [],
    universe_source: { kind: "market_list", symbols: [], market_list_key: "day_gainers" },
    criteria: [
      { metric: "relative_volume", operator: "gte", value: 1.5, value_max: null, label: null },
      { metric: "broker.tradable", operator: "eq", value: true, value_max: null, label: null },
      { metric: "broker.fractionable", operator: "eq", value: true, value_max: null, label: null },
    ],
    expression: null,
    timeframe: "1d",
    source_preference: "auto",
    sort_metric: "relative_volume",
    sort_descending: true,
    max_results: 200,
  };
}

function expressionLabels(expr: unknown): string[] {
  const node = expr as {
    kind?: string;
    criterion?: { metric?: string; operator?: string; value?: unknown; value_max?: unknown; label?: string | null };
    children?: unknown[];
  };
  if (!node || typeof node !== "object") return [];
  if (node.kind === "criterion" && node.criterion) {
    const c = node.criterion;
    const value = c.operator === "between" ? `${String(c.value)} to ${String(c.value_max)}` : String(c.value);
    return [c.label || `${c.metric ?? "field"} ${c.operator ?? "="} ${value}`];
  }
  return (node.children ?? []).flatMap(expressionLabels);
}

function describeUniverseFromSource(source: { kind: string; preset?: string | null; market_list_key?: string | null; symbols?: string[] }): string {
  if (source.kind === "market_list") return `Alpaca list: ${prettyKey(source.market_list_key ?? "market_list")}`;
  if (source.kind === "preset") return `Preset: ${prettyKey(source.preset ?? "preset")}`;
  if (source.kind === "explicit") return `${source.symbols?.length ?? 0} explicit symbols`;
  return "Watchlist source";
}

function prettyKey(key: string): string {
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function parseTags(value: string): string[] {
  return Array.from(
    new Set(
      value
        .split(/[,\s]+/)
        .map((tag) => tag.trim())
        .filter(Boolean),
    ),
  );
}

function errorText(e: unknown): string {
  return e instanceof ApiError ? e.detail || e.message : e instanceof Error ? e.message : String(e);
}

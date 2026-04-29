import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  BarChart3,
  Bot,
  CalendarClock,
  Filter,
  Library,
  ListFilter,
  Play,
  Plus,
  Settings2,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { ApiError } from "@/api/client";
import { DiscoverySchedulesApi } from "@/api/discoverySchedules";
import { ScreenerApi } from "@/api/screener";
import type { DiscoverySchedule } from "@/api/schemas/discoverySchedules";
import type {
  MarketListDefinition,
  Screener,
  ScreenerAIInterpretResponse,
  ScreenerCreateRequest,
  ScreenerPreset,
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
import { StatusBadge, type StatusTone } from "@/components/badges/StatusBadge";
import { LoadingState } from "@/components/empty/LoadingState";
import { ErrorState } from "@/components/empty/ErrorState";
import { EmptyState } from "@/components/empty/EmptyState";
import { CriteriaEditor } from "@/components/screener/CriteriaEditor";
import { ExpressionPreview } from "@/components/screener/ExpressionPreview";
import { UniverseSourcePicker } from "@/components/screener/UniverseSourcePicker";
import { PageHeader } from "./PageHeader";
import { formatTimestamp, relativeTime } from "@/lib/format";

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
  const presets = useQuery({
    queryKey: ["screeners", "presets"],
    queryFn: () => ScreenerApi.presets(),
    staleTime: 5 * 60_000,
  });
  const marketLists = useQuery({
    queryKey: ["screeners", "market-lists"],
    queryFn: () => ScreenerApi.marketLists(),
    staleTime: 5 * 60_000,
  });
  const schedules = useQuery({
    queryKey: ["discovery-schedules", "list"],
    queryFn: () => DiscoverySchedulesApi.list(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const [createOpen, setCreateOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [templateOpen, setTemplateOpen] = useState(false);
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
        subtitle="Discovery surface. Live Alpaca lists run now; templates are optional starters; saved Screeners can be scheduled and then saved as entry Watchlists."
        explainSlug="screeners"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<Library className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={() => setTemplateOpen(true)}
            >
              Browse templates
            </Button>
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

      <MarketListsPanel
        marketLists={marketLists.data?.market_lists ?? []}
        loading={marketLists.isLoading}
        loadError={marketLists.isError ? errorText(marketLists.error) : null}
        onRetry={() => marketLists.refetch()}
      />

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
          message="Run a live Alpaca market list, browse starter templates, use AI Composer, or create typed criteria manually."
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
          {filteredScreeners.map((s) => (
            <ScreenerCard
              key={s.id}
              screener={s}
              schedules={schedulesForScreener(s, schedules.data?.schedules ?? [])}
            />
          ))}
        </div>
      )}

      <CreateScreenerDrawer open={createOpen} onOpenChange={setCreateOpen} />
      <AiComposerDrawer open={aiOpen} onOpenChange={setAiOpen} />
      <TemplateLibraryDrawer
        open={templateOpen}
        onOpenChange={setTemplateOpen}
        templates={templates.data?.templates ?? []}
        presets={presets.data?.presets ?? []}
        loading={templates.isLoading}
      />
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
          These are live Alpaca provider lists, not templates. Running one creates a saved Screener
          and an immediate run from current provider evidence.
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
                <div className="flex min-w-0 gap-2">
                  <div
                    className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded border ${marketListIconTone(m.key)}`}
                  >
                    {marketListIcon(m.key)}
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium">{m.label}</div>
                    <div className="mt-0.5 text-[11px] text-fg-muted">{m.description}</div>
                    <div className="mt-1 flex flex-wrap gap-1">
                      <StatusBadge tone={marketListIntentTone(m.key)} size="sm">
                        {marketListIntent(m.key)}
                      </StatusBadge>
                      <StatusBadge tone="info" size="sm">
                        live Alpaca
                      </StatusBadge>
                      <StatusBadge tone="neutral" size="sm">
                        up to 50 symbols
                      </StatusBadge>
                    </div>
                    <div className="mt-1 text-[11px] text-fg-subtle">
                      Creates a new Screener run; the symbols can change each time Alpaca ranks the
                      list.
                    </div>
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

function TemplateLibraryDrawer({
  open,
  onOpenChange,
  templates,
  presets,
  loading,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  templates: ScreenerTemplate[];
  presets: ScreenerPreset[];
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
  const visibleTemplates =
    showAll || query.trim() ? filteredTemplates : filteredTemplates.slice(0, 6);
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
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-w-2xl">
        <DrawerHeader>
          <DrawerTitle>Screener templates</DrawerTitle>
          <DrawerDescription>
            Starter definitions for new Screeners. They are not Watchlists and do not attach to
            Deployments.
          </DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-2">
          {error ? (
            <Banner severity="danger" title="Template create failed" message={error} />
          ) : null}
          {loading ? <LoadingState title="Loading templates" /> : null}
          <div className="flex items-center justify-between gap-3">
            <div className="text-xs text-fg-muted">
              Pick one only when you want a new Screener draft from a known pattern.
            </div>
            <StatusBadge tone="neutral">{templates.length}</StatusBadge>
          </div>
          <TextField
            label="Search templates"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="fractionable, momentum, gap"
          />
          <div className="grid grid-cols-1 gap-2">
            {visibleTemplates.map((t) => {
              const universe = templateUniverseMeta(t, presets);
              return (
                <div key={t.key} className="rounded border border-border bg-bg-inset/40 px-3 py-2">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 gap-2">
                      <div
                        className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded border ${templateIconTone(t)}`}
                      >
                        {templateIcon(t)}
                      </div>
                      <div className="min-w-0">
                        <div className="font-medium">{t.label}</div>
                        <div className="mt-0.5 text-[11px] text-fg-muted">{t.description}</div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          <StatusBadge tone={templateIntentTone(t)} size="sm">
                            {templateIntent(t)}
                          </StatusBadge>
                          <StatusBadge tone={universe.tone} size="sm">
                            {universe.countLabel}
                          </StatusBadge>
                          <StatusBadge tone="neutral" size="sm">
                            {templateRulesCount(t.expression)} rules
                          </StatusBadge>
                          <StatusBadge tone="muted" size="sm">
                            {t.timeframe}
                          </StatusBadge>
                        </div>
                        <div className="mt-1 text-[11px] text-fg-subtle">
                          Universe: {universe.label}
                          {universe.samples.length
                            ? ` / samples: ${universe.samples.slice(0, 5).join(", ")}`
                            : ""}
                        </div>
                        <div className="mt-1 text-[11px] text-fg-subtle">
                          Sorts by {t.sort_metric ? prettyKey(t.sort_metric) : "matched first"}.
                          Creates an editable Screener version.
                        </div>
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
                </div>
              );
            })}
          </div>
          {!query.trim() && templates.length > 6 ? (
            <Button size="sm" variant="ghost" onClick={() => setShowAll((current) => !current)}>
              {showAll ? "Show fewer templates" : `Show all ${templates.length} templates`}
            </Button>
          ) : null}
        </DrawerBody>
        <DrawerFooter>
          <Button size="sm" variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function ScreenerCard({
  screener,
  schedules,
}: {
  screener: Screener;
  schedules: DiscoverySchedule[];
}): JSX.Element {
  const activeSchedules = schedules.filter((schedule) => schedule.status === "active");
  const nextRun =
    activeSchedules
      .map((schedule) => schedule.next_run_at)
      .filter((value): value is string => Boolean(value))
      .sort((a, b) => Date.parse(a) - Date.parse(b))[0] ?? null;
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
            <StatusBadge tone={activeSchedules.length ? "ok" : "neutral"}>
              {activeSchedules.length ? `${activeSchedules.length} scheduled` : "not scheduled"}
            </StatusBadge>
          </div>
        </div>
      </div>
      {screener.description ? (
        <div className="px-4 py-2 text-xs text-fg-muted">{screener.description}</div>
      ) : null}
      <div className="px-4 py-2 text-[11px] text-fg-muted">
        {nextRun
          ? `Next automatic run: ${formatTimestamp(nextRun)}`
          : "No automatic run set. Open Schedule to make it run by itself."}
      </div>
      {screener.tags.length ? (
        <div className="px-4 pb-2 text-[11px] text-fg-subtle">{screener.tags.join(" / ")}</div>
      ) : null}
      <div className="flex items-center justify-between border-t border-border/70 px-4 py-2 text-xs text-fg-muted">
        <span>{relativeTime(screener.created_at)}</span>
        <span className="flex items-center gap-1">
          <Link to={`/screeners/${screener.id}#schedules`}>
            <Button
              size="sm"
              variant="ghost"
              leftIcon={<CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />}
            >
              Schedule
            </Button>
          </Link>
          <Link to={`/screeners/${screener.id}`}>
            <Button size="sm" variant="secondary">
              Open
            </Button>
          </Link>
        </span>
      </div>
    </Card>
  );
}

function screenerSearchText(screener: Screener): string {
  return [screener.name, screener.description ?? "", screener.status, ...screener.tags]
    .join(" ")
    .toLowerCase();
}

function compareScreeners(
  a: Screener,
  b: Screener,
  sortBy: "last_run" | "created" | "name",
): number {
  if (sortBy === "name") return a.name.localeCompare(b.name);
  const aTime = Date.parse(sortBy === "last_run" ? (a.last_run_at ?? a.created_at) : a.created_at);
  const bTime = Date.parse(sortBy === "last_run" ? (b.last_run_at ?? b.created_at) : b.created_at);
  return bTime - aTime;
}

function schedulesForScreener(
  screener: Screener,
  schedules: DiscoverySchedule[],
): DiscoverySchedule[] {
  return schedules.filter(
    (schedule) =>
      schedule.target_kind === "screener_run" &&
      schedule.screener_id === screener.id &&
      (!screener.latest_version_id || schedule.screener_version_id === screener.latest_version_id),
  );
}

function marketListIcon(key: string): JSX.Element {
  if (key.includes("loser")) return <TrendingDown className="h-4 w-4" aria-hidden="true" />;
  if (key.includes("active")) return <Activity className="h-4 w-4" aria-hidden="true" />;
  return <TrendingUp className="h-4 w-4" aria-hidden="true" />;
}

function marketListIconTone(key: string): string {
  if (key.includes("loser")) return "border-danger/30 bg-danger-subtle text-danger";
  if (key.includes("active")) return "border-info/30 bg-info-subtle text-info";
  return "border-ok/30 bg-ok-subtle text-ok";
}

function marketListIntent(key: string): string {
  if (key.includes("loser")) return "falling movers";
  if (key.includes("active")) return "volume leaders";
  return "rising movers";
}

function marketListIntentTone(key: string): StatusTone {
  if (key.includes("loser")) return "danger";
  if (key.includes("active")) return "info";
  return "ok";
}

function templateIcon(template: ScreenerTemplate): JSX.Element {
  const text = [template.label, template.category, ...template.tags].join(" ").toLowerCase();
  if (text.includes("loser") || text.includes("short"))
    return <TrendingDown className="h-4 w-4" aria-hidden="true" />;
  if (text.includes("volume") || text.includes("liquid"))
    return <BarChart3 className="h-4 w-4" aria-hidden="true" />;
  if (text.includes("broker") || text.includes("fractionable"))
    return <Settings2 className="h-4 w-4" aria-hidden="true" />;
  return <TrendingUp className="h-4 w-4" aria-hidden="true" />;
}

function templateIconTone(template: ScreenerTemplate): string {
  const intent = templateIntent(template);
  if (intent.includes("falling") || intent.includes("short"))
    return "border-danger/30 bg-danger-subtle text-danger";
  if (intent.includes("volume") || intent.includes("liquidity"))
    return "border-info/30 bg-info-subtle text-info";
  if (intent.includes("broker")) return "border-ai/30 bg-ai-subtle text-ai";
  return "border-ok/30 bg-ok-subtle text-ok";
}

function templateIntent(template: ScreenerTemplate): string {
  const text = [template.label, template.category, ...template.tags].join(" ").toLowerCase();
  if (text.includes("loser")) return "falling movers";
  if (text.includes("short")) return "short candidates";
  if (text.includes("volume") || text.includes("liquid")) return "volume/liquidity";
  if (text.includes("broker") || text.includes("fractionable")) return "broker capability";
  if (text.includes("gainer") || text.includes("momentum")) return "rising movers";
  return prettyKey(template.category);
}

function templateIntentTone(template: ScreenerTemplate): StatusTone {
  const intent = templateIntent(template);
  if (intent.includes("falling") || intent.includes("short")) return "danger";
  if (intent.includes("volume") || intent.includes("liquidity")) return "info";
  if (intent.includes("broker")) return "ai";
  if (intent.includes("rising")) return "ok";
  return "neutral";
}

function templateUniverseMeta(
  template: ScreenerTemplate,
  presets: ScreenerPreset[],
): { label: string; countLabel: string; samples: string[]; tone: StatusTone } {
  const source = template.universe_source;
  if (source.kind === "market_list") {
    return {
      label: `Live Alpaca ${prettyKey(source.market_list_key ?? "market list")}`,
      countLabel: "up to 50 live",
      samples: [],
      tone: "info",
    };
  }
  if (source.kind === "preset") {
    const preset = presets.find((item) => item.key === source.preset);
    return {
      label: preset ? preset.label : prettyKey(source.preset ?? "preset"),
      countLabel: preset ? `${preset.symbol_count} symbols` : "preset universe",
      samples: preset?.sample_symbols ?? [],
      tone: "neutral",
    };
  }
  if (source.kind === "explicit") {
    const symbols = source.symbols ?? [];
    return {
      label: "Explicit symbol list",
      countLabel: `${symbols.length} symbols`,
      samples: symbols,
      tone: symbols.length ? "neutral" : "warn",
    };
  }
  return {
    label: "Saved Watchlist universe",
    countLabel: "watchlist",
    samples: [],
    tone: "neutral",
  };
}

function templateRulesCount(expression: unknown): number {
  const node = expression as { kind?: string; children?: unknown[]; criterion?: unknown } | null;
  if (!node || typeof node !== "object") return 0;
  if (node.kind === "criterion" && node.criterion) return 1;
  return (node.children ?? []).reduce<number>(
    (total, child) => total + templateRulesCount(child),
    0,
  );
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
          {error ? (
            <Banner severity="danger" title="Could not create screener" message={error} />
          ) : null}
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
  const [prompt, setPrompt] = useState(
    "Alpaca day gainers that are tradable and fractionable with relative volume above 1.5",
  );
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
            AI is advisory only. It compiles the prompt into visible typed rules before anything is
            saved.
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
                <StatusBadge tone="neutral">
                  {describeUniverseFromSource(draft.universe_source)}
                </StatusBadge>
              </div>
              <ExpressionPreview expression={draft.expression} title="Compiled boolean tree" />
              {labels.length ? (
                <div className="text-[11px] text-fg-muted">Rule leaves: {labels.join(" / ")}</div>
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
    criterion?: {
      metric?: string;
      operator?: string;
      value?: unknown;
      value_max?: unknown;
      label?: string | null;
    };
    children?: unknown[];
  };
  if (!node || typeof node !== "object") return [];
  if (node.kind === "criterion" && node.criterion) {
    const c = node.criterion;
    const value =
      c.operator === "between" ? `${String(c.value)} to ${String(c.value_max)}` : String(c.value);
    return [c.label || `${c.metric ?? "field"} ${c.operator ?? "="} ${value}`];
  }
  return (node.children ?? []).flatMap(expressionLabels);
}

function describeUniverseFromSource(source: {
  kind: string;
  preset?: string | null;
  market_list_key?: string | null;
  symbols?: string[];
}): string {
  if (source.kind === "market_list")
    return `Alpaca list: ${prettyKey(source.market_list_key ?? "market_list")}`;
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

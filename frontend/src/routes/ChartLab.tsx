import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Eye,
  EyeOff,
  Layers3,
  Play,
  Plus,
  X,
} from "lucide-react";
import { ChartLabApi } from "@/api/chartLab";
import { StrategiesApi } from "@/api/strategies";
import type {
  ChartLabBarPreview,
  ChartLabFeatureDescriptor,
  ChartLabFeatureGroup,
  ChartLabPreviewRequest,
  ChartLabPreviewResponse,
} from "@/api/schemas/chartLab";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Select } from "@/components/ui/Select";
import { TextField } from "@/components/ui/TextField";
import { StatusBadge } from "@/components/badges/StatusBadge";
import {
  StrategyPreviewChart,
  type PreviewBarRow,
  type StrategyPreviewChartDensity,
} from "@/components/charts/StrategyPreviewChart";
import { EmptyState } from "@/components/empty/EmptyState";
import { ErrorState } from "@/components/empty/ErrorState";
import { LoadingState } from "@/components/empty/LoadingState";
import { StaleState } from "@/components/empty/StaleState";
import { PageHeader } from "./PageHeader";
import { cn } from "@/lib/cn";
import { formatTimestamp } from "@/lib/format";

const TIMEFRAMES = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"] as const;
const DATA_SOURCES = ["alpaca", "yahoo"] as const;
const FEATURE_GROUPS: ChartLabFeatureGroup[] = [
  "Trend",
  "Momentum",
  "Volatility",
  "Volume",
  "Price",
  "Time",
];

type Timeframe = (typeof TIMEFRAMES)[number];
type DataSource = (typeof DATA_SOURCES)[number];
type AdjustmentPolicy = "split_dividend_adjusted" | "split_only" | "raw";

/** Normalize StrategyVersion feature_ref strings into preview API refs (drops trailing `[0]` lookback shorthand). */
function normalizeManualFeatureRef(raw: string): string {
  return raw.trim().replace(/\[\d+\]$/, "");
}

function markerIsEntry(marker_type: string): boolean {
  return marker_type.includes("entry");
}

function defaultIsoDate(daysAgo: number): string {
  const d = new Date(Date.now() - daysAgo * 24 * 3600 * 1000);
  return d.toISOString().slice(0, 10);
}

export function ChartLab(): JSX.Element {
  const strategies = useQuery({
    queryKey: ["strategies", "list"],
    queryFn: () => StrategiesApi.list(),
    refetchInterval: 60_000,
  });

  const [strategyId, setStrategyId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [symbol, setSymbol] = useState("SPY");
  const [timeframe, setTimeframe] = useState<Timeframe>("5m");
  const [source, setSource] = useState<DataSource>("alpaca");
  const [adjustmentPolicy, setAdjustmentPolicy] =
    useState<AdjustmentPolicy>("split_dividend_adjusted");
  const [startDate, setStartDate] = useState(defaultIsoDate(30));
  const [endDate, setEndDate] = useState(defaultIsoDate(0));
  const [manualRefs, setManualRefs] = useState<Set<string>>(new Set());
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [selectedIndex, setSelectedIndex] = useState<number>(0);
  const [featureSearch, setFeatureSearch] = useState("");
  const [lastLoadedSignature, setLastLoadedSignature] = useState<string | null>(null);
  const [showSignalLabels, setShowSignalLabels] = useState(false);
  const [density, setDensity] = useState<StrategyPreviewChartDensity>({
    showEntries: true,
    showExits: true,
    showDerivedOverlays: true,
    showManualOverlays: true,
    showWarmupBars: true,
  });
  const [crosshairBarIndex, setCrosshairBarIndex] = useState<number | null>(null);

  const versions = useQuery({
    queryKey: ["strategies", strategyId, "versions"],
    queryFn: () => StrategiesApi.listVersions(strategyId),
    enabled: Boolean(strategyId),
  });

  const featureLibrary = useQuery({
    queryKey: ["chart-lab", "features", timeframe],
    queryFn: () => ChartLabApi.features(timeframe),
    staleTime: 60_000,
  });

  useEffect(() => {
    if (!strategyId) {
      setVersionId("");
      return;
    }
    if (!versions.data || versions.data.length === 0) {
      setVersionId("");
      return;
    }
    setVersionId((current) => {
      if (current && versions.data.some((v) => v.strategy_version_id === current)) {
        return current;
      }
      return [...versions.data].sort((a, b) => b.version - a.version)[0].strategy_version_id;
    });
  }, [strategyId, versions.data]);

  /** Seed manual overlay refs declared on the StrategyVersion when a version is picked. */
  useEffect(() => {
    if (!strategyId || !versionId || !versions.data?.length) return;
    const record = versions.data.find((entry) => entry.strategy_version_id === versionId);
    const rawRefs = record?.payload?.feature_refs ?? [];
    const normalized = rawRefs.map(normalizeManualFeatureRef).filter(Boolean);
    if (!normalized.length) return;
    setManualRefs((prev) => new Set([...prev, ...normalized]));
  }, [strategyId, versionId, versions.data]);

  const currentSignature = useMemo(
    () =>
      JSON.stringify({
        strategyId,
        versionId,
        symbol: symbol.trim().toUpperCase(),
        timeframe,
        source,
        adjustmentPolicy,
        startDate,
        endDate,
        manualRefs: [...manualRefs].sort(),
      }),
    [
      adjustmentPolicy,
      endDate,
      manualRefs,
      source,
      startDate,
      strategyId,
      symbol,
      timeframe,
      versionId,
    ],
  );

  const preview = useMutation({
    mutationFn: (request: ChartLabPreviewRequest) => ChartLabApi.preview(request),
    onSuccess: (response) => {
      setVisibleKeys(new Set(response.features.map((feature) => feature.feature_key)));
      setSelectedIndex(firstActiveIndex(response));
      setLastLoadedSignature(currentSignature);
    },
  });

  const response = preview.data;
  const derivedFeatures = useMemo(
    () => (response?.features ?? []).filter((feature) => feature.origin === "derived"),
    [response],
  );
  const manualFeatures = useMemo(
    () => (response?.features ?? []).filter((feature) => feature.origin === "manual"),
    [response],
  );
  const derivedKeys = useMemo(
    () => new Set(derivedFeatures.map((feature) => feature.feature_key)),
    [derivedFeatures],
  );

  const libraryFeatures = featureLibrary.data?.features ?? [];
  const availableLibraryFeatures = useMemo(() => {
    const q = featureSearch.trim().toLowerCase();
    const manualKeysByRef = new Set(
      [...manualRefs]
        .map((ref) => libraryFeatures.find((feature) => feature.feature_ref === ref)?.feature_key)
        .filter((key): key is string => Boolean(key)),
    );
    return libraryFeatures.filter((feature) => {
      if (derivedKeys.has(feature.feature_key)) return false;
      if (manualKeysByRef.has(feature.feature_key)) return false;
      if (!q) return true;
      return [feature.name, feature.feature_ref, feature.indicator_type, feature.group]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [derivedKeys, featureSearch, libraryFeatures, manualRefs]);
  const selectedLibraryManualFeatures = useMemo(
    () => libraryFeatures.filter((feature) => manualRefs.has(feature.feature_ref)),
    [libraryFeatures, manualRefs],
  );

  const selectedBar = response?.bars[selectedIndex] ?? response?.bars[0] ?? null;
  const chartRows = useMemo(() => previewBarsFrom(response), [response]);
  const warmupCount = response?.bars.filter((bar) => bar.is_warmup).length ?? 0;
  const activeBarCount =
    response?.bars.filter((bar) => !bar.is_warmup).length ?? 0;
  const signalStats = useMemo(() => {
    let entries = 0;
    let exits = 0;
    for (const bar of response?.bars ?? []) {
      for (const marker of bar.signal_markers) {
        if (markerIsEntry(marker.marker_type)) entries += 1;
        else exits += 1;
      }
    }
    return { entries, exits };
  }, [response]);
  const isStale = Boolean(response && lastLoadedSignature && currentSignature !== lastLoadedSignature);
  const canLoad = Boolean(
    symbol.trim() && startDate && endDate && (!strategyId || versionId) && !preview.isPending,
  );

  function loadData(): void {
    const request: ChartLabPreviewRequest = {
      strategy_version_id: strategyId ? versionId : null,
      manual_feature_refs: [...manualRefs],
      symbol: symbol.trim().toUpperCase(),
      timeframe,
      start: new Date(`${startDate}T00:00:00`).toISOString(),
      end: new Date(`${endDate}T23:59:59`).toISOString(),
      source,
      adjustment_policy: adjustmentPolicy,
    };
    preview.mutate(request);
  }

  function toggleVisible(featureKey: string): void {
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(featureKey)) next.delete(featureKey);
      else next.add(featureKey);
      return next;
    });
  }

  function addManualFeature(feature: ChartLabFeatureDescriptor): void {
    setManualRefs((prev) => new Set(prev).add(feature.feature_ref));
  }

  function removeManualFeature(feature: ChartLabFeatureDescriptor): void {
    setManualRefs((prev) => {
      const next = new Set(prev);
      next.delete(feature.feature_ref);
      return next;
    });
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      next.delete(feature.feature_key);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="ChartLab"
        subtitle="Signal and Feature Verification"
        explainSlug="chart-lab"
        actions={
          <span className="flex items-center gap-2">
            <StatusBadge tone={strategyId ? "info" : "muted"}>
              {strategyId ? "Strategy Mode" : "Feature Explorer"}
            </StatusBadge>
            <StatusBadge tone="muted">No trading</StatusBadge>
          </span>
        }
      />

      <Card>
        <CardBody className="grid grid-cols-1 gap-3 xl:grid-cols-[minmax(180px,1.2fr)_minmax(160px,1fr)_110px_100px_110px_150px_130px_130px_auto]">
          <Select
            label="Strategy"
            value={strategyId}
            onChange={(event) => setStrategyId(event.target.value)}
            disabled={strategies.isLoading || strategies.isError}
          >
            <option value="">Feature Exploration</option>
            {strategies.data?.strategies.map((strategy) => (
              <option key={strategy.strategy_id} value={strategy.strategy_id}>
                {strategy.name}
              </option>
            ))}
          </Select>
          <Select
            label="Strategy Version"
            value={versionId}
            onChange={(event) => setVersionId(event.target.value)}
            disabled={!strategyId || versions.isLoading}
          >
            <option value="">Select version</option>
            {versions.data?.map((version) => (
              <option key={version.strategy_version_id} value={version.strategy_version_id}>
                v{version.version} - {version.status}
              </option>
            ))}
          </Select>
          <TextField
            label="Symbol"
            value={symbol}
            onChange={(event) => setSymbol(event.target.value.toUpperCase())}
          />
          <Select
            label="Timeframe"
            value={timeframe}
            onChange={(event) => setTimeframe(event.target.value as Timeframe)}
          >
            {TIMEFRAMES.map((tf) => (
              <option key={tf} value={tf}>
                {tf}
              </option>
            ))}
          </Select>
          <Select
            label="Data Source"
            value={source}
            onChange={(event) => setSource(event.target.value as DataSource)}
          >
            <option value="alpaca">Alpaca</option>
            <option value="yahoo">Yahoo</option>
          </Select>
          <Select
            label="Adjustment"
            value={adjustmentPolicy}
            onChange={(event) => setAdjustmentPolicy(event.target.value as AdjustmentPolicy)}
          >
            <option value="split_dividend_adjusted">Split + dividend</option>
            <option value="split_only">Split only</option>
            <option value="raw">Raw</option>
          </Select>
          <TextField
            label="Start"
            type="date"
            value={startDate}
            onChange={(event) => setStartDate(event.target.value)}
          />
          <TextField
            label="End"
            type="date"
            value={endDate}
            onChange={(event) => setEndDate(event.target.value)}
          />
          <div className="flex items-end">
            <Button
              className="w-full"
              variant="primary"
              leftIcon={<Play className="h-3.5 w-3.5" aria-hidden="true" />}
              loading={preview.isPending}
              disabled={!canLoad}
              onClick={loadData}
            >
              Load Data
            </Button>
          </div>
        </CardBody>
      </Card>

      {isStale ? (
        <StaleState
          title="Loaded data is stale"
          message="The controls changed after the last load."
          detail="reload to refresh the verification view"
        />
      ) : null}

      {preview.isError ? (
        <ErrorState
          title="ChartLab load failed"
          detail={(preview.error as Error)?.message}
          onRetry={loadData}
        />
      ) : null}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[320px_minmax(0,1fr)_340px]">
        <FeatureSystem
          strategySelected={Boolean(strategyId)}
          derivedFeatures={derivedFeatures}
          manualFeatures={manualFeatures}
          selectedManualFeatures={selectedLibraryManualFeatures}
          libraryFeatures={availableLibraryFeatures}
          groupedFeatures={groupFeatures(availableLibraryFeatures)}
          visibleKeys={visibleKeys}
          featureSearch={featureSearch}
          loadingLibrary={featureLibrary.isLoading}
          onSearch={setFeatureSearch}
          onAddManual={addManualFeature}
          onRemoveManual={removeManualFeature}
          onToggleVisible={toggleVisible}
        />

        <Card className="min-w-0 overflow-hidden">
          <CardHeader>
            <CardTitle>
              <span className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-info" aria-hidden="true" />
                {response?.session.symbol ?? symbol.toUpperCase()} Candles
              </span>
            </CardTitle>
            <span className="flex flex-wrap items-center justify-end gap-2">
              <StatusBadge tone="muted">
                Entry markers: {signalStats.entries}
              </StatusBadge>
              <StatusBadge tone="muted">
                Exit markers: {signalStats.exits}
              </StatusBadge>
              <StatusBadge tone="ok">
                Active bars: {activeBarCount}
              </StatusBadge>
              <StatusBadge tone={warmupCount ? "warn" : "muted"}>
                Warm-up bars: {warmupCount}
              </StatusBadge>
            </span>
          </CardHeader>
          <CardBody className="space-y-0 p-0">
            {preview.isPending ? <LoadingState title="Loading bars and features" /> : null}
            {!preview.isPending && !response ? (
              <EmptyState
                className="m-4"
                icon={<Layers3 className="h-5 w-5" aria-hidden="true" />}
                title="No ChartLab data loaded"
                message="Pick a symbol, choose optional Strategy context, then load."
              />
            ) : null}
            {response && chartRows.length === 0 ? (
              <EmptyState
                className="m-4"
                title="No candles returned"
                message="The data source returned no base-timeframe bars."
              />
            ) : null}
            {response && chartRows.length > 0 ? (
              <>
                <ChartLabDensityToolbar
                  showSignalLabels={showSignalLabels}
                  onToggleLabels={setShowSignalLabels}
                  density={density}
                  onDensity={(patch) => setDensity((d) => ({ ...d, ...patch }))}
                />
                <SignalHoverCard
                  bar={
                    crosshairBarIndex !== null
                      ? (response.bars[crosshairBarIndex] ?? null)
                      : null
                  }
                />
                <StrategyPreviewChart
                  symbol={response.session.symbol}
                  bars={chartRows}
                  preview={response.bars}
                  plan={response.feature_plan}
                  derivedFeatureKeys={derivedFeatures.map((row) => row.feature_key)}
                  manualFeatureKeys={manualFeatures.map((row) => row.feature_key)}
                  visibleFeatureKeys={[...visibleKeys]}
                  density={density}
                  showSignalLabels={showSignalLabels}
                  selectedBarIndex={selectedIndex}
                  onBarClick={setSelectedIndex}
                  onCrosshairBarIndex={setCrosshairBarIndex}
                  height={520}
                />
              </>
            ) : null}
          </CardBody>
        </Card>

        <BarInspector
          bar={selectedBar}
          features={response?.features ?? []}
          visibleKeys={visibleKeys}
          strategySelected={Boolean(strategyId)}
        />
      </div>

      <TimelineDebug
        bars={response?.bars ?? []}
        selectedIndex={selectedIndex}
        onSelect={setSelectedIndex}
      />
    </div>
  );
}

function ChartLabDensityToolbar({
  showSignalLabels,
  onToggleLabels,
  density,
  onDensity,
}: {
  showSignalLabels: boolean;
  onToggleLabels: (value: boolean) => void;
  density: StrategyPreviewChartDensity;
  onDensity: (patch: Partial<StrategyPreviewChartDensity>) => void;
}): JSX.Element {
  return (
    <div className="flex flex-col gap-2 border-b border-border/70 bg-bg-subtle/50 px-3 py-2 text-[11px]">
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-fg-muted">
        <label className="inline-flex cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            className="h-3.5 w-3.5 rounded border-border text-accent"
            checked={showSignalLabels}
            onChange={(event) => onToggleLabels(event.target.checked)}
            aria-label="Show signal labels"
          />
          Show signal labels
        </label>
        <DensityToggle
          checked={density.showEntries}
          label="Show entries"
          onChange={(value) => onDensity({ showEntries: value })}
        />
        <DensityToggle
          checked={density.showExits}
          label="Show exits"
          onChange={(value) => onDensity({ showExits: value })}
        />
        <DensityToggle
          checked={density.showDerivedOverlays}
          label="Plot derived overlays"
          onChange={(value) => onDensity({ showDerivedOverlays: value })}
        />
        <DensityToggle
          checked={density.showManualOverlays}
          label="Plot manual overlays"
          onChange={(value) => onDensity({ showManualOverlays: value })}
        />
        <DensityToggle
          checked={density.showWarmupBars}
          label="Warm-up bars"
          onChange={(value) => onDensity({ showWarmupBars: value })}
        />
      </div>
    </div>
  );
}

function DensityToggle({
  checked,
  label,
  onChange,
}: {
  checked: boolean;
  label: string;
  onChange: (value: boolean) => void;
}): JSX.Element {
  const id = `chartlab-density-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <span className="inline-flex items-center gap-2">
      <input
        id={id}
        type="checkbox"
        className="h-3.5 w-3.5 rounded border-border text-accent"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <label htmlFor={id} className="cursor-pointer select-none">
        {label}
      </label>
    </span>
  );
}

function SignalHoverCard({ bar }: { bar: ChartLabBarPreview | null }): JSX.Element {
  const entrySignals =
    bar?.signal_markers.filter((m) => markerIsEntry(m.marker_type)) ?? [];
  const exitSignals =
    bar?.signal_markers.filter((m) => !markerIsEntry(m.marker_type)) ?? [];
  const entryFired = entrySignals.length > 0;
  const exitFired = exitSignals.length > 0;

  return (
    <div
      data-testid="chart-lab-signal-hover"
      className="border-b border-border/60 px-3 py-2 text-xs text-fg-muted"
    >
      {!bar ? (
        <span>Hover over the chart — signal names, timestamps, reasons, and truth values appear here.</span>
      ) : (
        <div className="space-y-2 text-fg">
          <div className="flex flex-wrap gap-2 font-medium text-fg-muted">
            <span className="tabular">{formatTimestamp(bar.timestamp)}</span>
            <StatusBadge tone={bar.is_warmup ? "warn" : "ok"} size="sm">
              {bar.is_warmup ? "Warm-up bar" : "Active bar"}
            </StatusBadge>
            <span>
              Entry:{" "}
              <strong className="text-fg">{entryFired ? "true" : "false"}</strong>
            </span>
            <span>
              Exit / risk exit:{" "}
              <strong className="text-fg">{exitFired ? "true" : "false"}</strong>
            </span>
          </div>
          {!bar.signal_markers.length ? (
            <span className="text-fg-subtle">No signal markers on this bar.</span>
          ) : (
            <ul className="grid gap-1.5 sm:grid-cols-2">
              {bar.signal_markers.map((marker, idx) => (
                <li
                  key={`${marker.timestamp}-${marker.marker_type}-${idx}`}
                  className="rounded border border-border/80 bg-bg-inset px-2 py-1.5"
                >
                  <div className="font-medium text-fg">
                    {(marker.signal_name ?? "").trim() ||
                      marker.marker_type.replace(/^candidate_/i, "")}
                  </div>
                  <div className="mt-1 space-y-0.5 text-[11px] text-fg-muted">
                    <div className="tabular">{formatTimestamp(marker.timestamp)}</div>
                    <div className="text-fg-subtle">Reason: {marker.reason || "—"}</div>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {bar.non_fire_reasons.length ? (
            <div className="rounded bg-bg-inset px-2 py-1 text-[11px] text-fg-subtle">
              Non-fire (context): {bar.non_fire_reasons.join(", ") || "—"}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

function FeatureSystem({
  strategySelected,
  derivedFeatures,
  manualFeatures,
  selectedManualFeatures,
  libraryFeatures,
  groupedFeatures,
  visibleKeys,
  featureSearch,
  loadingLibrary,
  onSearch,
  onAddManual,
  onRemoveManual,
  onToggleVisible,
}: {
  strategySelected: boolean;
  derivedFeatures: ChartLabFeatureDescriptor[];
  manualFeatures: ChartLabFeatureDescriptor[];
  selectedManualFeatures: ChartLabFeatureDescriptor[];
  libraryFeatures: ChartLabFeatureDescriptor[];
  groupedFeatures: Map<ChartLabFeatureGroup, ChartLabFeatureDescriptor[]>;
  visibleKeys: Set<string>;
  featureSearch: string;
  loadingLibrary: boolean;
  onSearch: (value: string) => void;
  onAddManual: (feature: ChartLabFeatureDescriptor) => void;
  onRemoveManual: (feature: ChartLabFeatureDescriptor) => void;
  onToggleVisible: (featureKey: string) => void;
}): JSX.Element {
  const pendingManualFeatures = selectedManualFeatures.filter(
    (feature) => !manualFeatures.some((active) => active.feature_ref === feature.feature_ref),
  );

  return (
    <Card className="self-start">
      <CardHeader>
        <CardTitle>Feature System</CardTitle>
        <StatusBadge tone="muted">{derivedFeatures.length + manualFeatures.length} active</StatusBadge>
      </CardHeader>
      <CardBody className="space-y-4">
        {strategySelected ? (
          <section className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase text-fg-muted">
                Features Used by Strategy
              </h3>
              <StatusBadge tone="info" size="sm">Derived from Strategy</StatusBadge>
            </div>
            {derivedFeatures.length === 0 ? (
              <div className="rounded border border-dashed border-border bg-bg-inset px-3 py-2 text-xs text-fg-subtle">
                Load data to derive the Strategy feature plan.
              </div>
            ) : (
              <FeatureList
                features={derivedFeatures}
                visibleKeys={visibleKeys}
                onToggleVisible={onToggleVisible}
              />
            )}
          </section>
        ) : null}

        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase text-fg-muted">Manual Overlays</h3>
            <StatusBadge tone="neutral" size="sm">Manual</StatusBadge>
          </div>
          {manualFeatures.length || pendingManualFeatures.length ? (
            <FeatureList
              features={manualFeatures.length ? manualFeatures : pendingManualFeatures}
              visibleKeys={visibleKeys}
              onToggleVisible={onToggleVisible}
              onRemove={onRemoveManual}
            />
          ) : (
            <div className="rounded border border-dashed border-border bg-bg-inset px-3 py-2 text-xs text-fg-subtle">
              No manual overlays added.
            </div>
          )}
        </section>

        <section className="space-y-3 border-t border-border/70 pt-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase text-fg-muted">Feature Library</h3>
            <StatusBadge tone="muted" size="sm">{libraryFeatures.length}</StatusBadge>
          </div>
          <TextField
            label="Search"
            value={featureSearch}
            onChange={(event) => onSearch(event.target.value)}
            placeholder="EMA, RSI, volume"
          />
          {loadingLibrary ? <LoadingState title="Loading Feature Library" /> : null}
          <div className="max-h-[520px] space-y-3 overflow-auto pr-1">
            {FEATURE_GROUPS.map((group) => {
              const features = groupedFeatures.get(group) ?? [];
              return (
                <div key={group} className="space-y-1">
                  <div className="flex items-center justify-between text-[11px] uppercase text-fg-subtle">
                    <span>{group}</span>
                    <span>{features.length}</span>
                  </div>
                  {features.length === 0 ? (
                    <div className="rounded bg-bg-inset px-2 py-1 text-[11px] text-fg-subtle">
                      none
                    </div>
                  ) : (
                    features.map((feature) => (
                      <button
                        key={feature.feature_key}
                        type="button"
                        className="flex w-full items-start justify-between gap-2 rounded border border-border bg-bg-inset px-2 py-2 text-left text-xs hover:border-accent/50"
                        onClick={() => onAddManual(feature)}
                      >
                        <FeatureSummary feature={feature} />
                        <Plus className="mt-0.5 h-3.5 w-3.5 shrink-0 text-info" aria-hidden="true" />
                      </button>
                    ))
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </CardBody>
    </Card>
  );
}

function FeatureList({
  features,
  visibleKeys,
  onToggleVisible,
  onRemove,
}: {
  features: ChartLabFeatureDescriptor[];
  visibleKeys: Set<string>;
  onToggleVisible: (featureKey: string) => void;
  onRemove?: (feature: ChartLabFeatureDescriptor) => void;
}): JSX.Element {
  return (
    <div className="space-y-1">
      {features.map((feature) => {
        const visible = visibleKeys.has(feature.feature_key);
        return (
          <div
            key={`${feature.origin}-${feature.feature_key}`}
            className="flex items-start justify-between gap-2 rounded border border-border bg-bg-inset px-2 py-2 text-xs"
          >
            <FeatureSummary feature={feature} />
            <span className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                className={cn(
                  "inline-flex h-6 w-6 items-center justify-center rounded border border-border",
                  visible ? "text-ok" : "text-fg-subtle",
                )}
                onClick={() => onToggleVisible(feature.feature_key)}
                aria-label={`Toggle ${feature.name}`}
              >
                {visible ? (
                  <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <EyeOff className="h-3.5 w-3.5" aria-hidden="true" />
                )}
              </button>
              {onRemove ? (
                <button
                  type="button"
                  className="inline-flex h-6 w-6 items-center justify-center rounded border border-border text-fg-subtle hover:text-danger"
                  onClick={() => onRemove(feature)}
                  aria-label={`Remove ${feature.name}`}
                >
                  <X className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              ) : null}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function FeatureSummary({ feature }: { feature: ChartLabFeatureDescriptor }): JSX.Element {
  return (
    <span className="min-w-0">
      <span className="block truncate font-medium text-fg">{feature.name}</span>
      <span className="mt-1 flex flex-wrap items-center gap-1">
        <StatusBadge tone={feature.origin === "derived" ? "info" : "neutral"} size="sm">
          {feature.origin === "derived" ? "Derived" : "Manual"}
        </StatusBadge>
        <span className="text-[11px] text-fg-subtle">{feature.timeframe}</span>
        <span className="text-[11px] text-fg-subtle">{feature.indicator_type}</span>
      </span>
    </span>
  );
}

function BarInspector({
  bar,
  features,
  visibleKeys,
  strategySelected,
}: {
  bar: ChartLabBarPreview | null;
  features: ChartLabFeatureDescriptor[];
  visibleKeys: Set<string>;
  strategySelected: boolean;
}): JSX.Element {
  const values = useMemo(() => {
    const byKey = new Map<string, ChartLabBarPreview["feature_values"][number]>();
    for (const value of bar?.feature_values ?? []) byKey.set(value.feature_key, value);
    return byKey;
  }, [bar]);
  const derivedRows = features.filter(
    (feature) => feature.origin === "derived" && visibleKeys.has(feature.feature_key),
  );
  const manualRows = features.filter(
    (feature) => feature.origin === "manual" && visibleKeys.has(feature.feature_key),
  );
  const conditionRows = conditionTruthRows(bar?.condition_truth_tree ?? {});
  const entrySignal = Boolean(bar?.signal_markers.some((m) => markerIsEntry(m.marker_type)));
  const exitSignal = Boolean(
    bar?.signal_markers.some((m) => !markerIsEntry(m.marker_type)),
  );

  function featureBlock(
    label: string,
    tone: "info" | "neutral",
    rows: ChartLabFeatureDescriptor[],
    testId?: string,
  ): JSX.Element {
    return (
      <section className="space-y-2 border-t border-border/70 pt-3" data-testid={testId}>
        <div className="flex items-center gap-2">
          <span className="font-semibold text-fg-muted">{label}</span>
          <StatusBadge tone={tone} size="sm">
            {tone === "info" ? "Derived" : "Manual"}
          </StatusBadge>
        </div>
        {!rows.length ? (
          <div className="text-fg-subtle">None toggled visible.</div>
        ) : (
          <div className="space-y-1">
            {rows.map((feature) => {
              const value = values.get(feature.feature_key);
              return (
                <div
                  key={feature.feature_key}
                  className="grid grid-cols-[minmax(0,1fr)_auto] gap-2 rounded bg-bg-inset px-2 py-1.5"
                >
                  <span className="min-w-0">
                    <span className="block truncate">{feature.name}</span>
                    <span className="text-[11px] text-fg-subtle">{feature.timeframe}</span>
                  </span>
                  <span className="text-right tabular">
                    {value ? formatFeatureValue(value.value) : "missing"}
                    {value ? (
                      <span className="ml-1 text-[10px] uppercase text-fg-subtle">
                        {value.availability}
                      </span>
                    ) : null}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </section>
    );
  }

  return (
    <Card className="self-start">
      <CardHeader>
        <CardTitle>Bar Inspector</CardTitle>
        {bar ? (
          <StatusBadge tone={bar.is_warmup ? "warn" : "ok"}>
            {bar.is_warmup ? "Warm-up" : "Active"}
          </StatusBadge>
        ) : (
          <StatusBadge tone="muted">empty</StatusBadge>
        )}
      </CardHeader>
      <CardBody className="space-y-4 text-xs">
        {!bar ? (
          <div className="text-fg-subtle">No bar selected.</div>
        ) : (
          <>
            <section className="grid grid-cols-2 gap-2">
              <InspectorField label="Bar" value={bar.bar_index} />
              <InspectorField label="Time" value={formatTimestamp(bar.timestamp)} />
              <InspectorField label="Open" value={formatPrice(bar.open)} />
              <InspectorField label="High" value={formatPrice(bar.high)} />
              <InspectorField label="Low" value={formatPrice(bar.low)} />
              <InspectorField label="Close" value={formatPrice(bar.close)} />
              <InspectorField label="Volume" value={formatNumber(bar.volume)} />
              <InspectorField label="Region" value={bar.is_warmup ? "Warm-up" : "Active"} />
            </section>

            {featureBlock(
              "Derived strategy features",
              "info",
              derivedRows,
              "bar-inspector-derived-features",
            )}
            {featureBlock(
              "Manual overlays",
              "neutral",
              manualRows,
              "bar-inspector-manual-features",
            )}

            <section className="space-y-2 border-t border-border/70 pt-3">
              <div className="font-semibold text-fg-muted">Signals (verification)</div>
              <div className="grid grid-cols-2 gap-2">
                <SignalTruth label="Entry signal" value={entrySignal} />
                <SignalTruth label="Exit signal" value={exitSignal} />
              </div>
              <InspectorField
                label="Non-fire reason"
                value={bar.non_fire_reasons.join(", ") || "none"}
              />
            </section>

            {strategySelected ? (
              <section className="space-y-2 border-t border-border/70 pt-3">
                <div className="font-semibold text-fg-muted">Condition truth tree</div>
                <div className="space-y-1">
                  {conditionRows.length === 0 ? (
                    <div className="text-fg-subtle">No condition rows reported.</div>
                  ) : (
                    conditionRows.map((row, index) => (
                      <div
                        key={`${row.label}-${index}`}
                        className="flex items-center justify-between gap-2 rounded bg-bg-inset px-2 py-1.5"
                      >
                        <span className="min-w-0 truncate">{row.label}</span>
                        <StatusBadge tone={row.result ? "ok" : "danger"} size="sm">
                          {row.result ? "true" : "false"}
                        </StatusBadge>
                      </div>
                    ))
                  )}
                </div>
              </section>
            ) : null}
          </>
        )}
      </CardBody>
    </Card>
  );
}

function TimelineDebug({
  bars,
  selectedIndex,
  onSelect,
}: {
  bars: ChartLabBarPreview[];
  selectedIndex: number;
  onSelect: (index: number) => void;
}): JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Timeline / Debug</CardTitle>
        <span className="flex items-center gap-2">
          <StatusBadge tone="muted">{bars.length} bars</StatusBadge>
          <StatusBadge tone="warn">{bars.filter((bar) => bar.is_warmup).length} warm-up</StatusBadge>
        </span>
      </CardHeader>
      <CardBody className="p-0">
        {bars.length === 0 ? (
          <div className="px-4 py-3 text-xs text-fg-subtle">No history loaded.</div>
        ) : (
          <div className="max-h-72 overflow-auto">
            <table className="ut-table">
              <thead>
                <tr>
                  <th>Bar</th>
                  <th>Time</th>
                  <th>Region</th>
                  <th>Close</th>
                  <th>Signals</th>
                  <th>Reason</th>
                </tr>
              </thead>
              <tbody>
                {bars.map((bar, index) => (
                  <tr
                    key={`${bar.timestamp}-${index}`}
                    className={cn(
                      "cursor-pointer",
                      selectedIndex === index ? "bg-info-subtle/60" : "hover:bg-bg-inset",
                    )}
                    onClick={() => onSelect(index)}
                  >
                    <td className="tabular">{bar.bar_index}</td>
                    <td className="text-fg-muted">{formatTimestamp(bar.timestamp)}</td>
                    <td>
                      <StatusBadge tone={bar.is_warmup ? "warn" : "ok"} size="sm">
                        {bar.is_warmup ? "warm-up" : "active"}
                      </StatusBadge>
                    </td>
                    <td className="tabular">{formatPrice(bar.close)}</td>
                    <td>
                      <SignalMarkers markers={bar.signal_markers} />
                    </td>
                    <td className="max-w-[360px] truncate text-fg-subtle">
                      {bar.non_fire_reasons.join(", ") || "none"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function SignalMarkers({
  markers,
}: {
  markers: ChartLabBarPreview["signal_markers"];
}): JSX.Element {
  if (markers.length === 0) return <span className="text-fg-subtle">none</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {markers.map((marker, index) => (
        <StatusBadge
          key={`${marker.timestamp}-${marker.marker_type}-${index}`}
          tone={marker.marker_type.includes("entry") ? "ok" : "warn"}
          size="sm"
        >
          {marker.marker_type.replace("candidate_", "")}
        </StatusBadge>
      ))}
    </span>
  );
}

function InspectorField({ label, value }: { label: string; value: React.ReactNode }): JSX.Element {
  return (
    <div className="rounded bg-bg-inset px-2 py-1.5">
      <div className="text-[11px] uppercase text-fg-subtle">{label}</div>
      <div className="mt-0.5 break-words tabular text-fg">{value}</div>
    </div>
  );
}

function SignalTruth({ label, value }: { label: string; value: boolean }): JSX.Element {
  return (
    <div className="flex items-center justify-between rounded bg-bg-inset px-2 py-1.5">
      <span className="text-fg-muted">{label}</span>
      <StatusBadge tone={value ? "ok" : "muted"} size="sm">
        {value ? "true" : "false"}
      </StatusBadge>
    </div>
  );
}

function previewBarsFrom(response: ChartLabPreviewResponse | undefined): PreviewBarRow[] {
  return (response?.bars ?? []).map((bar) => ({
    timestamp: bar.timestamp,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    isWarmup: bar.is_warmup,
  }));
}

function firstActiveIndex(response: ChartLabPreviewResponse): number {
  const active = response.bars.findIndex((bar) => !bar.is_warmup);
  return active >= 0 ? active : 0;
}

function groupFeatures(features: ChartLabFeatureDescriptor[]): Map<ChartLabFeatureGroup, ChartLabFeatureDescriptor[]> {
  const grouped = new Map<ChartLabFeatureGroup, ChartLabFeatureDescriptor[]>();
  for (const group of FEATURE_GROUPS) grouped.set(group, []);
  for (const feature of features) grouped.get(feature.group)?.push(feature);
  for (const rows of grouped.values()) rows.sort((a, b) => a.name.localeCompare(b.name));
  return grouped;
}

function conditionTruthRows(tree: Record<string, unknown>): Array<{ label: string; result: boolean }> {
  const rules = Array.isArray(tree.rules) ? tree.rules : [];
  const rows: Array<{ label: string; result: boolean }> = [];
  for (const raw of rules) {
    if (!raw || typeof raw !== "object") continue;
    const rule = raw as Record<string, unknown>;
    const condition = rule.condition;
    if (!condition || typeof condition !== "object") continue;
    const c = condition as Record<string, unknown>;
    const label =
      typeof rule.name === "string"
        ? rule.name
        : [c.left_feature, c.operator, c.right_feature ?? c.right_value]
            .filter(Boolean)
            .join(" ");
    rows.push({ label: label || "condition", result: c.result === true });
  }
  return rows;
}

function formatPrice(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return value.toFixed(value >= 100 ? 2 : 4);
}

function formatFeatureValue(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "missing";
  if (Math.abs(value) >= 1000) return value.toFixed(2);
  if (Math.abs(value) >= 1) return value.toFixed(4);
  return value.toPrecision(4);
}

function formatNumber(value: number | null | undefined): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "-";
  return Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

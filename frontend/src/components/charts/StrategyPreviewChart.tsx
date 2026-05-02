import { useEffect, useMemo, useRef, useState } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type {
  ChartLabBarPreview,
  ChartLabFeaturePlan,
  ChartLabSignalMarker,
} from "@/api/schemas/chartLab";
import { cn } from "@/lib/cn";

/**
 * StrategyPreviewChart - chart-first replay view for `/api/v1/chart-lab/preview`.
 *
 * Layout follows the research-visualizations doctrine: candles + per-bar
 * feature overlays + signal markers in the main pane, oscillators in a
 * separate pane below. Operators see what is happening at a glance instead
 * of hunting through stacked tables.
 *
 * ChartLab overlays use backend-authored feature snapshots only — no frontend
 * indicator recomputation beyond routing keys to panes/colors.
 *
 * Feature-key shape (from backend make_feature_key):
 *   `version|scope|timeframe|namespace.kind|source=...|params=...|lookback=N|shift=N`
 */

export interface PreviewBarRow {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number | null;
  isWarmup?: boolean;
}

export type StrategyPreviewChartMode = "candles" | "line";

export interface StrategyPreviewChartDensity {
  showEntries: boolean;
  showExits: boolean;
  showDerivedOverlays: boolean;
  showManualOverlays: boolean;
  showWarmupBars: boolean;
}

export interface StrategyPreviewChartProps {
  symbol: string;
  bars: PreviewBarRow[];
  preview: ChartLabBarPreview[];
  plan: ChartLabFeaturePlan;
  derivedFeatureKeys: string[];
  manualFeatureKeys: string[];
  visibleFeatureKeys: string[];
  density: StrategyPreviewChartDensity;
  chartMode: StrategyPreviewChartMode;
  resetZoomSignal: number;
  /** When true, markers may show compact text only on the hovered or selected bar. */
  showSignalLabels: boolean;
  selectedBarIndex: number | null | undefined;
  onBarClick?: (barIndex: number) => void;
  onCrosshairBarIndex?: (barIndex: number | null) => void;
  height?: number;
  className?: string;
}

interface ParsedFeatureKey {
  timeframe: string;
  namespace: string;
  kind: string;
}

const PRICE_OVERLAY_KINDS = new Set([
  "open",
  "high",
  "low",
  "close",
  "vwap",
  "ema",
  "sma",
  "wma",
  "hma",
  "supertrend",
  "bollinger_upper",
  "bollinger_lower",
  "bollinger_mid",
  "donchian_upper",
  "donchian_lower",
  "session_high",
  "session_low",
  "prior_day_high",
  "prior_day_low",
  "prior_close",
]);

const OSCILLATOR_KINDS = new Set([
  "rsi",
  "macd",
  "macd_signal",
  "macd_histogram",
  "atr",
  "adx",
  "stochastic_k",
  "stochastic_d",
  "cci",
  "roc",
  "ibs",
  "connors_rsi",
  "zscore",
  "z_score",
]);

const DERIVED_LINE_COLORS = [
  "rgb(95, 178, 232)",
  "rgb(86, 198, 162)",
  "rgb(132, 160, 232)",
  "rgb(120, 200, 220)",
];

const MANUAL_LINE_COLORS = [
  "rgb(232, 162, 86)",
  "rgb(214, 196, 86)",
  "rgb(232, 132, 168)",
  "rgb(200, 120, 200)",
];

function parseFeatureKey(key: string): ParsedFeatureKey | null {
  const parts = key.split("|");
  if (parts.length < 4) return null;
  const timeframe = parts[2];
  const nsKind = parts[3].split(".");
  if (nsKind.length < 2) return null;
  return { timeframe, namespace: nsKind[0], kind: nsKind.slice(1).join(".") };
}

function isPriceOverlay(parsed: ParsedFeatureKey | null): boolean {
  if (!parsed) return false;
  if (parsed.namespace === "price") return true;
  if (parsed.namespace === "session") return true;
  return PRICE_OVERLAY_KINDS.has(parsed.kind);
}

function isOscillator(parsed: ParsedFeatureKey | null): boolean {
  if (!parsed) return false;
  return OSCILLATOR_KINDS.has(parsed.kind);
}

function readTokens(): {
  bg: string;
  fg: string;
  fgMuted: string;
  border: string;
  ok: string;
  danger: string;
  accent: string;
  warn: string;
} {
  const root =
    typeof document !== "undefined" ? getComputedStyle(document.documentElement) : null;
  const v = (key: string, fallback: string): string =>
    root?.getPropertyValue(key).trim() || fallback;
  const rgb = (key: string, fallback: string): string =>
    `rgb(${v(key, fallback).split(/\s+/).join(", ")})`;
  return {
    bg: rgb("--ut-bg-raised", "22 26 31"),
    fg: rgb("--ut-fg", "232 236 240"),
    fgMuted: rgb("--ut-fg-muted", "167 176 184"),
    border: rgb("--ut-border", "36 42 49"),
    ok: rgb("--ut-ok", "56 196 130"),
    danger: rgb("--ut-danger", "232 86 86"),
    accent: rgb("--ut-accent", "95 178 232"),
    warn: rgb("--ut-warn", "232 162 86"),
  };
}

function toUtcSeconds(iso: string): UTCTimestamp {
  return Math.floor(new Date(iso).getTime() / 1000) as UTCTimestamp;
}

function isEntrySignal(marker_type: string): boolean {
  return marker_type.includes("entry");
}

function candleForDensity(
  bar: PreviewBarRow,
  tokens: ReturnType<typeof readTokens>,
  showWarmupBars: boolean,
): CandlestickData<Time> | { time: Time } {
  if (bar.isWarmup && !showWarmupBars) {
    return { time: toUtcSeconds(bar.timestamp) };
  }
  const candle: CandlestickData<Time> = {
    time: toUtcSeconds(bar.timestamp),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  };
  if (bar.isWarmup) {
    return {
      ...candle,
      color: "rgba(167, 176, 184, 0.16)",
      borderColor: "rgba(167, 176, 184, 0.28)",
      wickColor: "rgba(167, 176, 184, 0.32)",
    };
  }
  const up = bar.close >= bar.open;
  return {
    ...candle,
    color: up ? tokens.ok : tokens.danger,
    borderColor: up ? tokens.ok : tokens.danger,
    wickColor: up ? tokens.ok : tokens.danger,
  };
}

function closeLinePoint(
  bar: PreviewBarRow,
  showWarmupBars: boolean,
): LineData<Time> | { time: Time } {
  if (bar.isWarmup && !showWarmupBars) {
    return { time: toUtcSeconds(bar.timestamp) };
  }
  return { time: toUtcSeconds(bar.timestamp), value: bar.close };
}

function withAlpha(rgbColor: string, alpha: number): string {
  return rgbColor.replace(/^rgb\((.*)\)$/i, `rgba($1, ${alpha})`);
}

function volumePoint(
  bar: PreviewBarRow,
  tokens: ReturnType<typeof readTokens>,
): HistogramData<Time> | null {
  if (typeof bar.volume !== "number" || !Number.isFinite(bar.volume)) return null;
  return {
    time: toUtcSeconds(bar.timestamp),
    value: bar.volume,
    color: withAlpha(bar.close >= bar.open ? tokens.ok : tokens.danger, 0.34),
  };
}

function normalizeBars(bars: PreviewBarRow[]): PreviewBarRow[] {
  const seen = new Map<number, PreviewBarRow>();
  for (const bar of bars) seen.set(toUtcSeconds(bar.timestamp), bar);
  return [...seen.entries()].sort(([a], [b]) => a - b).map(([, bar]) => bar);
}

function dedupeLine(points: LineData<Time>[]): LineData<Time>[] {
  const seen = new Map<number, LineData<Time>>();
  for (const point of points) seen.set(point.time as number, point);
  return [...seen.entries()].sort(([a], [b]) => a - b).map(([, p]) => p);
}

function compactMarkerLabel(signal: ChartLabSignalMarker): string {
  const name = signal.signal_name?.trim();
  const raw = signal.marker_type.replace(/^candidate_/i, "");
  const base = name || raw || "signal";
  return base.length > 42 ? `${base.slice(0, 40)}…` : base;
}

function markerFromSignal(
  signal: ChartLabSignalMarker,
  tokens: ReturnType<typeof readTokens>,
  opts: {
    compact: boolean;
    text?: string;
  },
): SeriesMarker<Time> {
  const isEntry = isEntrySignal(signal.marker_type);
  const size = opts.compact ? 0.7 : 1;
  const base: SeriesMarker<Time> = {
    time: toUtcSeconds(signal.timestamp),
    position: isEntry ? "belowBar" : "aboveBar",
    shape: isEntry ? "arrowUp" : "arrowDown",
    color: isEntry ? tokens.ok : tokens.danger,
    size,
  };
  if (opts.text) base.text = opts.text;
  return base;
}

interface FeatureSeriesPoints {
  feature_key: string;
  parsed: ParsedFeatureKey | null;
  points: LineData<Time>[];
  lineage: "derived" | "manual";
}

interface OscillatorGuide {
  key: string;
  value: number;
  label: string;
}

function collectFeatureSeries(params: {
  preview: ChartLabBarPreview[];
  derivedKeys: Set<string>;
  manualKeys: Set<string>;
  visibleDerived: boolean;
  visibleManual: boolean;
  visibleKeys: Set<string>;
}): FeatureSeriesPoints[] {
  const activeKeys = new Set<string>();
  if (params.visibleDerived) {
    for (const k of params.derivedKeys) {
      if (params.visibleKeys.has(k)) activeKeys.add(k);
    }
  }
  if (params.visibleManual) {
    for (const k of params.manualKeys) {
      if (params.visibleKeys.has(k)) activeKeys.add(k);
    }
  }

  const byKey = new Map<string, LineData<Time>[]>();
  const lineageForKey = new Map<string, "derived" | "manual">();
  for (const key of activeKeys) {
    byKey.set(key, []);
    lineageForKey.set(key, params.derivedKeys.has(key) ? "derived" : "manual");
  }
  for (const row of params.preview) {
    const t = toUtcSeconds(row.timestamp);
    for (const fv of row.feature_values) {
      if (!byKey.has(fv.feature_key)) continue;
      if (fv.value === null || !Number.isFinite(fv.value)) continue;
      byKey.get(fv.feature_key)!.push({ time: t, value: fv.value });
    }
  }
  return [...byKey.entries()].map(([feature_key, points]) => ({
    feature_key,
    parsed: parseFeatureKey(feature_key),
    points: dedupeLine(points),
    lineage: lineageForKey.get(feature_key) ?? "manual",
  }));
}

function guideValuesForKind(kind: string): Array<{ value: number; label: string }> {
  if (kind === "rsi" || kind === "connors_rsi") {
    return [
      { value: 70, label: "RSI 70" },
      { value: 50, label: "RSI 50" },
      { value: 30, label: "RSI 30" },
    ];
  }
  if (kind === "stochastic_k" || kind === "stochastic_d") {
    return [
      { value: 80, label: "Stochastic 80" },
      { value: 20, label: "Stochastic 20" },
    ];
  }
  if (kind === "zscore" || kind === "z_score") {
    return [
      { value: 2, label: "Z-Score 2" },
      { value: 0, label: "Z-Score 0" },
      { value: -2, label: "Z-Score -2" },
    ];
  }
  if (kind === "macd" || kind === "macd_signal" || kind === "macd_histogram") {
    return [{ value: 0, label: "MACD 0" }];
  }
  if (kind === "ibs") {
    return [
      { value: 0.8, label: "IBS 0.8" },
      { value: 0.5, label: "IBS 0.5" },
      { value: 0.2, label: "IBS 0.2" },
    ];
  }
  return [];
}

function collectOscillatorGuides(series: FeatureSeriesPoints[]): OscillatorGuide[] {
  const guides = new Map<string, OscillatorGuide>();
  for (const entry of series) {
    const kind = entry.parsed?.kind;
    if (!kind) continue;
    for (const guide of guideValuesForKind(kind)) {
      const key = `${guide.label}:${guide.value}`;
      guides.set(key, { key, ...guide });
    }
  }
  return [...guides.values()];
}

function warmupBandLayout(args: {
  chart: IChartApi;
  preview: ChartLabBarPreview[];
}): { shadeLeft: number; shadeWidth: number; boundaryX: number | null } | null {
  if (args.preview.length === 0) return null;
  const firstActive = args.preview.findIndex((row) => !row.is_warmup);
  if (firstActive <= 0) return null;

  const tFirst = toUtcSeconds(args.preview[0].timestamp);
  const tBoundary =
    firstActive < args.preview.length
      ? toUtcSeconds(args.preview[firstActive].timestamp)
      : toUtcSeconds(args.preview[args.preview.length - 1].timestamp);

  const x0 = args.chart.timeScale().timeToCoordinate(tFirst as Time);
  const xB = args.chart.timeScale().timeToCoordinate(tBoundary as Time);

  if (x0 === null || xB === null) return null;
  const left = Math.min(x0 as number, xB as number);
  const shadeWidth = Math.max(1, Math.abs(xB - x0) - 2);
  return { shadeLeft: left, shadeWidth, boundaryX: xB };
}

export function StrategyPreviewChart({
  symbol,
  bars,
  preview,
  plan,
  derivedFeatureKeys,
  manualFeatureKeys,
  visibleFeatureKeys,
  density,
  chartMode,
  resetZoomSignal,
  showSignalLabels,
  selectedBarIndex,
  onBarClick,
  onCrosshairBarIndex,
  height = 480,
  className,
}: StrategyPreviewChartProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const closeLineRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const candleMarkersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const lineMarkersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const overlaySeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const oscillatorSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const oscillatorGuideSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const tokensRef = useRef(readTokens());

  const [warmupBand, setWarmupBand] = useState<{
    shadeLeft: number;
    shadeWidth: number;
    boundaryX: number | null;
  } | null>(null);

  const [hoverBarIndex, setHoverBarIndex] = useState<number | null>(null);

  const densityRef = useRef(density);
  const previewRef = useRef(preview);
  densityRef.current = density;
  previewRef.current = preview;

  const sortedBars = useMemo(() => normalizeBars(bars), [bars]);
  const candleData = useMemo(
    () =>
      sortedBars.map((bar) =>
        candleForDensity(bar, tokensRef.current, density.showWarmupBars),
      ),
    [density.showWarmupBars, sortedBars],
  );
  const closeLineData = useMemo(
    () => sortedBars.map((bar) => closeLinePoint(bar, density.showWarmupBars)),
    [density.showWarmupBars, sortedBars],
  );
  const volumeData = useMemo(
    () =>
      sortedBars
        .map((bar) => volumePoint(bar, tokensRef.current))
        .filter((point): point is HistogramData<Time> => point !== null),
    [sortedBars],
  );
  const derivedSet = useMemo(() => new Set(derivedFeatureKeys), [derivedFeatureKeys]);
  const manualSet = useMemo(() => new Set(manualFeatureKeys), [manualFeatureKeys]);
  const visibleKeySet = useMemo(() => new Set(visibleFeatureKeys), [visibleFeatureKeys]);

  const series = useMemo(
    () =>
      collectFeatureSeries({
        preview,
        derivedKeys: derivedSet,
        manualKeys: manualSet,
        visibleDerived: density.showDerivedOverlays,
        visibleManual: density.showManualOverlays,
        visibleKeys: visibleKeySet,
      }),
    [
      density.showDerivedOverlays,
      density.showManualOverlays,
      derivedSet,
      manualSet,
      preview,
      visibleKeySet,
    ],
  );

  const overlaySeriesData = useMemo(
    () => series.filter((s) => isPriceOverlay(s.parsed)),
    [series],
  );
  const oscillatorSeriesData = useMemo(
    () => series.filter((s) => !isPriceOverlay(s.parsed) && isOscillator(s.parsed)),
    [series],
  );
  const oscillatorGuides = useMemo(
    () => collectOscillatorGuides(oscillatorSeriesData),
    [oscillatorSeriesData],
  );

  const indexByTs = useMemo(() => {
    const map = new Map<number, number>();
    preview.forEach((row, idx) => map.set(toUtcSeconds(row.timestamp) as number, idx));
    return map;
  }, [preview]);

  const labelPreviewIndex =
    showSignalLabels && hoverBarIndex !== null
      ? hoverBarIndex
      : showSignalLabels &&
          (selectedBarIndex !== null && selectedBarIndex !== undefined)
        ? selectedBarIndex
        : null;

  const labeledBarTime =
    labelPreviewIndex !== null && preview[labelPreviewIndex]
      ? (toUtcSeconds(preview[labelPreviewIndex].timestamp) as number)
      : null;

  const markers = useMemo(() => {
    const tokens = tokensRef.current;
    const out: SeriesMarker<Time>[] = [];
    for (const row of preview) {
      for (const m of row.signal_markers) {
        const isEntry = isEntrySignal(m.marker_type);
        if (isEntry && !density.showEntries) continue;
        if (!isEntry && !density.showExits) continue;
        const t = toUtcSeconds(m.timestamp) as number;
        const showText =
          Boolean(showSignalLabels) && labeledBarTime !== null && t === labeledBarTime;
        out.push(
          markerFromSignal(m, tokens, {
            compact: !showSignalLabels || !showText,
            text: showText ? compactMarkerLabel(m) : undefined,
          }),
        );
      }
    }
    return [...out].sort((a, b) => Number(a.time) - Number(b.time));
  }, [
    density.showEntries,
    density.showExits,
    hoverBarIndex,
    labeledBarTime,
    preview,
    selectedBarIndex,
    showSignalLabels,
  ]);

  function refreshWarmupLayout(): void {
    const chart = chartRef.current;
    const dens = densityRef.current;
    const previewRows = previewRef.current;
    if (
      !chart ||
      !dens.showWarmupBars ||
      previewRows.length === 0 ||
      previewRows.every((row) => !row.is_warmup)
    ) {
      setWarmupBand((prev) => (prev === null ? prev : null));
      return;
    }
    const layout = warmupBandLayout({ chart, preview: previewRows });
    setWarmupBand((prev) => {
      if (!layout && prev === null) return prev;
      if (
        prev &&
        layout &&
        prev.shadeLeft === layout.shadeLeft &&
        prev.shadeWidth === layout.shadeWidth &&
        prev.boundaryX === layout.boundaryX
      ) {
        return prev;
      }
      return layout;
    });
  }

  useEffect(() => {
    if (!containerRef.current) return;
    const tokens = readTokens();
    tokensRef.current = tokens;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: tokens.bg },
        textColor: tokens.fgMuted,
        fontFamily: "Inter, system-ui, sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: tokens.border, style: 0 },
        horzLines: { color: tokens.border, style: 0 },
      },
      rightPriceScale: { borderColor: tokens.border },
      timeScale: { borderColor: tokens.border, timeVisible: true, secondsVisible: false },
      crosshair: {
        vertLine: { color: tokens.accent, width: 1 },
        horzLine: { color: tokens.accent, width: 1 },
      },
      autoSize: true,
    });
    chartRef.current = chart;

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: tokens.ok,
      downColor: tokens.danger,
      borderUpColor: tokens.ok,
      borderDownColor: tokens.danger,
      wickUpColor: tokens.ok,
      wickDownColor: tokens.danger,
    });
    candleRef.current = candle;
    candleMarkersRef.current = createSeriesMarkers(candle, []);

    const closeLine = chart.addSeries(LineSeries, {
      color: tokens.accent,
      lineWidth: 2,
      lastValueVisible: false,
      priceLineVisible: false,
      title: "Close",
      visible: false,
    });
    closeLineRef.current = closeLine;
    lineMarkersRef.current = createSeriesMarkers(closeLine, []);

    const volume = chart.addSeries(
      HistogramSeries,
      {
        color: withAlpha(tokens.fgMuted, 0.28),
        lastValueVisible: false,
        priceFormat: { type: "volume" },
        priceLineVisible: false,
        title: "Volume",
      },
      1,
    );
    volumeRef.current = volume;

    const observer = new ResizeObserver(() => {
      if (!containerRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
      refreshWarmupLayout();
    });
    observer.observe(containerRef.current);

    const onVisibleRange = (): void => {
      refreshWarmupLayout();
    };
    const onLogicalRange = (): void => {
      refreshWarmupLayout();
    };
    chart.timeScale().subscribeVisibleTimeRangeChange(onVisibleRange);
    chart.timeScale().subscribeVisibleLogicalRangeChange(onLogicalRange);

    return () => {
      chart.timeScale().unsubscribeVisibleTimeRangeChange(onVisibleRange);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onLogicalRange);
      observer.disconnect();
      candleMarkersRef.current?.detach();
      lineMarkersRef.current?.detach();
      candleMarkersRef.current = null;
      lineMarkersRef.current = null;
      overlaySeriesRef.current.clear();
      oscillatorSeriesRef.current.clear();
      oscillatorGuideSeriesRef.current.clear();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      closeLineRef.current = null;
      volumeRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!candleRef.current || !closeLineRef.current || !volumeRef.current || !chartRef.current) {
      return;
    }
    candleRef.current.setData(candleData);
    closeLineRef.current.setData(closeLineData);
    volumeRef.current.setData(volumeData);
    candleRef.current.applyOptions({ visible: chartMode === "candles" });
    closeLineRef.current.applyOptions({ visible: chartMode === "line" });
    volumeRef.current.applyOptions({ visible: volumeData.length > 0 });
    chartRef.current.timeScale().fitContent();
    refreshWarmupLayout();
  }, [candleData, chartMode, closeLineData, volumeData]);

  useEffect(() => {
    if (!chartRef.current) return;
    chartRef.current.timeScale().fitContent();
    refreshWarmupLayout();
  }, [resetZoomSignal]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const resolveIndexFromTimeParam = (
      raw: MouseEventParams<Time>["time"],
    ): number | null => {
      if (raw === undefined || raw === null) return null;
      if (typeof raw !== "number") return null;
      const idx = indexByTs.get(raw as number);
      return idx === undefined ? null : idx;
    };

    const crosshairHandler = (param: MouseEventParams<Time>): void => {
      const idx = resolveIndexFromTimeParam(param.time);
      setHoverBarIndex(idx);
      onCrosshairBarIndex?.(idx);
    };

    const clickHandler = (param: MouseEventParams<Time>): void => {
      if (!onBarClick) return;
      const idx = resolveIndexFromTimeParam(param.time);
      if (idx !== null) onBarClick(idx);
    };

    chart.subscribeCrosshairMove(crosshairHandler);
    chart.subscribeClick(clickHandler);
    return () => {
      chart.unsubscribeCrosshairMove(crosshairHandler);
      chart.unsubscribeClick(clickHandler);
    };
  }, [indexByTs, onBarClick, onCrosshairBarIndex]);

  useEffect(() => {
    refreshWarmupLayout();
  }, [density.showWarmupBars, preview, sortedBars]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const reconcile = (
      desired: FeatureSeriesPoints[],
      registry: Map<string, ISeriesApi<"Line">>,
      paneIndex: number,
    ) => {
      const desiredKeys = new Set(desired.map((s) => s.feature_key));
      for (const [key, s] of registry.entries()) {
        if (!desiredKeys.has(key)) {
          try {
            chart.removeSeries(s);
          } catch {
            //
          }
          registry.delete(key);
        }
      }
      let derivedSlot = 0;
      let manualSlot = 0;
      desired.forEach((entry) => {
        const palette =
          entry.lineage === "derived"
            ? DERIVED_LINE_COLORS[derivedSlot++ % DERIVED_LINE_COLORS.length]
            : MANUAL_LINE_COLORS[manualSlot++ % MANUAL_LINE_COLORS.length];

        let line = registry.get(entry.feature_key);
        if (!line) {
          line = chart.addSeries(
            LineSeries,
            {
              color: palette,
              lineWidth: 2,
              lineStyle: entry.lineage === "derived" ? LineStyle.Solid : LineStyle.Dashed,
              lastValueVisible: false,
              priceLineVisible: false,
              title: titleForKey(entry.feature_key, entry.parsed),
            },
            paneIndex,
          );
          registry.set(entry.feature_key, line);
        } else {
          line.applyOptions({
            color: palette,
            lineStyle: entry.lineage === "derived" ? LineStyle.Solid : LineStyle.Dashed,
            title: titleForKey(entry.feature_key, entry.parsed),
          });
        }
        line.setData(entry.points);
      });
    };

    reconcile(overlaySeriesData, overlaySeriesRef.current, 0);
    reconcile(oscillatorSeriesData, oscillatorSeriesRef.current, 2);
  }, [overlaySeriesData, oscillatorSeriesData]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const desiredKeys = new Set(oscillatorGuides.map((guide) => guide.key));
    for (const [key, series] of oscillatorGuideSeriesRef.current.entries()) {
      if (!desiredKeys.has(key)) {
        try {
          chart.removeSeries(series);
        } catch {
          //
        }
        oscillatorGuideSeriesRef.current.delete(key);
      }
    }
    if (sortedBars.length === 0) return;
    const firstTime = toUtcSeconds(sortedBars[0].timestamp);
    const lastTime = toUtcSeconds(sortedBars[sortedBars.length - 1].timestamp);
    oscillatorGuides.forEach((guide) => {
      let line = oscillatorGuideSeriesRef.current.get(guide.key);
      if (!line) {
        line = chart.addSeries(
          LineSeries,
          {
            color: withAlpha(tokensRef.current.fgMuted, 0.55),
            lineWidth: 1,
            lineStyle: LineStyle.Dotted,
            lastValueVisible: false,
            priceLineVisible: false,
            title: guide.label,
          },
          2,
        );
        oscillatorGuideSeriesRef.current.set(guide.key, line);
      } else {
        line.applyOptions({ title: guide.label });
      }
      line.setData([
        { time: firstTime, value: guide.value },
        { time: lastTime, value: guide.value },
      ]);
    });
  }, [oscillatorGuides, sortedBars]);

  useEffect(() => {
    candleMarkersRef.current?.setMarkers(markers);
    lineMarkersRef.current?.setMarkers(markers);
    refreshWarmupLayout();
  }, [markers]);

  return (
    <div
      className={cn("relative w-full", className)}
      aria-label={`Strategy preview chart for ${symbol}`}
      data-testid="strategy-preview-chart-real"
    >
      {density.showWarmupBars ? (
        warmupBand?.shadeLeft !== undefined ? (
          <>
            <div
              aria-hidden="true"
              className="pointer-events-none absolute left-0 right-9 top-[32px] z-[1] overflow-hidden"
              style={{ bottom: "30px" }}
            >
              <div
                className="pointer-events-none absolute top-0 h-full rounded-sm bg-fg-muted/15"
                style={{ left: warmupBand.shadeLeft, width: warmupBand.shadeWidth }}
              />
              {warmupBand.boundaryX !== null ? (
                <div
                  className="pointer-events-none absolute top-0 z-[2] h-full w-px bg-warn/40"
                  style={{ left: warmupBand.boundaryX }}
                  aria-hidden="true"
                />
              ) : null}
              <span
                className="pointer-events-none absolute rounded bg-bg-inset/80 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-fg-muted"
                style={{
                  left: warmupBand.shadeLeft + Math.max(12, warmupBand.shadeWidth * 0.5 - 42),
                  top: 12,
                }}
              >
                Warm-up
              </span>
            </div>
          </>
        ) : null
      ) : null}
      <div className="absolute left-3 top-2 z-10 rounded bg-bg-inset/90 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
        {symbol}
        {plan.feature_keys.length ? ` - ${plan.feature_keys.length} plan keys` : ""}
      </div>
      {volumeData.length ? (
        <div
          className="pointer-events-none absolute left-3 bottom-12 z-10 rounded bg-bg-inset/85 px-2 py-0.5 text-[10px] font-semibold uppercase text-fg-muted"
          data-testid="chart-lab-volume-pane"
        >
          Volume
        </div>
      ) : null}
      <div ref={containerRef} style={{ height }} className="w-full" />
    </div>
  );
}

function titleForKey(key: string, parsed: ParsedFeatureKey | null): string {
  if (!parsed) return key.slice(0, 24);
  return `${parsed.timeframe} ${parsed.kind}`;
}

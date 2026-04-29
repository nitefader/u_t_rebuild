import { useEffect, useMemo, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  createSeriesMarkers,
  type CandlestickData,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type LineData,
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
 * Feature-key shape (from backend make_feature_key):
 *   `version|scope|timeframe|namespace.kind|source=...|params=...|lookback=N|shift=N`
 * We split on `|` and take fields[2] (timeframe), fields[3] (namespace.kind)
 * to decide overlay vs oscillator routing.
 */

export interface PreviewBarRow {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface StrategyPreviewChartProps {
  symbol: string;
  bars: PreviewBarRow[];
  preview: ChartLabBarPreview[];
  plan: ChartLabFeaturePlan;
  /** Subset of feature_keys the operator wants to see plotted. */
  selectedFeatureKeys: string[];
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
]);

function parseFeatureKey(key: string): ParsedFeatureKey | null {
  // version|scope|timeframe|namespace.kind|source=...|params=...|lookback=N|shift=N
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

function toCandle(bar: PreviewBarRow): CandlestickData<Time> {
  return {
    time: toUtcSeconds(bar.timestamp),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
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

function markerFromSignal(
  signal: ChartLabSignalMarker,
  tokens: ReturnType<typeof readTokens>,
): SeriesMarker<Time> {
  const isEntry = signal.marker_type.includes("entry");
  const isLong = signal.side === "long";
  const upArrow = isEntry ? isLong : !isLong;
  return {
    time: toUtcSeconds(signal.timestamp),
    position: upArrow ? "belowBar" : "aboveBar",
    color: isEntry ? (isLong ? tokens.ok : tokens.danger) : tokens.warn,
    shape: upArrow ? "arrowUp" : "arrowDown",
    text: signal.signal_name,
  };
}

const PALETTE = [
  "rgb(95, 178, 232)", // accent
  "rgb(232, 162, 86)", // warn
  "rgb(180, 132, 232)",
  "rgb(86, 198, 162)",
  "rgb(232, 132, 168)",
  "rgb(132, 196, 232)",
  "rgb(214, 196, 86)",
];

function colorForIndex(i: number): string {
  return PALETTE[i % PALETTE.length];
}

interface FeatureSeriesPoints {
  feature_key: string;
  parsed: ParsedFeatureKey | null;
  points: LineData<Time>[];
}

function collectFeatureSeries(
  preview: ChartLabBarPreview[],
  selectedFeatureKeys: string[],
): FeatureSeriesPoints[] {
  const byKey = new Map<string, LineData<Time>[]>();
  for (const key of selectedFeatureKeys) byKey.set(key, []);
  for (const row of preview) {
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
  }));
}

export function StrategyPreviewChart({
  symbol,
  bars,
  preview,
  plan,
  selectedFeatureKeys,
  height = 480,
  className,
}: StrategyPreviewChartProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const overlaySeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const oscillatorSeriesRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const tokensRef = useRef(readTokens());

  const sortedBars = useMemo(() => normalizeBars(bars), [bars]);
  const series = useMemo(
    () => collectFeatureSeries(preview, selectedFeatureKeys),
    [preview, selectedFeatureKeys],
  );

  const overlaySeriesData = useMemo(
    () => series.filter((s) => isPriceOverlay(s.parsed)),
    [series],
  );
  const oscillatorSeriesData = useMemo(
    () => series.filter((s) => !isPriceOverlay(s.parsed) && isOscillator(s.parsed)),
    [series],
  );

  const allSignals = useMemo(() => preview.flatMap((row) => row.signal_markers), [preview]);

  // Build chart once; tear down on unmount.
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
    markersRef.current = createSeriesMarkers(candle, []);

    const observer = new ResizeObserver(() => {
      if (!containerRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      markersRef.current?.detach();
      markersRef.current = null;
      overlaySeriesRef.current.clear();
      oscillatorSeriesRef.current.clear();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
    };
  }, [height]);

  // Push candles when the bar data changes.
  useEffect(() => {
    if (!candleRef.current || !chartRef.current) return;
    candleRef.current.setData(sortedBars.map(toCandle));
    chartRef.current.timeScale().fitContent();
  }, [sortedBars]);

  // Reconcile overlay (main pane) and oscillator (pane 1) line series.
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const reconcile = (
      desired: FeatureSeriesPoints[],
      registry: Map<string, ISeriesApi<"Line">>,
      paneIndex: number,
    ) => {
      const desiredKeys = new Set(desired.map((s) => s.feature_key));
      // Remove series the operator no longer wants displayed.
      for (const [key, s] of registry.entries()) {
        if (!desiredKeys.has(key)) {
          try {
            chart.removeSeries(s);
          } catch {
            // Series may already be detached during teardown.
          }
          registry.delete(key);
        }
      }
      // Add or update.
      desired.forEach((entry, i) => {
        let series = registry.get(entry.feature_key);
        if (!series) {
          series = chart.addSeries(
            LineSeries,
            {
              color: colorForIndex(i),
              lineWidth: 2,
              lastValueVisible: false,
              priceLineVisible: false,
              title: titleForKey(entry.feature_key, entry.parsed),
            },
            paneIndex,
          );
          registry.set(entry.feature_key, series);
        } else {
          series.applyOptions({
            color: colorForIndex(i),
            title: titleForKey(entry.feature_key, entry.parsed),
          });
        }
        series.setData(entry.points);
      });
    };

    reconcile(overlaySeriesData, overlaySeriesRef.current, 0);
    reconcile(oscillatorSeriesData, oscillatorSeriesRef.current, 1);
  }, [overlaySeriesData, oscillatorSeriesData]);

  // Push signal markers.
  useEffect(() => {
    if (!markersRef.current) return;
    const tokens = tokensRef.current;
    const sorted = [...allSignals].sort(
      (a, b) => toUtcSeconds(a.timestamp) - toUtcSeconds(b.timestamp),
    );
    markersRef.current.setMarkers(sorted.map((m) => markerFromSignal(m, tokens)));
  }, [allSignals]);

  return (
    <div className={cn("relative w-full", className)} aria-label={`Strategy preview chart for ${symbol}`}>
      <div className="absolute left-3 top-2 z-10 rounded bg-bg-inset/90 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
        {symbol}
        {plan.feature_keys.length ? ` - ${plan.feature_keys.length} features` : ""}
      </div>
      <div ref={containerRef} style={{ height }} className="w-full" />
    </div>
  );
}

function titleForKey(key: string, parsed: ParsedFeatureKey | null): string {
  if (!parsed) return key.slice(0, 24);
  return `${parsed.timeframe} ${parsed.kind}`;
}

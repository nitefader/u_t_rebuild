import { useEffect, useMemo, useRef } from "react";
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import type { ChartBar } from "@/api/schemas/chartLab";
import { cn } from "@/lib/cn";

/**
 * PriceChart — TradingView lightweight-charts wrapper.
 *
 * Quant note: chart consumes the same `ChartBar` shape the Chart Lab
 * WebSocket emits. Bar timestamps are ISO; we convert to UTC seconds.
 * The chart auto-scales to the visible range.
 *
 * `dataInspectionMode` adds a read-only volume strip and optional VWAP
 * overlay for Data Center historical verification (not Chart Lab).
 *
 * UX note: theme tokens come from CSS variables on `:root` so the
 * chart matches dark/light theme switching without an extra prop.
 */
export interface PriceChartProps {
  bars: ChartBar[];
  symbol: string;
  height?: number;
  className?: string;
  /** Stacked volume + VWAP when present — Data Center inspection path. */
  dataInspectionMode?: boolean;
}

function readTokens(): {
  bg: string;
  fg: string;
  fgMuted: string;
  border: string;
  ok: string;
  danger: string;
  accent: string;
} {
  const root = typeof document !== "undefined" ? getComputedStyle(document.documentElement) : null;
  const v = (key: string, fallback: string): string =>
    root?.getPropertyValue(key).trim() || fallback;
  // Tokens are stored as space-separated RGB triplets in theme.css.
  const rgb = (key: string, fallback: string): string => `rgb(${v(key, fallback)})`;
  return {
    bg: rgb("--ut-bg-raised", "22 26 31"),
    fg: rgb("--ut-fg", "232 236 240"),
    fgMuted: rgb("--ut-fg-muted", "167 176 184"),
    border: rgb("--ut-border", "36 42 49"),
    ok: rgb("--ut-ok", "56 196 130"),
    danger: rgb("--ut-danger", "232 86 86"),
    accent: rgb("--ut-accent", "95 178 232"),
  };
}

function barVwap(bar: ChartBar): number | undefined {
  const v = (bar as Record<string, unknown>).vwap;
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function barVolume(bar: ChartBar): number | undefined {
  const v = bar.volume;
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

function toCandle(bar: ChartBar): CandlestickData<Time> {
  const t = (Math.floor(new Date(bar.timestamp).getTime() / 1000) as UTCTimestamp);
  return { time: t, open: bar.open, high: bar.high, low: bar.low, close: bar.close };
}

function toLinePoint(bar: ChartBar): LineData<Time> {
  const t = (Math.floor(new Date(bar.timestamp).getTime() / 1000) as UTCTimestamp);
  return { time: t, value: bar.close };
}

function toVwapPoint(bar: ChartBar): LineData<Time> | null {
  const vw = barVwap(bar);
  if (vw === undefined) return null;
  const t = (Math.floor(new Date(bar.timestamp).getTime() / 1000) as UTCTimestamp);
  return { time: t, value: vw };
}

function toHistogramPoint(bar: ChartBar, up: string, down: string): HistogramData<Time> | null {
  const vol = barVolume(bar);
  if (vol === undefined) return null;
  const t = (Math.floor(new Date(bar.timestamp).getTime() / 1000) as UTCTimestamp);
  const upBar = bar.close >= bar.open;
  return { time: t, value: vol, color: upBar ? up : down };
}

/** De-dupe and sort bars by timestamp ascending — lightweight-charts requires it. */
function normalizeBars(bars: ChartBar[]): ChartBar[] {
  const seen = new Map<number, ChartBar>();
  for (const bar of bars) {
    const t = Math.floor(new Date(bar.timestamp).getTime() / 1000);
    seen.set(t, bar);
  }
  return [...seen.entries()].sort(([a], [b]) => a - b).map(([, bar]) => bar);
}

export function PriceChart({
  bars,
  symbol,
  height = 320,
  className,
  dataInspectionMode = false,
}: PriceChartProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const vwapSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const tokensRef = useRef(readTokens());

  const sorted = useMemo(() => normalizeBars(bars), [bars]);
  const useCandles = useMemo(() => sorted.some((b) => b.high !== b.low || b.open !== b.close), [sorted]);
  const hasVwap = useMemo(() => sorted.some((b) => barVwap(b) !== undefined), [sorted]);
  const hasVolume = useMemo(() => sorted.some((b) => barVolume(b) !== undefined), [sorted]);

  // Build / tear down the chart once.
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
    candleSeriesRef.current = candle;

    chart.priceScale("right").applyOptions({
      scaleMargins: dataInspectionMode ? { top: 0.05, bottom: 0.22 } : { top: 0.05, bottom: 0.05 },
    });

    const line = chart.addSeries(LineSeries, {
      color: tokens.accent,
      lineWidth: 2,
      visible: false,
    });
    lineSeriesRef.current = line;

    if (dataInspectionMode) {
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "",
        color: tokens.fgMuted,
      });
      volumeSeriesRef.current = volumeSeries;
      chart.priceScale("").applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
      });

      const vwapSeries = chart.addSeries(LineSeries, {
        color: tokens.accent,
        lineWidth: 1,
        lineStyle: 1,
        visible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      });
      vwapSeriesRef.current = vwapSeries;
    }

    const observer = new ResizeObserver(() => {
      if (!containerRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({ width: containerRef.current.clientWidth });
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      lineSeriesRef.current = null;
      volumeSeriesRef.current = null;
      vwapSeriesRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [height, dataInspectionMode]);

  // Push data on every bar change.
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current || !lineSeriesRef.current) return;
    if (useCandles) {
      candleSeriesRef.current.applyOptions({ visible: true });
      lineSeriesRef.current.applyOptions({ visible: false });
      candleSeriesRef.current.setData(sorted.map(toCandle));
    } else {
      candleSeriesRef.current.applyOptions({ visible: false });
      lineSeriesRef.current.applyOptions({ visible: true });
      lineSeriesRef.current.setData(sorted.map(toLinePoint));
    }

    if (chartRef.current) {
      chartRef.current.priceScale("right").applyOptions({
        scaleMargins:
          dataInspectionMode && hasVolume ? { top: 0.05, bottom: 0.22 } : { top: 0.05, bottom: 0.05 },
      });
    }

    if (dataInspectionMode && volumeSeriesRef.current && hasVolume) {
      const pts = sorted.map((b) => toHistogramPoint(b, tokensRef.current.ok, tokensRef.current.danger)).filter(
        (p): p is HistogramData<Time> => p !== null,
      );
      volumeSeriesRef.current.applyOptions({ visible: pts.length > 0 });
      if (pts.length) volumeSeriesRef.current.setData(pts);
    } else if (volumeSeriesRef.current) {
      volumeSeriesRef.current.applyOptions({ visible: false });
    }

    if (dataInspectionMode && vwapSeriesRef.current && hasVwap) {
      const pts = sorted.map(toVwapPoint).filter((p): p is LineData<Time> => p !== null);
      vwapSeriesRef.current.applyOptions({ visible: pts.length > 0 });
      if (pts.length) vwapSeriesRef.current.setData(pts);
    } else if (vwapSeriesRef.current) {
      vwapSeriesRef.current.applyOptions({ visible: false });
    }

    chartRef.current.timeScale().fitContent();
  }, [sorted, useCandles, dataInspectionMode, hasVolume, hasVwap]);

  return (
    <div className={cn("relative w-full", className)} aria-label={`Price chart for ${symbol}`}>
      <div ref={containerRef} style={{ height }} />
    </div>
  );
}

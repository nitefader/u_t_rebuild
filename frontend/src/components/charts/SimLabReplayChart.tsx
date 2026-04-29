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
import { cn } from "@/lib/cn";

/**
 * SimLabReplayChart — chart-first view of a streaming sim run.
 *
 * Operator design language: dense, visual, "see what is going on at a
 * glance." Bars render as candles; virtual fills appear as triangle
 * markers (long/buy below the bar in green, short/sell above in red);
 * a thin equity overlay tracks per-tick PnL on a separate price scale
 * so it never fights the bar scale.
 *
 * The chart updates incrementally — the `bars`, `fills`, and `equity`
 * arrays are appended each WS message — so lightweight-charts only
 * pays the diff cost, not a full redraw.
 */
export interface SimLabReplayBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface SimLabReplayFill {
  timestamp: string;
  side: "buy" | "sell" | "long" | "short";
  intent?: "open" | "close" | "entry" | "exit";
  price: number;
  qty?: number;
}

export interface SimLabReplayEquityPoint {
  timestamp: string;
  value: number;
}

export interface SimLabReplayChartProps {
  symbol: string;
  bars: SimLabReplayBar[];
  fills: SimLabReplayFill[];
  equity?: SimLabReplayEquityPoint[];
  height?: number;
  className?: string;
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
  const root = typeof document !== "undefined" ? getComputedStyle(document.documentElement) : null;
  const v = (key: string, fallback: string): string =>
    root?.getPropertyValue(key).trim() || fallback;
  const rgb = (key: string, fallback: string): string => `rgb(${v(key, fallback)})`;
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

function toCandle(bar: SimLabReplayBar): CandlestickData<Time> {
  return {
    time: toUtcSeconds(bar.timestamp),
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
  };
}

function toEquityLine(point: SimLabReplayEquityPoint): LineData<Time> {
  return { time: toUtcSeconds(point.timestamp), value: point.value };
}

function fillIsEntry(fill: SimLabReplayFill): boolean {
  if (fill.intent === "open" || fill.intent === "entry") return true;
  if (fill.intent === "close" || fill.intent === "exit") return false;
  // Without explicit intent, treat buy/long as entry, sell/short as exit.
  return fill.side === "buy" || fill.side === "long";
}

function toMarker(fill: SimLabReplayFill, tokens: ReturnType<typeof readTokens>): SeriesMarker<Time> {
  const entry = fillIsEntry(fill);
  return {
    time: toUtcSeconds(fill.timestamp),
    position: entry ? "belowBar" : "aboveBar",
    color: entry ? tokens.ok : tokens.danger,
    shape: entry ? "arrowUp" : "arrowDown",
    text: fill.qty != null ? `${entry ? "+" : "-"}${fill.qty}` : entry ? "buy" : "sell",
  };
}

/** De-dupe and sort bars so lightweight-charts doesn't reject the series. */
function normalizeBars(bars: SimLabReplayBar[]): SimLabReplayBar[] {
  const seen = new Map<number, SimLabReplayBar>();
  for (const bar of bars) {
    seen.set(toUtcSeconds(bar.timestamp), bar);
  }
  return [...seen.entries()].sort(([a], [b]) => a - b).map(([, bar]) => bar);
}

function normalizeEquity(points: SimLabReplayEquityPoint[]): SimLabReplayEquityPoint[] {
  const seen = new Map<number, SimLabReplayEquityPoint>();
  for (const point of points) {
    if (!Number.isFinite(point.value)) continue;
    seen.set(toUtcSeconds(point.timestamp), point);
  }
  return [...seen.entries()].sort(([a], [b]) => a - b).map(([, p]) => p);
}

export function SimLabReplayChart({
  symbol,
  bars,
  fills,
  equity = [],
  height = 320,
  className,
}: SimLabReplayChartProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const equityRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const tokensRef = useRef(readTokens());

  const sortedBars = useMemo(() => normalizeBars(bars), [bars]);
  const sortedEquity = useMemo(() => normalizeEquity(equity), [equity]);

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

    const equityLine = chart.addSeries(LineSeries, {
      color: tokens.accent,
      lineWidth: 2,
      priceScaleId: "equity",
      priceLineVisible: false,
      lastValueVisible: true,
      title: "equity",
    });
    chart.priceScale("equity").applyOptions({
      scaleMargins: { top: 0.65, bottom: 0.05 },
      borderColor: tokens.border,
    });
    equityRef.current = equityLine;

    return () => {
      markersRef.current?.detach();
      markersRef.current = null;
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      equityRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    if (!candleRef.current) return;
    candleRef.current.setData(sortedBars.map(toCandle));
    chartRef.current?.timeScale().fitContent();
  }, [sortedBars]);

  useEffect(() => {
    if (!equityRef.current) return;
    equityRef.current.setData(sortedEquity.map(toEquityLine));
  }, [sortedEquity]);

  useEffect(() => {
    if (!markersRef.current) return;
    const tokens = tokensRef.current;
    const sortedFills = [...fills].sort(
      (a, b) => toUtcSeconds(a.timestamp) - toUtcSeconds(b.timestamp),
    );
    markersRef.current.setMarkers(sortedFills.map((f) => toMarker(f, tokens)));
  }, [fills]);

  return (
    <div className={cn("relative", className)}>
      <div className="absolute left-3 top-2 z-10 rounded bg-bg-inset/90 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-fg-muted">
        {symbol}
      </div>
      <div ref={containerRef} style={{ height }} className="w-full" />
    </div>
  );
}

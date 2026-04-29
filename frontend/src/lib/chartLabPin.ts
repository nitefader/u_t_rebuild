import { useCallback, useEffect, useState } from "react";

/**
 * useChartLabPin — operator pin for the home dashboard hub card.
 *
 * Persists the pinned symbol in localStorage and broadcasts changes
 * across React subtrees in the same tab via a CustomEvent. The
 * Dashboard hub card subscribes; ChartLab is the publisher.
 *
 * Pin is *per browser* — it is not server state. The backend never
 * needs to know which symbol an operator pinned.
 */
const STORAGE_KEY = "ut.dashboard.chartLabPin";
const EVENT_NAME = "ut:chart-lab-pin-changed";

export function readChartLabPin(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw && raw.trim() ? raw.trim().toUpperCase() : null;
  } catch {
    return null;
  }
}

export function writeChartLabPin(symbol: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (symbol && symbol.trim()) {
      window.localStorage.setItem(STORAGE_KEY, symbol.trim().toUpperCase());
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
    window.dispatchEvent(new CustomEvent(EVENT_NAME));
  } catch {
    // localStorage may be disabled (private mode); pin is best-effort.
  }
}

export function useChartLabPin(): {
  symbol: string | null;
  pin: (symbol: string) => void;
  unpin: () => void;
} {
  const [symbol, setSymbol] = useState<string | null>(() => readChartLabPin());

  useEffect(() => {
    function refresh(): void {
      setSymbol(readChartLabPin());
    }
    window.addEventListener(EVENT_NAME, refresh);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener(EVENT_NAME, refresh);
      window.removeEventListener("storage", refresh);
    };
  }, []);

  const pin = useCallback((s: string) => writeChartLabPin(s), []);
  const unpin = useCallback(() => writeChartLabPin(null), []);
  return { symbol, pin, unpin };
}

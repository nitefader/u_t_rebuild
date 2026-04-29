/**
 * Operator-grade formatters.
 *
 * Quant note: trading numbers must be precise and visually
 * comparable. Currency uses 2-decimal grouping; percent uses 2
 * decimals; quantity uses up to 6 decimals (fractional shares).
 * Timestamps render in the operator's local zone with a stable,
 * sortable shape.
 */

const usd2 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const usd0 = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
});

const pct2 = new Intl.NumberFormat("en-US", {
  style: "percent",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const qtyFmt = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 6,
});

export function formatCurrency(value: number | null | undefined, opts?: { whole?: boolean }): string {
  if (value == null || Number.isNaN(value)) return "—";
  return opts?.whole ? usd0.format(value) : usd2.format(value);
}

export function formatPercent(value: number | null | undefined, opts?: { fromBasisPoints?: boolean }): string {
  if (value == null || Number.isNaN(value)) return "—";
  const v = opts?.fromBasisPoints ? value / 10000 : value / 100;
  return pct2.format(v);
}

export function formatQuantity(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return qtyFmt.format(value);
}

export function formatSignedCurrency(value: number | null | undefined): {
  text: string;
  tone: "ok" | "danger" | "neutral";
} {
  if (value == null || Number.isNaN(value)) return { text: "—", tone: "neutral" };
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  const abs = usd2.format(Math.abs(value));
  return {
    text: `${sign}${abs}`,
    tone: value > 0 ? "ok" : value < 0 ? "danger" : "neutral",
  };
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const diffMs = Date.now() - d.getTime();
  const sec = Math.round(diffMs / 1000);
  if (Math.abs(sec) < 5) return "just now";
  if (Math.abs(sec) < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (Math.abs(min) < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (Math.abs(hr) < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  return `${day}d ago`;
}

/** Stable, machine-friendly idempotency key for operator mutations. */
export function newIdempotencyKey(prefix = "ut"): string {
  const rand = crypto.randomUUID().replace(/-/g, "");
  return `${prefix}-${Date.now().toString(36)}-${rand.slice(0, 12)}`;
}

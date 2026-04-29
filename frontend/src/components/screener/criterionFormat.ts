import type {
  ScreenerCriterion,
  ScreenerCriterionOperator,
  ScreenerFieldDefinition,
  ScreenerFieldValue,
  ScreenerMetric,
} from "@/api/schemas/screener";

export const OPERATOR_LABELS: { value: ScreenerCriterionOperator; label: string }[] = [
  { value: "gte", label: ">=" },
  { value: "gt", label: ">" },
  { value: "lte", label: "<=" },
  { value: "lt", label: "<" },
  { value: "eq", label: "=" },
  { value: "between", label: "between" },
];

const METRIC_LABELS: Partial<Record<ScreenerMetric, string>> = {
  price: "Last price",
  avg_volume_20d: "Average volume (20d)",
  relative_volume: "Relative volume",
  gap_pct: "Gap from prior close",
  change_pct: "Change from prior close",
  rsi_14: "RSI(14)",
  atr_14_pct: "ATR(14) as percent of price",
  prior_day_close: "Prior day close",
  prior_day_range_pct: "Prior day range",
  "broker.tradable": "Tradable at Alpaca",
  "broker.fractionable": "Fractionable at Alpaca",
  "broker.shortable": "Shortable at Alpaca",
  "broker.easy_to_borrow": "Easy to borrow at Alpaca",
  "broker.active": "Active at Alpaca",
  "broker.exchange": "Exchange",
  "broker.asset_class": "Asset class",
  "broker.name": "Company name",
};

export function operatorLabel(operator: ScreenerCriterionOperator): string {
  return OPERATOR_LABELS.find((item) => item.value === operator)?.label ?? operator;
}

export function metricLabel(metric: ScreenerMetric, field?: ScreenerFieldDefinition): string {
  return field?.label ?? METRIC_LABELS[metric] ?? prettyKey(metric);
}

export function formatCriterion(
  criterion: ScreenerCriterion,
  field?: ScreenerFieldDefinition,
): string {
  const label = criterion.label || metricLabel(criterion.metric, field);
  const unit = field?.unit ?? unitForMetric(criterion.metric);
  if (criterion.operator === "eq" && typeof criterion.value === "boolean") {
    return `${label}: ${criterion.value ? "Yes" : "No"}`;
  }
  if (criterion.operator === "between") {
    return `${label} between ${formatFieldValue(criterion.value, unit)} and ${formatFieldValue(criterion.value_max ?? "", unit)}`;
  }
  if (criterion.operator === "eq") {
    return `${label}: ${formatFieldValue(criterion.value, unit)}`;
  }
  return `${label} ${operatorLabel(criterion.operator)} ${formatFieldValue(criterion.value, unit)}`;
}

export function formatFieldValue(value: ScreenerFieldValue | number | null | undefined, unit?: string | null): string {
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "string") return value;
  if (unit === "$") return `$${formatNumber(value, 2)}`;
  if (unit === "%") return `${formatNumber(value, 2)}%`;
  if (unit === "x") return `${formatNumber(value, 2)}x`;
  if (unit === "shares") return formatShares(value);
  if (unit === "0..100") return formatNumber(value, 1);
  return formatNumber(value, Number.isInteger(value) ? 0 : 2);
}

function unitForMetric(metric: ScreenerMetric): string | null {
  if (metric === "price" || metric === "prior_day_close") return "$";
  if (metric === "avg_volume_20d") return "shares";
  if (metric === "relative_volume") return "x";
  if (
    metric === "gap_pct" ||
    metric === "change_pct" ||
    metric === "atr_14_pct" ||
    metric === "prior_day_range_pct"
  ) {
    return "%";
  }
  if (metric === "rsi_14") return "0..100";
  return null;
}

function formatNumber(value: number, digits: number): string {
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function formatShares(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toFixed(0);
}

function prettyKey(key: string): string {
  return key
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

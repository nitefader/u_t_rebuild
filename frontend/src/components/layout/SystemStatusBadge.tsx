import { useQuery } from "@tanstack/react-query";
import { SystemApi } from "@/api/system";
import { StatusBadge } from "@/components/badges/StatusBadge";
import { PulseDot } from "@/components/ui/PulseDot";
import { cn } from "@/lib/cn";

/**
 * Top-nav system status badge.
 * Reads /api/v1/system/status and renders a single-glance line:
 *   "Alpaca · Paper · IEX"  with a healthy / warn / danger dot.
 *
 * Operator vs marketing: this badge always says what it is reading
 * from. No silent green.
 */
export function SystemStatusBadge({ className }: { className?: string }): JSX.Element {
  const q = useQuery({
    queryKey: ["system", "status"],
    queryFn: () => SystemApi.status(),
    refetchInterval: 30_000,
    staleTime: 10_000,
  });

  if (q.isLoading) {
    return (
      <span className={cn("inline-flex items-center gap-2 text-xs text-fg-muted", className)}>
        <PulseDot tone="muted" pulse size="sm" />
        Checking platform…
      </span>
    );
  }

  if (q.isError || !q.data) {
    return (
      <span className={cn("inline-flex items-center gap-2 text-xs", className)}>
        <PulseDot tone="danger" size="sm" />
        <StatusBadge tone="danger">Backend unreachable</StatusBadge>
      </span>
    );
  }

  const s = q.data;
  const credentialsMissing = !s.alpaca_credentials_present;
  const envConflict = Boolean(s.operator_environment_conflict);
  const tone = credentialsMissing || envConflict ? "warn" : s.alpaca_test_stream ? "info" : "ok";
  const feed = (s.alpaca_data_feed ?? "iex").toUpperCase();
  const env = s.operator_environment;

  return (
    <span className={cn("inline-flex items-center gap-2 text-xs", className)} title={describe(s)}>
      <PulseDot tone={tone} pulse={tone === "ok"} size="sm" />
      <StatusBadge tone={tone}>
        {credentialsMissing ? "Alpaca · not configured" : `Alpaca · ${env} · ${s.alpaca_test_stream ? "TEST" : feed}`}
      </StatusBadge>
    </span>
  );
}

function describe(s: { alpaca_endpoint: string; operator_environment: string; operator_environment_source: string; alpaca_credentials_present: boolean; alpaca_test_stream: boolean; alpaca_data_feed?: string | null; operator_environment_conflict?: string | null }): string {
  const lines = [
    `Endpoint: ${s.alpaca_endpoint}`,
    `Environment: ${s.operator_environment} (${s.operator_environment_source})`,
    `Credentials: ${s.alpaca_credentials_present ? "configured" : "missing"}`,
    `Market data: ${s.alpaca_test_stream ? "FAKEPACA test stream" : `${(s.alpaca_data_feed ?? "iex").toUpperCase()} feed`}`,
  ];
  if (s.operator_environment_conflict) lines.push(`Conflict: ${s.operator_environment_conflict}`);
  return lines.join("\n");
}

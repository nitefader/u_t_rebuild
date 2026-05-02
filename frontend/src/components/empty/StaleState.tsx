import { CloudOff } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";

/**
 * StaleState — fourth chart-container state alongside Loading / Empty / Error.
 *
 * Surfaces when a live data source (WebSocket stream, broker sync) has
 * disconnected or fallen behind freshness bounds. Distinct from Error
 * because the chart still has *some* historical data; it just stopped
 * updating. Operator should know the picture is frozen, not pretend it
 * is live.
 */
export interface StaleStateProps {
  title?: string;
  message?: React.ReactNode;
  /** e.g. "Last update 3m ago" — surfaced beneath the message. */
  detail?: string;
  onReconnect?: () => void;
  className?: string;
}

export function StaleState({
  title = "Live data is stale",
  message = "The stream is disconnected or behind freshness bounds. Showing the last known data.",
  detail,
  onReconnect,
  className,
}: StaleStateProps): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-start gap-3 rounded-md border border-warn/40 bg-warn-subtle px-4 py-3 text-sm",
        className,
      )}
    >
      <CloudOff className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-warn">{title}</div>
        {message ? <div className="mt-1 text-fg/90">{message}</div> : null}
        {detail ? (
          <div className="mt-1 text-xs text-fg-muted">
            <span className="text-fg-subtle">last:</span> {detail}
          </div>
        ) : null}
      </div>
      {onReconnect ? (
        <Button variant="secondary" size="sm" onClick={onReconnect}>
          Reconnect
        </Button>
      ) : null}
    </div>
  );
}

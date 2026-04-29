import { Hourglass } from "lucide-react";
import { ApiError } from "@/api/client";
import { Banner } from "@/components/ui/Banner";
import { ErrorState } from "./ErrorState";

/**
 * AwaitingApi — when a typed client is in place but the backend route
 * is not yet registered, the operator sees an honest "awaiting"
 * panel instead of a 404 error masquerading as data corruption.
 *
 * 404 + endpoint label match → render the awaiting state.
 * Anything else → render ErrorState (real failure surfaces, never silent).
 */
export interface AwaitingApiProps {
  title: string;
  endpoint: string;
  awaitingMessage: string;
  error: unknown;
  onRetry?: () => void;
}

export function AwaitingApiOrError({
  title,
  endpoint,
  awaitingMessage,
  error,
  onRetry,
}: AwaitingApiProps): JSX.Element {
  if (isAwaiting(error)) {
    return (
      <div className="rounded-md border border-info/40 bg-info-subtle px-4 py-3 text-sm">
        <div className="flex items-start gap-3">
          <Hourglass className="mt-0.5 h-4 w-4 shrink-0 text-info" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-info">{title}</div>
            <div className="mt-1 text-fg/90">{awaitingMessage}</div>
            <div className="mt-2 font-mono text-[11px] text-fg-subtle">{endpoint}</div>
          </div>
        </div>
      </div>
    );
  }
  return (
    <ErrorState
      title={`Could not load ${title.toLowerCase()}`}
      detail={error instanceof Error ? error.message : String(error)}
      onRetry={onRetry}
    />
  );
}

export function isAwaiting(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}

export function AwaitingApiBanner({
  title,
  endpoint,
  message,
}: {
  title: string;
  endpoint: string;
  message: string;
}): JSX.Element {
  return (
    <Banner
      severity="info"
      title={title}
      message={
        <div className="space-y-1">
          <div>{message}</div>
          <div className="font-mono text-[11px] text-fg-subtle">{endpoint}</div>
        </div>
      }
    />
  );
}

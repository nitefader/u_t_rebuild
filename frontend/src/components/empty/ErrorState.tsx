import { CircleAlert } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";

export interface ErrorStateProps {
  title?: string;
  message?: React.ReactNode;
  /** Operator-readable detail (e.g. ApiError.detail). Shown in a quiet line. */
  detail?: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Something failed",
  message,
  detail,
  onRetry,
  className,
}: ErrorStateProps): JSX.Element {
  return (
    <div
      role="alert"
      className={cn(
        "flex items-start gap-3 rounded-md border border-danger/40 bg-danger-subtle px-4 py-3 text-sm",
        className,
      )}
    >
      <CircleAlert className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-danger">{title}</div>
        {message ? <div className="mt-1 text-fg/90">{message}</div> : null}
        {detail ? (
          <div className="mt-1 text-xs text-fg-muted">
            <span className="text-fg-subtle">detail:</span> {detail}
          </div>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" size="sm" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}

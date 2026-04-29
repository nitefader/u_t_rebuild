import { cn } from "@/lib/cn";

export interface LoadingStateProps {
  title?: string;
  message?: React.ReactNode;
  className?: string;
}

export function LoadingState({ title = "Loading", message, className }: LoadingStateProps): JSX.Element {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex items-center gap-3 rounded-md border border-border bg-bg-raised px-4 py-3 text-sm",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-fg-muted border-t-transparent"
      />
      <div>
        <div className="font-medium">{title}</div>
        {message ? <div className="text-xs text-fg-muted">{message}</div> : null}
      </div>
    </div>
  );
}

import { cn } from "@/lib/cn";

export interface EmptyStateProps {
  title: string;
  message?: React.ReactNode;
  action?: React.ReactNode;
  icon?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title, message, action, icon, className }: EmptyStateProps): JSX.Element {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-md border border-border border-dashed bg-bg-subtle px-6 py-10 text-center",
        className,
      )}
    >
      {icon ? <div className="text-fg-subtle">{icon}</div> : null}
      <div>
        <div className="text-sm font-semibold text-fg">{title}</div>
        {message ? <div className="mt-1 text-xs text-fg-muted">{message}</div> : null}
      </div>
      {action ? <div>{action}</div> : null}
    </div>
  );
}

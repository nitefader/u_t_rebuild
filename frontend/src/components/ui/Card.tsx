import { cn } from "@/lib/cn";

/**
 * Dense card primitive.
 *
 * UX rule: information density is a feature. Cards do not get
 * taller to make space; they get denser. Whitespace lives in the
 * margins, not inside the content.
 */
export interface CardProps {
  className?: string;
  children: React.ReactNode;
  /** True for the operator-default raised look (cards on the page). */
  raised?: boolean;
}

export function Card({ className, children, raised = true }: CardProps): JSX.Element {
  return (
    <div
      className={cn(
        "rounded-md border border-border",
        raised ? "bg-bg-raised shadow-card" : "bg-bg-subtle",
        className,
      )}
    >
      {children}
    </div>
  );
}

export interface CardHeaderProps {
  className?: string;
  children: React.ReactNode;
}

export function CardHeader({ className, children }: CardHeaderProps): JSX.Element {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 px-4 py-2.5 border-b border-border/70",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <h2 className={cn("text-sm font-semibold tracking-tight", className)}>{children}</h2>
  );
}

export function CardSubtitle({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}): JSX.Element {
  return <p className={cn("text-xs text-fg-muted", className)}>{children}</p>;
}

export function CardBody({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}): JSX.Element {
  return <div className={cn("px-4 py-3", className)}>{children}</div>;
}

export function CardFooter({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}): JSX.Element {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 px-4 py-2.5 border-t border-border/70 text-xs text-fg-muted",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Compact KPI tile for the Dashboard. */
export interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  sublabel?: React.ReactNode;
  trailing?: React.ReactNode;
  tone?: "ok" | "warn" | "danger" | "info" | "ai" | "neutral";
  className?: string;
}

const KPI_TONE: Record<NonNullable<KpiCardProps["tone"]>, string> = {
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
  ai: "text-ai",
  neutral: "text-fg",
};

export function KpiCard({ label, value, sublabel, trailing, tone = "neutral", className }: KpiCardProps): JSX.Element {
  return (
    <Card className={cn("flex flex-col", className)}>
      <div className="flex items-start justify-between gap-3 px-4 pt-3">
        <span className="text-xs font-medium uppercase tracking-wide text-fg-muted">{label}</span>
        {trailing}
      </div>
      <div className="px-4 pb-3 pt-1">
        <div className={cn("text-2xl font-semibold tabular leading-tight", KPI_TONE[tone])}>{value}</div>
        {sublabel ? <div className="mt-1 text-xs text-fg-muted">{sublabel}</div> : null}
      </div>
    </Card>
  );
}

import { AlertTriangle, CircleAlert, CircleCheck, Info } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Banner — page-level alert that stays visible for the lifetime
 * of the condition.
 *
 * Use for Operations-wide states: global kill, Live Stock Data
 * down, all Account Trade Sync down, system recovery in progress.
 *
 * Per the design language: never silent. Every banner states why
 * it exists and what the operator can do about it.
 */
export type BannerSeverity = "danger" | "warning" | "info" | "success";

export interface BannerProps {
  severity: BannerSeverity;
  title: string;
  message?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}

const SEVERITY_MAP: Record<
  BannerSeverity,
  { icon: typeof AlertTriangle; surface: string; text: string }
> = {
  danger: {
    icon: CircleAlert,
    surface: "bg-danger-subtle border-danger/40",
    text: "text-danger",
  },
  warning: {
    icon: AlertTriangle,
    surface: "bg-warn-subtle border-warn/40",
    text: "text-warn",
  },
  info: {
    icon: Info,
    surface: "bg-info-subtle border-info/40",
    text: "text-info",
  },
  success: {
    icon: CircleCheck,
    surface: "bg-ok-subtle border-ok/40",
    text: "text-ok",
  },
};

export function Banner({ severity, title, message, action, className }: BannerProps): JSX.Element {
  const { icon: Icon, surface, text } = SEVERITY_MAP[severity];
  return (
    <div
      role={severity === "danger" || severity === "warning" ? "alert" : "status"}
      className={cn(
        "flex items-start gap-3 rounded border px-3 py-2.5 text-sm",
        surface,
        className,
      )}
    >
      <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", text)} aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <div className={cn("font-semibold", text)}>{title}</div>
        {message ? <div className="mt-1 text-fg/90">{message}</div> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

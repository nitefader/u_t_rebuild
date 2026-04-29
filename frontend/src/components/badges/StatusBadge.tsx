import { cn } from "@/lib/cn";

/**
 * StatusBadge — compact, factual, one-word badge.
 *
 * Banned: any badge that asserts safety without backing data
 * (e.g. "Safe"). The operator must always know what each badge
 * is reading from.
 */
export type StatusTone = "ok" | "warn" | "danger" | "info" | "ai" | "muted" | "neutral";

export interface StatusBadgeProps {
  tone?: StatusTone;
  size?: "sm" | "md";
  children: React.ReactNode;
  className?: string;
}

const TONE_MAP: Record<StatusTone, string> = {
  ok: "bg-ok-subtle text-ok border-ok/30",
  warn: "bg-warn-subtle text-warn border-warn/30",
  danger: "bg-danger-subtle text-danger border-danger/30",
  info: "bg-info-subtle text-info border-info/30",
  ai: "bg-ai-subtle text-ai border-ai/30",
  muted: "bg-bg-inset text-fg-subtle border-border",
  neutral: "bg-bg-inset text-fg-muted border-border",
};

const SIZE_MAP = {
  sm: "px-1.5 py-0.5 text-[10px]",
  md: "px-2 py-0.5 text-xs",
};

export function StatusBadge({ tone = "neutral", size = "md", children, className }: StatusBadgeProps): JSX.Element {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border font-medium uppercase tracking-wide leading-none",
        TONE_MAP[tone],
        SIZE_MAP[size],
        className,
      )}
    >
      {children}
    </span>
  );
}

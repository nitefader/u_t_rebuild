import { cn } from "@/lib/cn";

/**
 * PulseDot — small filled dot that *pulses* when the underlying
 * signal is alive. Pulse animation is 1.4s ease-in-out and
 * respects `prefers-reduced-motion` (defined in theme.css).
 *
 * Tone is the operator's read of the underlying state. Pulse is
 * controlled separately so a "stale but technically connected"
 * stream renders amber-non-pulsing rather than green-pulsing.
 */
export type PulseTone = "ok" | "warn" | "danger" | "info" | "ai" | "muted";

export interface PulseDotProps {
  tone: PulseTone;
  pulse?: boolean;
  size?: "sm" | "md" | "lg";
  /** Accessible label for screen readers. */
  label?: string;
  className?: string;
}

const SIZE_MAP: Record<NonNullable<PulseDotProps["size"]>, string> = {
  sm: "h-1.5 w-1.5",
  md: "h-2 w-2",
  lg: "h-2.5 w-2.5",
};

const TONE_MAP: Record<PulseTone, { bg: string; ring: string }> = {
  ok: { bg: "bg-ok", ring: "ring-ok/40" },
  warn: { bg: "bg-warn", ring: "ring-warn/40" },
  danger: { bg: "bg-danger", ring: "ring-danger/40" },
  info: { bg: "bg-info", ring: "ring-info/40" },
  ai: { bg: "bg-ai", ring: "ring-ai/40" },
  muted: { bg: "bg-fg-subtle", ring: "ring-fg-subtle/30" },
};

export function PulseDot({ tone, pulse = false, size = "md", label, className }: PulseDotProps): JSX.Element {
  const sz = SIZE_MAP[size];
  const tn = TONE_MAP[tone];
  return (
    <span
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn("relative inline-flex items-center justify-center align-middle", className)}
    >
      {/* Halo (only visible while pulsing) */}
      {pulse && (
        <span
          aria-hidden="true"
          className={cn(
            "absolute inline-flex h-full w-full rounded-full ring-2 animate-ut-pulse",
            tn.ring,
            sz,
          )}
        />
      )}
      {/* Solid core */}
      <span
        aria-hidden="true"
        className={cn("inline-flex rounded-full", sz, tn.bg, pulse ? "animate-ut-pulse" : null)}
      />
    </span>
  );
}

import { Wifi, WifiOff, WifiHigh, WifiLow } from "lucide-react";
import { cn } from "@/lib/cn";
import { PulseDot, type PulseTone } from "@/components/ui/PulseDot";

/**
 * SyncSignal — wifi-style glyph encoding broker stream / market
 * data stream / Account Trade Sync state at a glance.
 *
 * Glyph and pulse must be in sync. A green pulsing wifi means the
 * operator can trust the stream; anything else is a flag.
 */
export type SyncState =
  | "connected"        // running + recent events
  | "idle"             // running + no recent events but ok
  | "reconnecting"
  | "stale"            // running + last event old
  | "down"
  | "credentials_invalid"
  | "operator_paused";

export interface SyncSignalProps {
  state: SyncState;
  label?: string;
  className?: string;
}

const STATE_MAP: Record<
  SyncState,
  { Icon: typeof Wifi; tone: PulseTone; pulse: boolean; text: string }
> = {
  connected:           { Icon: Wifi,     tone: "ok",     pulse: true,  text: "Connected" },
  idle:                { Icon: Wifi,     tone: "ok",     pulse: false, text: "Connected (idle)" },
  reconnecting:        { Icon: WifiLow,  tone: "warn",   pulse: true,  text: "Reconnecting" },
  stale:               { Icon: WifiHigh, tone: "warn",   pulse: false, text: "Stale" },
  down:                { Icon: WifiOff,  tone: "danger", pulse: false, text: "Down" },
  credentials_invalid: { Icon: WifiOff,  tone: "danger", pulse: false, text: "Credentials invalid" },
  operator_paused:     { Icon: WifiOff,  tone: "muted",  pulse: false, text: "Paused" },
};

const TONE_TEXT: Record<PulseTone, string> = {
  ok: "text-ok",
  warn: "text-warn",
  danger: "text-danger",
  info: "text-info",
  ai: "text-ai",
  muted: "text-fg-subtle",
};

export function SyncSignal({ state, label, className }: SyncSignalProps): JSX.Element {
  const { Icon, tone, pulse, text } = STATE_MAP[state];
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 text-xs font-medium", TONE_TEXT[tone], className)}
      role="status"
      aria-label={label ?? text}
    >
      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
      <PulseDot tone={tone} pulse={pulse} size="sm" />
      <span className="leading-none">{label ?? text}</span>
    </span>
  );
}

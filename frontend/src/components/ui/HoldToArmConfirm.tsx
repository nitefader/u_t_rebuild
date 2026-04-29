import { useEffect, useRef, useState } from "react";
import { Button } from "./Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./Dialog";
import { cn } from "@/lib/cn";

export interface HoldToArmConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  message: React.ReactNode;
  actionLabel: string;
  onConfirm: (notes: string) => void | Promise<void>;
  busy?: boolean;
  tone?: "danger" | "ok";
  notePlaceholder?: string;
  holdMs?: number;
}

export function HoldToArmConfirm({
  open,
  onOpenChange,
  title,
  message,
  actionLabel,
  onConfirm,
  busy = false,
  tone = "danger",
  notePlaceholder = "Optional audit note",
  holdMs = 2000,
}: HoldToArmConfirmProps): JSX.Element {
  const [notes, setNotes] = useState("");
  const [holding, setHolding] = useState(false);
  const [armed, setArmed] = useState(false);
  const [holdProgress, setHoldProgress] = useState(0);
  const armTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const progressTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const elapsedRef = useRef(0);

  function clearHoldTimers(): void {
    if (armTimerRef.current != null) {
      clearTimeout(armTimerRef.current);
      armTimerRef.current = null;
    }
    if (progressTimerRef.current != null) {
      clearInterval(progressTimerRef.current);
      progressTimerRef.current = null;
    }
  }

  useEffect(() => clearHoldTimers, []);

  function reset(): void {
    clearHoldTimers();
    setNotes("");
    setHolding(false);
    setArmed(false);
    setHoldProgress(0);
    elapsedRef.current = 0;
  }

  function handleOpenChange(next: boolean): void {
    if (!next) reset();
    onOpenChange(next);
  }

  function startHold(): void {
    if (busy || armed) return;
    clearHoldTimers();
    elapsedRef.current = 0;
    setHoldProgress(0);
    setHolding(true);

    progressTimerRef.current = setInterval(() => {
      elapsedRef.current += 50;
      setHoldProgress(Math.min(99, Math.round((elapsedRef.current / holdMs) * 100)));
    }, 50);

    armTimerRef.current = setTimeout(() => {
      clearHoldTimers();
      setHolding(false);
      setHoldProgress(100);
      setArmed(true);
    }, holdMs);
  }

  function cancelHold(): void {
    if (armed) return;
    clearHoldTimers();
    setHolding(false);
    setHoldProgress(0);
    elapsedRef.current = 0;
  }

  const enabled = armed && !busy;
  const holdLabel = armed ? "Verified" : holding ? "Keep holding" : "Hold 2 seconds to verify";

  async function handleConfirm(): Promise<void> {
    if (!enabled) return;
    await onConfirm(notes.trim());
    reset();
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{message}</DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <div className="text-xs text-fg-muted">Hold to verify</div>
            <button
              type="button"
              autoFocus
              aria-pressed={armed}
              disabled={busy}
              onPointerDown={startHold}
              onPointerUp={cancelHold}
              onPointerLeave={cancelHold}
              onPointerCancel={cancelHold}
              onKeyDown={(event) => {
                if ((event.key === " " || event.key === "Enter") && !holding) {
                  event.preventDefault();
                  startHold();
                }
              }}
              onKeyUp={(event) => {
                if (event.key === " " || event.key === "Enter") {
                  event.preventDefault();
                  cancelHold();
                }
              }}
              className={cn(
                "relative flex h-10 w-full items-center justify-center overflow-hidden rounded border px-3 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-accent/60",
                armed
                  ? "border-ok bg-ok/15 text-ok shadow-[0_0_0_1px_rgb(var(--ut-ok)/0.35)]"
                  : holding
                    ? "animate-pulse border-warn bg-warn/15 text-warn"
                    : "border-border bg-bg-inset text-fg hover:border-border-strong",
                busy ? "cursor-not-allowed opacity-60" : "cursor-pointer",
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  "absolute inset-y-0 left-0 transition-[width]",
                  armed ? "bg-ok/25" : "bg-warn/20",
                )}
                style={{ width: `${holdProgress}%` }}
              />
              <span className="relative">{holdLabel}</span>
            </button>
            <div className="text-[11px] text-fg-subtle">
              Hold for the full two seconds. Release early and it resets.
            </div>
          </div>

          <label className="block text-xs">
            <span className="text-fg-muted">Notes (optional)</span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder={notePlaceholder}
              rows={2}
              className="mt-1 block w-full resize-none rounded border border-border bg-bg-inset px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
            />
          </label>
        </div>

        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant={tone}
            size="sm"
            disabled={!enabled}
            loading={busy}
            onClick={() => {
              void handleConfirm();
            }}
          >
            {actionLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

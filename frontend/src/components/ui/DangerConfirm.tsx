import { useState } from "react";
import { Button } from "./Button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./Dialog";

/**
 * DangerConfirm — type-name-to-confirm primitive.
 *
 * Pattern: any action that creates or removes broker risk requires
 * the operator to type the target's exact display name (or a
 * stronger acknowledgement string) before the action button
 * enables. The component returns the entered string via `onConfirm`
 * only when it matches `expected`.
 *
 * Required reasons (free-text) are also captured for the audit
 * trail — Operations control commands all take a `reason` field.
 */
export interface DangerConfirmProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  message: React.ReactNode;
  expected: string;
  /** Label of the destructive action button. */
  actionLabel: string;
  /** Variant tone of the action — defaults to danger. */
  tone?: "danger" | "ok";
  /** Called with the operator-supplied reason when typed name matches. */
  onConfirm: (reason: string) => void | Promise<void>;
  /** Show a busy state during async confirm. */
  busy?: boolean;
  /** Optional override for the input label. */
  typeLabel?: string;
}

export function DangerConfirm({
  open,
  onOpenChange,
  title,
  message,
  expected,
  actionLabel,
  tone = "danger",
  onConfirm,
  busy = false,
  typeLabel,
}: DangerConfirmProps): JSX.Element {
  const [typed, setTyped] = useState("");
  const [reason, setReason] = useState("");

  function reset(): void {
    setTyped("");
    setReason("");
  }

  function handleOpenChange(next: boolean): void {
    if (!next) reset();
    onOpenChange(next);
  }

  const matches = typed.trim() === expected.trim();
  const reasonOk = reason.trim().length >= 3;
  const enabled = matches && reasonOk && !busy;

  async function handleConfirm(): Promise<void> {
    if (!enabled) return;
    await onConfirm(reason.trim());
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
          <label className="block text-xs">
            <span className="text-fg-muted">{typeLabel ?? `Type "${expected}" to confirm`}</span>
            <input
              autoFocus
              type="text"
              autoComplete="off"
              spellCheck={false}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              className="mt-1 block w-full rounded border border-border bg-bg-inset px-2 py-1.5 font-mono text-sm focus:border-accent focus:outline-none"
            />
          </label>

          <label className="block text-xs">
            <span className="text-fg-muted">Reason (operator audit)</span>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="why are you doing this?"
              className="mt-1 block w-full rounded border border-border bg-bg-inset px-2 py-1.5 text-sm focus:border-accent focus:outline-none"
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

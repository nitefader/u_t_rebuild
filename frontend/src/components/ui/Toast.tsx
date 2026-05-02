import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { CheckCircle, XCircle, AlertCircle, X } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * Toast — operator-facing post-action evidence layer.
 *
 * One ToastProvider lives at the AppShell root. Any route or component can
 * call `useToast().show({ ... })` to surface a transient banner — typically
 * after a successful mutation (Pause, Resume, Flatten, Bulk-Delete, Save,
 * etc.) so the operator never has to wonder whether their click landed.
 *
 * Severity tones map to existing theme tokens (ok / warn / danger). The
 * structure mirrors the JobToaster radix usage so we have one consistent
 * notification system, not two.
 */
export type ToastSeverity = "ok" | "warn" | "danger" | "info";

export interface ToastInput {
  /** Stable id; if omitted a uuid is generated. Pass an id to dedupe. */
  id?: string;
  severity: ToastSeverity;
  title: string;
  description?: React.ReactNode;
  /** Optional internal route the toast deep-links to (e.g. "/operations"). */
  linkTo?: string;
  /** Label for `linkTo`; defaults to "View →". */
  linkLabel?: string;
  /** ms before auto-dismiss; defaults vary by severity (8000 ok/warn/info, 12000 danger). */
  durationMs?: number;
}

interface ToastEntry extends ToastInput {
  id: string;
}

interface ToastContextValue {
  show: (input: ToastInput) => string;
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [items, setItems] = useState<ToastEntry[]>([]);
  const counter = useRef(0);

  const dismiss = useCallback((id: string) => {
    setItems((prev) => prev.filter((entry) => entry.id !== id));
  }, []);

  const show = useCallback((input: ToastInput): string => {
    counter.current += 1;
    const id = input.id ?? `toast-${Date.now()}-${counter.current}`;
    setItems((prev) => {
      const filtered = prev.filter((entry) => entry.id !== id);
      return [...filtered, { ...input, id }];
    });
    return id;
  }, []);

  const value = useMemo<ToastContextValue>(() => ({ show, dismiss }), [show, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      <ToastPrimitive.Provider swipeDirection="right" duration={8_000}>
        {children}
        {items.map((entry) => {
          const duration =
            entry.durationMs ?? (entry.severity === "danger" ? 12_000 : 8_000);
          return (
            <ToastPrimitive.Root
              key={entry.id}
              duration={duration}
              onOpenChange={(open) => {
                if (!open) dismiss(entry.id);
              }}
              className={`pointer-events-auto rounded border bg-bg-elevated shadow-lg ${severityBorder(
                entry.severity,
              )} data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:slide-in-from-bottom-2`}
            >
              <div className="flex items-start gap-3 p-3">
                <span
                  className={`mt-0.5 ${severityIconClass(entry.severity)}`}
                  aria-hidden="true"
                >
                  {severityIcon(entry.severity)}
                </span>
                <div className="min-w-0 flex-1">
                  <ToastPrimitive.Title
                    className={`text-sm font-semibold ${severityTextClass(entry.severity)}`}
                  >
                    {entry.title}
                  </ToastPrimitive.Title>
                  {entry.description ? (
                    <ToastPrimitive.Description className="mt-0.5 text-xs text-fg-muted break-words">
                      {entry.description}
                    </ToastPrimitive.Description>
                  ) : null}
                  {entry.linkTo ? (
                    <ToastPrimitive.Action altText={entry.linkLabel ?? "View"} asChild>
                      <Link
                        to={entry.linkTo}
                        onClick={() => dismiss(entry.id)}
                        className="mt-2 inline-block text-xs text-accent underline hover:no-underline"
                      >
                        {entry.linkLabel ?? "View →"}
                      </Link>
                    </ToastPrimitive.Action>
                  ) : null}
                </div>
                <ToastPrimitive.Close
                  className="ml-2 text-fg-muted hover:text-fg"
                  aria-label="Close"
                >
                  <X className="h-3.5 w-3.5" />
                </ToastPrimitive.Close>
              </div>
            </ToastPrimitive.Root>
          );
        })}
        <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[60] flex w-[380px] max-w-[calc(100vw-2rem)] flex-col gap-2" />
      </ToastPrimitive.Provider>
    </ToastContext.Provider>
  );
}

/**
 * useToast — fire-and-forget toast emitter.
 *
 * Call `show({ severity, title, description?, linkTo? })` from any
 * mutation onSuccess / onError handler. The provider must be mounted
 * upstream (it is, in `AppShell.tsx`).
 *
 * In tests that render an isolated component without `AppShell`, the
 * hook returns a no-op so test setup doesn't have to wrap every mount.
 * Use `<ToastProvider>` in the test render if the test asserts on the
 * toast itself.
 */
export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (ctx) return ctx;
  return NO_OP_TOAST;
}

const NO_OP_TOAST: ToastContextValue = {
  show: () => "",
  dismiss: () => undefined,
};

function severityIcon(severity: ToastSeverity): JSX.Element {
  switch (severity) {
    case "ok":
      return <CheckCircle className="h-4 w-4" />;
    case "danger":
      return <XCircle className="h-4 w-4" />;
    case "warn":
    case "info":
    default:
      return <AlertCircle className="h-4 w-4" />;
  }
}

function severityBorder(severity: ToastSeverity): string {
  switch (severity) {
    case "ok":
      return "border-ok/40";
    case "warn":
      return "border-warn/40";
    case "danger":
      return "border-danger/40";
    case "info":
    default:
      return "border-accent/40";
  }
}

function severityTextClass(severity: ToastSeverity): string {
  switch (severity) {
    case "ok":
      return "text-ok";
    case "warn":
      return "text-warn";
    case "danger":
      return "text-danger";
    case "info":
    default:
      return "text-accent";
  }
}

function severityIconClass(severity: ToastSeverity): string {
  return severityTextClass(severity);
}

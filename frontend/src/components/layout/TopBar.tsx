import { SystemStatusBadge } from "./SystemStatusBadge";

/** Slim top bar — keeps the system status badge visible above all pages. */
export function TopBar(): JSX.Element {
  return (
    <header className="sticky top-0 z-20 flex h-12 items-center justify-between gap-4 border-b border-border bg-bg/95 px-4 backdrop-blur">
      <div className="text-xs uppercase tracking-wide text-fg-subtle">Ultimate Trader · Operator Console</div>
      <SystemStatusBadge />
    </header>
  );
}

import { cn } from "@/lib/cn";

/**
 * SectionCard — shared shell for the 14 Page-2 editor sections.
 *
 * Each section card mounts at a stable `id` so the right-rail TOC can
 * deep-link into it. The left-edge severity bar slot is a 6d concern
 * (full coherence validator surfacing) — Slice 6c renders an inert
 * neutral border. Slice 6d will swap `severity` to drive the bar.
 */
export type SectionSeverity = "ok" | "warn" | "error" | "neutral";

const SEVERITY_BAR: Record<SectionSeverity, string> = {
  ok: "before:bg-ok",
  warn: "before:bg-warn",
  error: "before:bg-danger",
  neutral: "before:bg-border",
};

export interface SectionCardProps {
  id: string;
  number: number;
  title: string;
  subtitle?: string;
  severity?: SectionSeverity;
  trailing?: React.ReactNode;
  children: React.ReactNode;
}

export function SectionCard(props: SectionCardProps): JSX.Element {
  const { id, number, title, subtitle, severity = "neutral", trailing, children } = props;
  return (
    <section
      id={id}
      data-testid={id}
      className={cn(
        "relative rounded border border-border bg-bg-raised pl-4",
        "before:absolute before:left-0 before:top-0 before:h-full before:w-1 before:rounded-l",
        SEVERITY_BAR[severity],
      )}
    >
      <header className="flex items-start justify-between gap-3 border-b border-border/60 px-3 py-2">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
              Section {number}
            </span>
            <h3 className="text-sm font-semibold tracking-tight">{title}</h3>
          </div>
          {subtitle ? <p className="mt-0.5 text-[11px] text-fg-muted">{subtitle}</p> : null}
        </div>
        {trailing ? <div className="shrink-0">{trailing}</div> : null}
      </header>
      <div className="px-3 py-3">{children}</div>
    </section>
  );
}

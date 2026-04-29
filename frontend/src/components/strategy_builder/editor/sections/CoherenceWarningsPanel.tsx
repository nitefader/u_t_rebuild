import { CircleCheck, X } from "lucide-react";
import type { StrategyDraft } from "@/api/schemas/strategyComposer";
import { Banner } from "@/components/ui/Banner";
import { cn } from "@/lib/cn";
import type { CoherenceWarning } from "../coherenceValidator";
import { SectionCard } from "./SectionCard";

/**
 * CoherenceWarningsPanel (#13) — global validation surface.
 *
 * Layout:
 *   1. Backend validation block (errors/warnings from draft.validation)
 *   2. Client-side coherence warnings grouped by severity:
 *      errors (not dismissible) → warns → infos
 *   3. Green "all clear" row only when backend is clean AND no client
 *      errors/undismissed warns remain.
 */
export interface CoherenceWarningsPanelProps {
  draft: StrategyDraft;
  warnings: CoherenceWarning[];
  onDismiss: (id: string) => void;
}

export function CoherenceWarningsPanel(props: CoherenceWarningsPanelProps): JSX.Element {
  const { draft, warnings, onDismiss } = props;
  const v = draft.validation;
  const backendErrors = v.errors ?? [];
  const backendWarnings = v.warnings ?? [];

  const clientErrors = warnings.filter((w) => w.severity === "error");
  const clientWarns = warnings.filter((w) => w.severity === "warn");
  const clientInfos = warnings.filter((w) => w.severity === "info");

  const undismissedWarns = clientWarns.filter((w) => !w.dismissed);
  const undismissedInfos = clientInfos.filter((w) => !w.dismissed);

  const panelSeverity =
    backendErrors.length > 0 || clientErrors.length > 0
      ? "error"
      : backendWarnings.length > 0 || undismissedWarns.length > 0
      ? "warn"
      : undismissedInfos.length > 0
      ? "warn"
      : "ok";

  const isAllClear =
    backendErrors.length === 0 &&
    backendWarnings.length === 0 &&
    clientErrors.length === 0 &&
    undismissedWarns.length === 0 &&
    undismissedInfos.length === 0;

  return (
    <SectionCard
      id="section-coherence"
      number={13}
      title="Validation & coherence warnings"
      subtitle="Backend pre-save checks and client-side coherence rules."
      severity={panelSeverity}
    >
      <div className="space-y-3">
        {/* ── Backend validation ── */}
        {backendErrors.length > 0 ? (
          <Banner
            severity="danger"
            title={`${backendErrors.length} backend validation error${backendErrors.length === 1 ? "" : "s"}`}
            message={
              <ul className="list-disc pl-5">
                {backendErrors.slice(0, 5).map((e, i) => (
                  <li key={i}>{e}</li>
                ))}
              </ul>
            }
          />
        ) : null}
        {backendWarnings.length > 0 ? (
          <Banner
            severity="warning"
            title={`${backendWarnings.length} backend warning${backendWarnings.length === 1 ? "" : "s"}`}
            message={
              <ul className="list-disc pl-5">
                {backendWarnings.slice(0, 5).map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            }
          />
        ) : null}

        {/* ── Client errors (no dismiss button) ── */}
        {clientErrors.length > 0 ? (
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-danger">
              {clientErrors.length} coherence error{clientErrors.length === 1 ? "" : "s"} — blocks save
            </p>
            {clientErrors.map((w) => (
              <WarningRow key={w.id} warning={w} onDismiss={onDismiss} />
            ))}
          </div>
        ) : null}

        {/* ── Client warnings ── */}
        {clientWarns.length > 0 ? (
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-warn">
              {clientWarns.length} warning{clientWarns.length === 1 ? "" : "s"}
            </p>
            {clientWarns.map((w) => (
              <WarningRow key={w.id} warning={w} onDismiss={onDismiss} />
            ))}
          </div>
        ) : null}

        {/* ── Client infos ── */}
        {clientInfos.length > 0 ? (
          <div className="space-y-1">
            <p className="text-[10px] font-semibold uppercase tracking-wide text-fg-muted">
              {clientInfos.length} advisory note{clientInfos.length === 1 ? "" : "s"}
            </p>
            {clientInfos.map((w) => (
              <WarningRow key={w.id} warning={w} onDismiss={onDismiss} />
            ))}
          </div>
        ) : null}

        {/* ── All clear ── */}
        {isAllClear ? (
          <div className="flex items-center gap-2 rounded border border-ok/30 bg-ok-subtle/30 px-2 py-1 text-[12px] text-ok">
            <CircleCheck className="h-4 w-4" aria-hidden="true" />
            Backend reports valid. Save when ready.
          </div>
        ) : null}
      </div>
    </SectionCard>
  );
}

interface WarningRowProps {
  warning: CoherenceWarning;
  onDismiss: (id: string) => void;
}

function WarningRow({ warning, onDismiss }: WarningRowProps): JSX.Element {
  const canDismiss = warning.severity !== "error";

  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded px-2 py-1 text-[11px]",
        warning.severity === "error"
          ? "bg-danger-subtle/30 text-danger"
          : warning.severity === "warn"
          ? "bg-warn-subtle/30 text-warn"
          : "bg-bg-inset text-fg-muted",
        warning.dismissed ? "opacity-50 line-through" : "",
      )}
      data-testid={`coherence-warning-${warning.id}`}
    >
      <span className="flex-1">{warning.message}</span>
      {canDismiss ? (
        <button
          type="button"
          onClick={() => onDismiss(warning.id)}
          className="shrink-0 rounded p-0.5 opacity-60 hover:opacity-100"
          aria-label={warning.dismissed ? `Restore ${warning.id}` : `Dismiss ${warning.id}`}
          title={warning.dismissed ? "Restore" : "Dismiss"}
        >
          <X className="h-3 w-3" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}

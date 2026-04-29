import { useState } from "react";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { ExplainerDrawer } from "@/components/ui/ExplainerDrawer";
import { EXPLAINERS } from "./explainerContent";

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  /** Optional override; when omitted, reads `EXPLAINERS[explainSlug]`. */
  onExplain?: () => void;
  /** Slug into `explainerContent.EXPLAINERS`. When set, the Explain button auto-opens the drawer. */
  explainSlug?: string;
}

export function PageHeader({
  title,
  subtitle,
  actions,
  onExplain,
  explainSlug,
}: PageHeaderProps): JSX.Element {
  const [explainOpen, setExplainOpen] = useState(false);
  const explainer = explainSlug ? EXPLAINERS[explainSlug] : undefined;
  const hasExplain = Boolean(onExplain) || Boolean(explainer);

  function handleExplain(): void {
    if (onExplain) {
      onExplain();
      return;
    }
    if (explainer) setExplainOpen(true);
  }

  return (
    <>
      <header className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
          {subtitle ? <p className="text-xs text-fg-muted">{subtitle}</p> : null}
        </div>
        <div className="flex items-center gap-2">
          {actions}
          {hasExplain ? (
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<Info className="h-3.5 w-3.5" aria-hidden="true" />}
              onClick={handleExplain}
            >
              Explain
            </Button>
          ) : null}
        </div>
      </header>
      {explainer ? (
        <ExplainerDrawer
          open={explainOpen}
          onOpenChange={setExplainOpen}
          pageTitle={explainer.pageTitle}
          oneLiner={explainer.oneLiner}
          sections={explainer.sections}
          pageSlug={explainer.pageSlug}
        />
      ) : null}
    </>
  );
}

/**
 * LongShortTabs — Long/Short tab switcher with a Mirror button.
 */

import { useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { mirrorExpression } from "@/api/strategiesV4";
import { Button } from "@/components/ui/Button";

export type TradeSide = "long" | "short";

export interface LongShortTabsProps {
  activeSide: TradeSide;
  longText: string;
  shortText: string;
  onChange: (side: TradeSide, text: string) => void;
  onMirror: (mirroredText: string, targetSide: TradeSide) => void;
}

export function LongShortTabs({
  activeSide,
  longText,
  shortText,
  onChange,
  onMirror,
}: LongShortTabsProps): JSX.Element {
  const [mirroring, setMirroring] = useState(false);
  const [mirrorError, setMirrorError] = useState<string | null>(null);

  const activeText = activeSide === "long" ? longText : shortText;
  const targetSide: TradeSide = activeSide === "long" ? "short" : "long";
  const mirrorDisabled = !activeText.trim() || mirroring;

  async function handleMirror(): Promise<void> {
    setMirrorError(null);
    setMirroring(true);
    try {
      const result = await mirrorExpression(activeText);
      onMirror(result.mirrored_text, targetSide);
    } catch (err) {
      setMirrorError(err instanceof Error ? err.message : "Mirror failed");
    } finally {
      setMirroring(false);
    }
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-0 border-b border-border">
        <button
          role="tab"
          aria-selected={activeSide === "long"}
          className={`px-4 py-2 text-sm font-medium transition-colors focus:outline-none ${
            activeSide === "long"
              ? "border-b-2 border-accent text-accent"
              : "text-fg-subtle hover:text-fg-muted"
          }`}
          onClick={() => onChange("long", longText)}
        >
          Long
        </button>
        <button
          role="tab"
          aria-selected={activeSide === "short"}
          className={`px-4 py-2 text-sm font-medium transition-colors focus:outline-none ${
            activeSide === "short"
              ? "border-b-2 border-accent text-accent"
              : "text-fg-subtle hover:text-fg-muted"
          }`}
          onClick={() => onChange("short", shortText)}
        >
          Short
        </button>
        <div className="ml-auto flex items-center gap-2 pr-3">
          {mirrorError ? (
            <span className="text-xs text-danger">{mirrorError}</span>
          ) : null}
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<ArrowLeftRight className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={() => void handleMirror()}
            disabled={mirrorDisabled}
            loading={mirroring}
            title={`Mirror ${activeSide} expression to ${targetSide}`}
          >
            Mirror to {targetSide}
          </Button>
        </div>
      </div>
    </div>
  );
}

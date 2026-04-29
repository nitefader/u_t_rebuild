import { useMemo, useState } from "react";
import { Copy } from "lucide-react";
import { Button } from "./Button";
import {
  Drawer,
  DrawerBody,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from "./Drawer";

/**
 * ExplainerDrawer — right-side help drawer per the operator-experience
 * doc (`docs/architecture/UI_VISUAL_DIRECTION.md`).
 *
 * Every major page passes its own content. The drawer always shows a
 * `Copy context` button that puts a markdown blob on the clipboard so
 * the operator can paste it into an LLM or notes.
 */
export interface ExplainerSection {
  heading: string;
  body: string;
}

export interface ExplainerDrawerProps {
  open: boolean;
  onOpenChange: (b: boolean) => void;
  /** Page title — shown in the drawer header. */
  pageTitle: string;
  /** One-line summary. */
  oneLiner: string;
  /** Free-form sections rendered in order. */
  sections: ExplainerSection[];
  /** Page slug used in the copyable context payload. */
  pageSlug: string;
}

export function ExplainerDrawer({
  open,
  onOpenChange,
  pageTitle,
  oneLiner,
  sections,
  pageSlug,
}: ExplainerDrawerProps): JSX.Element {
  const [copied, setCopied] = useState(false);

  const copyPayload = useMemo(() => buildCopyPayload(pageTitle, pageSlug, oneLiner, sections), [
    pageTitle,
    pageSlug,
    oneLiner,
    sections,
  ]);

  function handleCopy(): void {
    void navigator.clipboard.writeText(copyPayload).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>About · {pageTitle}</DrawerTitle>
          <DrawerDescription>{oneLiner}</DrawerDescription>
        </DrawerHeader>
        <DrawerBody className="space-y-4 text-sm leading-relaxed">
          {sections.map((section) => (
            <section key={section.heading}>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">
                {section.heading}
              </h3>
              <div className="mt-1 whitespace-pre-line text-fg/90">{section.body}</div>
            </section>
          ))}

          <div className="rounded-md border border-border bg-bg-inset px-3 py-2 text-xs leading-relaxed text-fg-muted">
            <div className="font-medium text-fg">Doctrine flow</div>
            <div className="mt-1 font-mono">
              Strategy → Deployment → SignalPlan → Account Decision → Governor → Order →
              BrokerSync → Position
            </div>
          </div>
        </DrawerBody>
        <DrawerFooter>
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Copy className="h-3.5 w-3.5" aria-hidden="true" />}
            onClick={handleCopy}
          >
            {copied ? "Copied" : "Copy context"}
          </Button>
          <Button size="sm" variant="primary" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

function buildCopyPayload(
  pageTitle: string,
  pageSlug: string,
  oneLiner: string,
  sections: ExplainerSection[],
): string {
  const lines = [`# Ultimate Trader · ${pageTitle} (${pageSlug})`, "", oneLiner, ""];
  for (const section of sections) {
    lines.push(`## ${section.heading}`);
    lines.push("");
    lines.push(section.body);
    lines.push("");
  }
  lines.push("## Doctrine flow");
  lines.push("");
  lines.push(
    "Strategy → Deployment → SignalPlan → Account Decision → Governor → Order → BrokerSync → Position",
  );
  return lines.join("\n");
}

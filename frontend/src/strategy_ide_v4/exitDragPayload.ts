/**
 * exitDragPayload — drag transport contract for exit block palette entries.
 *
 * Uses a MIME type distinct from the feature-drag MIME ("text/plain") used in FeaturePalette,
 * so the Monaco drop handler cannot accidentally consume exit drags.
 */

import type { ExitTemplateId } from "./exitTemplates";
import { EXIT_TEMPLATES } from "./exitTemplates";

/** MIME type for exit template drag events. Distinct from feature-drag ("text/plain"). */
export const EXIT_DRAG_MIME = "application/x-strategy-exit-template";

export type ExitDragPayload = {
  kind: "exit-template";
  template_id: ExitTemplateId;
};

/** Serializes an exit drag payload to a JSON string. */
export function serializeExitDrag(template_id: ExitTemplateId): string {
  const payload: ExitDragPayload = { kind: "exit-template", template_id };
  return JSON.stringify(payload);
}

const VALID_IDS: ReadonlySet<string> = new Set(EXIT_TEMPLATES.map((t) => t.id));

/**
 * Attempts to parse a raw string as an ExitDragPayload.
 * Returns null if the string is malformed JSON, has the wrong kind, or contains
 * an unknown template_id.
 */
export function tryParseExitDrag(raw: string): ExitDragPayload | null {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw) as unknown;
  } catch {
    return null;
  }

  if (
    parsed === null ||
    typeof parsed !== "object" ||
    (parsed as Record<string, unknown>)["kind"] !== "exit-template" ||
    typeof (parsed as Record<string, unknown>)["template_id"] !== "string" ||
    !VALID_IDS.has((parsed as Record<string, unknown>)["template_id"] as string)
  ) {
    return null;
  }

  return parsed as ExitDragPayload;
}

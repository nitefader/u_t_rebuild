/**
 * Tests for exitDragPayload — serialise/parse round-trip + rejection cases.
 */

import { describe, expect, it } from "vitest";
import {
  EXIT_DRAG_MIME,
  serializeExitDrag,
  tryParseExitDrag,
} from "./exitDragPayload";
import type { ExitTemplateId } from "./exitTemplates";

describe("EXIT_DRAG_MIME", () => {
  it("is distinct from the feature-drag MIME (text/plain)", () => {
    expect(EXIT_DRAG_MIME).not.toBe("text/plain");
    expect(EXIT_DRAG_MIME).toBe("application/x-strategy-exit-template");
  });
});

describe("serializeExitDrag / tryParseExitDrag round-trip", () => {
  const ids: ExitTemplateId[] = ["no_progress", "opposite_cross", "session_end", "bars_since"];

  for (const id of ids) {
    it(`round-trips template_id "${id}"`, () => {
      const serialized = serializeExitDrag(id);
      const parsed = tryParseExitDrag(serialized);
      expect(parsed).not.toBeNull();
      expect(parsed!.kind).toBe("exit-template");
      expect(parsed!.template_id).toBe(id);
    });
  }
});

describe("tryParseExitDrag rejection cases", () => {
  it("returns null for malformed JSON", () => {
    expect(tryParseExitDrag("not-json-{{{")).toBeNull();
  });

  it("returns null for empty string", () => {
    expect(tryParseExitDrag("")).toBeNull();
  });

  it("returns null when kind is wrong", () => {
    const raw = JSON.stringify({ kind: "feature", template_id: "no_progress" });
    expect(tryParseExitDrag(raw)).toBeNull();
  });

  it("returns null when template_id is unknown", () => {
    const raw = JSON.stringify({ kind: "exit-template", template_id: "evil_hack" });
    expect(tryParseExitDrag(raw)).toBeNull();
  });

  it("returns null when template_id is missing", () => {
    const raw = JSON.stringify({ kind: "exit-template" });
    expect(tryParseExitDrag(raw)).toBeNull();
  });

  it("returns null for null JSON value", () => {
    expect(tryParseExitDrag("null")).toBeNull();
  });

  it("returns null for an array", () => {
    expect(tryParseExitDrag("[]")).toBeNull();
  });
});

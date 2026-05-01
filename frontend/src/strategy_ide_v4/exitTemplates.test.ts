/**
 * Tests for exitTemplates registry.
 */

import { describe, expect, it } from "vitest";
import {
  EXIT_TEMPLATES,
  getExitTemplate,
  defaultParamsFor,
} from "./exitTemplates";
import type { ExitTemplateId } from "./exitTemplates";

const ALL_IDS: ExitTemplateId[] = ["no_progress", "opposite_cross", "session_end", "bars_since"];

describe("EXIT_TEMPLATES", () => {
  it("covers exactly the 4 required template ids", () => {
    const ids = EXIT_TEMPLATES.map((t) => t.id);
    expect(ids).toHaveLength(4);
    for (const id of ALL_IDS) {
      expect(ids).toContain(id);
    }
  });

  it("no_progress has bars and threshold_r params", () => {
    const tpl = getExitTemplate("no_progress");
    const paramNames = tpl.params.map((p) => p.name);
    expect(paramNames).toContain("bars");
    expect(paramNames).toContain("threshold_r");
  });

  it("opposite_cross has no params", () => {
    const tpl = getExitTemplate("opposite_cross");
    expect(tpl.params).toHaveLength(0);
  });

  it("session_end has minutes_before_close param", () => {
    const tpl = getExitTemplate("session_end");
    const paramNames = tpl.params.map((p) => p.name);
    expect(paramNames).toContain("minutes_before_close");
  });

  it("bars_since has event and bars params", () => {
    const tpl = getExitTemplate("bars_since");
    const paramNames = tpl.params.map((p) => p.name);
    expect(paramNames).toContain("event");
    expect(paramNames).toContain("bars");
  });

  it("each template has label, description, and id", () => {
    for (const tpl of EXIT_TEMPLATES) {
      expect(typeof tpl.label).toBe("string");
      expect(tpl.label.length).toBeGreaterThan(0);
      expect(typeof tpl.description).toBe("string");
      expect(tpl.description.length).toBeGreaterThan(0);
      expect(typeof tpl.id).toBe("string");
    }
  });
});

describe("getExitTemplate", () => {
  it("returns the correct template for each id", () => {
    for (const id of ALL_IDS) {
      const tpl = getExitTemplate(id);
      expect(tpl.id).toBe(id);
    }
  });

  it("throws on an unknown id", () => {
    expect(() => getExitTemplate("unknown_exit" as ExitTemplateId)).toThrow();
  });
});

describe("defaultParamsFor", () => {
  it("returns an object with all param defaults", () => {
    const defaults = defaultParamsFor("no_progress");
    expect(typeof defaults["bars"]).toBe("number");
    expect(typeof defaults["threshold_r"]).toBe("number");
  });

  it("returns empty object for opposite_cross (no params)", () => {
    const defaults = defaultParamsFor("opposite_cross");
    expect(Object.keys(defaults)).toHaveLength(0);
  });

  it("returns fresh objects on each call (not the same reference)", () => {
    const a = defaultParamsFor("no_progress");
    const b = defaultParamsFor("no_progress");
    expect(a).not.toBe(b);
    a["bars"] = 999;
    expect(b["bars"]).not.toBe(999);
  });

  it("session_end defaults: minutes_before_close=5", () => {
    const defaults = defaultParamsFor("session_end");
    expect(defaults["minutes_before_close"]).toBe(5);
  });

  it("bars_since defaults: event='entry', bars=20", () => {
    const defaults = defaultParamsFor("bars_since");
    expect(defaults["event"]).toBe("entry");
    expect(defaults["bars"]).toBe(20);
  });
});

import { describe, it, expect } from "vitest";
import { getProtectionDisplay } from "./protectionDisplay";

describe("getProtectionDisplay", () => {
  it("returns ok tone with leg count for protected", () => {
    const d = getProtectionDisplay("protected", 2);
    expect(d.tone).toBe("ok");
    expect(d.label).toBe("Protected (2)");
    expect(d.title).toMatch(/incremental fill/);
  });

  it("returns danger tone with NAKED label for naked", () => {
    const d = getProtectionDisplay("naked", 0);
    expect(d.tone).toBe("danger");
    expect(d.label).toBe("NAKED");
    expect(d.title).toMatch(/no active protective stop/i);
  });

  it("returns warn tone with Stop Pending label for pending_protection", () => {
    const d = getProtectionDisplay("pending_protection", 0);
    expect(d.tone).toBe("warn");
    expect(d.label).toBe("Stop Pending");
  });

  it("returns neutral tone with em-dash for unknown", () => {
    const d = getProtectionDisplay("unknown", 0);
    expect(d.tone).toBe("neutral");
    expect(d.label).toBe("—");
    expect(d.title).toMatch(/not tracked/i);
  });

  it("Critic Fix #8: unknown enum values render with warn tone, not silent neutral", () => {
    const d = getProtectionDisplay("future_status_added_backend_side", 0);
    expect(d.tone).toBe("warn");
    expect(d.label).toContain("future_status_added_backend_side");
    expect(d.title).toMatch(/Investigate/);
  });

  it("returns singular tooltip when protective_order_count is 1", () => {
    const d = getProtectionDisplay("protected", 1);
    expect(d.label).toBe("Protected (1)");
    expect(d.title).not.toMatch(/incremental fill/);
  });
});

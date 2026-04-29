import { describe, expect, it } from "vitest";
import { formatCurrency, formatPercent, formatSignedCurrency, formatQuantity } from "./format";

describe("format", () => {
  it("formats currency with two decimals", () => {
    expect(formatCurrency(1234.5)).toMatch(/\$1,234\.50/);
  });

  it("returns em-dash for null", () => {
    expect(formatCurrency(null)).toBe("—");
    expect(formatPercent(null)).toBe("—");
    expect(formatQuantity(null)).toBe("—");
  });

  it("signs currency with danger tone for negative", () => {
    const r = formatSignedCurrency(-50);
    expect(r.tone).toBe("danger");
    expect(r.text.startsWith("−")).toBe(true);
  });

  it("signs currency with ok tone for positive", () => {
    const r = formatSignedCurrency(50);
    expect(r.tone).toBe("ok");
    expect(r.text.startsWith("+")).toBe(true);
  });
});

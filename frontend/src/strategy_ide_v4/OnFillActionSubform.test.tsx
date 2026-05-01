import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@testing-library/react";
import { OnFillActionSubform } from "./OnFillActionSubform";
import type { OnFillActionV4Draft } from "@/api/schemas/strategiesV4";

function renderSubform(value: OnFillActionV4Draft, onChange = vi.fn()) {
  return render(<OnFillActionSubform value={value} onChange={onChange} />);
}

describe("<OnFillActionSubform />", () => {
  it("renders kind picker", () => {
    renderSubform({ kind: "be_exact" });
    expect(screen.getByRole("combobox", { name: /on fill action kind/i })).toBeInTheDocument();
  });

  it("does not show offset input for be_exact", () => {
    renderSubform({ kind: "be_exact" });
    expect(screen.queryByRole("spinbutton", { name: /offset/i })).not.toBeInTheDocument();
  });

  it("does not show offset input for leave", () => {
    renderSubform({ kind: "leave" });
    expect(screen.queryByRole("spinbutton", { name: /offset/i })).not.toBeInTheDocument();
  });

  it("shows offset input for be_plus", () => {
    renderSubform({ kind: "be_plus", offset_value: 0.5 });
    expect(screen.getByRole("spinbutton", { name: /offset/i })).toBeInTheDocument();
  });

  it("shows offset input for be_minus", () => {
    renderSubform({ kind: "be_minus", offset_value: 0.1 });
    expect(screen.getByRole("spinbutton", { name: /offset/i })).toBeInTheDocument();
  });

  it("shows offset input for tighten_atr", () => {
    renderSubform({ kind: "tighten_atr", offset_value: 1.0 });
    expect(screen.getByRole("spinbutton", { name: /offset/i })).toBeInTheDocument();
  });

  it("shows offset input for tighten_pct", () => {
    renderSubform({ kind: "tighten_pct", offset_value: 0.5 });
    expect(screen.getByRole("spinbutton", { name: /offset/i })).toBeInTheDocument();
  });

  it("switching from be_plus to be_exact sets offset_value=null", () => {
    const onChange = vi.fn();
    renderSubform({ kind: "be_plus", offset_value: 0.5 }, onChange);
    fireEvent.change(screen.getByRole("combobox", { name: /on fill action kind/i }), {
      target: { value: "be_exact" },
    });
    expect(onChange).toHaveBeenCalledWith({ kind: "be_exact", offset_value: null });
  });

  it("switching from be_exact to be_minus sets offset_value=0.0 (default)", () => {
    const onChange = vi.fn();
    renderSubform({ kind: "be_exact" }, onChange);
    fireEvent.change(screen.getByRole("combobox", { name: /on fill action kind/i }), {
      target: { value: "be_minus" },
    });
    const call = onChange.mock.calls[0][0] as OnFillActionV4Draft;
    expect(call.kind).toBe("be_minus");
    expect(call.offset_value).toBe(0.0);
  });

  it("switching from leave to tighten_pct preserves non-null offset if present", () => {
    const onChange = vi.fn();
    // leave has offset_value=null, so new kind should get 0.0
    renderSubform({ kind: "leave" }, onChange);
    fireEvent.change(screen.getByRole("combobox", { name: /on fill action kind/i }), {
      target: { value: "tighten_pct" },
    });
    const call = onChange.mock.calls[0][0] as OnFillActionV4Draft;
    expect(call.kind).toBe("tighten_pct");
    expect(call.offset_value).toBe(0.0);
  });

  it("offset input change fires onChange with updated offset_value", () => {
    const onChange = vi.fn();
    renderSubform({ kind: "tighten_atr", offset_value: 1.0 }, onChange);
    fireEvent.change(screen.getByRole("spinbutton", { name: /offset/i }), {
      target: { value: "2.5" },
    });
    const call = onChange.mock.calls[0][0] as OnFillActionV4Draft;
    expect(call.offset_value).toBeCloseTo(2.5, 5);
  });
});

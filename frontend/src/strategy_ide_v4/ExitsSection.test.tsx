/**
 * Tests for ExitsSection component.
 */

import { describe, expect, it, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ExitsSection } from "./ExitsSection";
import type { ExitsSectionValue } from "./ExitsSection";
import type { ExitBlockData } from "./ExitBlock";
import { defaultParamsFor } from "./exitTemplates";

function makeBlock(id: string, template_id: ExitBlockData["template_id"] = "no_progress"): ExitBlockData {
  return { id, template_id, params: defaultParamsFor(template_id) };
}

const EMPTY_VALUE: ExitsSectionValue = { long: [], short: [] };

describe("<ExitsSection />", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders Long exits and Short exits column headers", () => {
    render(<ExitsSection value={EMPTY_VALUE} onChange={vi.fn()} />);
    expect(screen.getByText(/Long exits/i)).toBeInTheDocument();
    expect(screen.getByText(/Short exits/i)).toBeInTheDocument();
  });

  it("renders the section header 'Logical exits'", () => {
    render(<ExitsSection value={EMPTY_VALUE} onChange={vi.fn()} />);
    expect(screen.getByText(/Logical exits/i)).toBeInTheDocument();
  });

  it("both columns work independently — long change does not affect short", () => {
    const onChange = vi.fn();
    const value: ExitsSectionValue = {
      long: [makeBlock("l1")],
      short: [makeBlock("s1")],
    };
    render(<ExitsSection value={value} onChange={onChange} />);

    // Remove the long block
    const removeButtons = screen.getAllByRole("button", { name: /Remove No-progress timeout/i });
    fireEvent.click(removeButtons[0]);

    expect(onChange).toHaveBeenCalledOnce();
    const updated = onChange.mock.calls[0][0] as ExitsSectionValue;
    expect(updated.long).toHaveLength(0);
    expect(updated.short).toHaveLength(1);
  });

  it("copy long to short clones blocks with fresh UUIDs", () => {
    const onChange = vi.fn();
    const value: ExitsSectionValue = {
      long: [makeBlock("original-id-1"), makeBlock("original-id-2")],
      short: [],
    };
    render(<ExitsSection value={value} onChange={onChange} />);

    // Click "Copy to short" on the long column
    fireEvent.click(screen.getByRole("button", { name: /copy long exits to short/i }));

    expect(onChange).toHaveBeenCalledOnce();
    const updated = onChange.mock.calls[0][0] as ExitsSectionValue;
    expect(updated.short).toHaveLength(2);
    for (const block of updated.short) {
      expect(block.id).not.toBe("original-id-1");
      expect(block.id).not.toBe("original-id-2");
    }
    // Long side should be unchanged
    expect(updated.long).toHaveLength(2);
    expect(updated.long[0].id).toBe("original-id-1");
  });

  it("copy short to long clones blocks with fresh UUIDs", () => {
    const onChange = vi.fn();
    const value: ExitsSectionValue = {
      long: [],
      short: [makeBlock("s-original")],
    };
    render(<ExitsSection value={value} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /copy short exits to long/i }));

    expect(onChange).toHaveBeenCalledOnce();
    const updated = onChange.mock.calls[0][0] as ExitsSectionValue;
    expect(updated.long).toHaveLength(1);
    expect(updated.long[0].id).not.toBe("s-original");
  });

  it("confirm dialog fires when destination is non-empty on copy", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const onChange = vi.fn();
    const value: ExitsSectionValue = {
      long: [makeBlock("l1")],
      short: [makeBlock("s1")],
    };
    render(<ExitsSection value={value} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /copy long exits to short/i }));

    expect(confirmSpy).toHaveBeenCalledOnce();
    // User cancelled — onChange must not have been called
    expect(onChange).not.toHaveBeenCalled();
  });

  it("no confirm dialog when destination is empty", () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    const onChange = vi.fn();
    const value: ExitsSectionValue = {
      long: [makeBlock("l1")],
      short: [],
    };
    render(<ExitsSection value={value} onChange={onChange} />);

    fireEvent.click(screen.getByRole("button", { name: /copy long exits to short/i }));

    expect(confirmSpy).not.toHaveBeenCalled();
    expect(onChange).toHaveBeenCalledOnce();
  });
});

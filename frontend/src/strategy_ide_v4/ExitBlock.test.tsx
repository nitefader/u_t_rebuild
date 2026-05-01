/**
 * Tests for ExitBlock component.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ExitBlock } from "./ExitBlock";
import type { ExitBlockData } from "./ExitBlock";
import { defaultParamsFor } from "./exitTemplates";

function makeBlock(template_id: ExitBlockData["template_id"]): ExitBlockData {
  return {
    id: "test-id-1",
    template_id,
    params: defaultParamsFor(template_id),
  };
}

describe("<ExitBlock />", () => {
  it("renders the template label in the header", () => {
    render(
      <ExitBlock
        block={makeBlock("no_progress")}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByText(/No-progress timeout/i)).toBeInTheDocument();
  });

  it("renders the remove button", () => {
    render(
      <ExitBlock
        block={makeBlock("session_end")}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Remove Force flat at close/i }),
    ).toBeInTheDocument();
  });

  it("fires onRemove when remove button is clicked", () => {
    const onRemove = vi.fn();
    render(
      <ExitBlock block={makeBlock("opposite_cross")} onChange={vi.fn()} onRemove={onRemove} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Remove Opposite EMA cross/i }));
    expect(onRemove).toHaveBeenCalledOnce();
  });

  it("renders param inputs for no_progress", () => {
    render(
      <ExitBlock block={makeBlock("no_progress")} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.getByRole("spinbutton", { name: /Bars window/i })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: /Progress threshold/i })).toBeInTheDocument();
  });

  it("fires onChange with updated param on number input change", () => {
    const onChange = vi.fn();
    const block = makeBlock("no_progress");
    render(<ExitBlock block={block} onChange={onChange} onRemove={vi.fn()} />);

    const barsInput = screen.getByRole("spinbutton", { name: /Bars window/i });
    fireEvent.change(barsInput, { target: { value: "25" } });

    expect(onChange).toHaveBeenCalledOnce();
    const updated = onChange.mock.calls[0][0] as ExitBlockData;
    expect(updated.params["bars"]).toBe(25);
    expect(updated.id).toBe(block.id);
    expect(updated.template_id).toBe("no_progress");
  });

  it("renders event select for bars_since", () => {
    render(
      <ExitBlock block={makeBlock("bars_since")} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.getByRole("combobox", { name: /Since event/i })).toBeInTheDocument();
  });

  it("fires onChange with updated event param on select change", () => {
    const onChange = vi.fn();
    render(
      <ExitBlock block={makeBlock("bars_since")} onChange={onChange} onRemove={vi.fn()} />,
    );
    const select = screen.getByRole("combobox", { name: /Since event/i });
    fireEvent.change(select, { target: { value: "last_target" } });

    expect(onChange).toHaveBeenCalledOnce();
    const updated = onChange.mock.calls[0][0] as ExitBlockData;
    expect(updated.params["event"]).toBe("last_target");
  });

  it("renders no param inputs for opposite_cross", () => {
    render(
      <ExitBlock block={makeBlock("opposite_cross")} onChange={vi.fn()} onRemove={vi.fn()} />,
    );
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(screen.queryByRole("combobox")).toBeNull();
  });
});

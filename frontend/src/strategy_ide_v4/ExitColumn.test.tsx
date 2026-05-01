/**
 * Tests for ExitColumn component.
 */

import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ExitColumn } from "./ExitColumn";
import type { ExitBlockData } from "./ExitBlock";
import { EXIT_DRAG_MIME, serializeExitDrag } from "./exitDragPayload";
import { defaultParamsFor } from "./exitTemplates";

function makeBlock(id: string): ExitBlockData {
  return { id, template_id: "no_progress", params: defaultParamsFor("no_progress") };
}

describe("<ExitColumn />", () => {
  it("renders empty state placeholder when no blocks", () => {
    render(
      <ExitColumn side="long" blocks={[]} onChange={vi.fn()} onCopyToOther={vi.fn()} />,
    );
    expect(screen.getByText(/Drop exit blocks from the palette/i)).toBeInTheDocument();
  });

  it("renders existing blocks", () => {
    render(
      <ExitColumn
        side="long"
        blocks={[makeBlock("b1"), makeBlock("b2")]}
        onChange={vi.fn()}
        onCopyToOther={vi.fn()}
      />,
    );
    expect(screen.getAllByTestId("exit-block")).toHaveLength(2);
  });

  it("copy button is disabled when blocks is empty", () => {
    render(
      <ExitColumn side="long" blocks={[]} onChange={vi.fn()} onCopyToOther={vi.fn()} />,
    );
    const btn = screen.getByRole("button", { name: /copy long exits to short/i });
    expect(btn).toBeDisabled();
  });

  it("copy button is enabled when blocks are present and fires onCopyToOther", () => {
    const onCopyToOther = vi.fn();
    render(
      <ExitColumn
        side="long"
        blocks={[makeBlock("b1")]}
        onChange={vi.fn()}
        onCopyToOther={onCopyToOther}
      />,
    );
    const btn = screen.getByRole("button", { name: /copy long exits to short/i });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    expect(onCopyToOther).toHaveBeenCalledOnce();
  });

  it("drop event with valid EXIT_DRAG_MIME appends a new block with fresh UUID and defaults", () => {
    const onChange = vi.fn();
    render(
      <ExitColumn side="long" blocks={[]} onChange={onChange} onCopyToOther={vi.fn()} />,
    );
    const dropZone = screen.getByRole("list", { name: /Long exits drop zone/i });

    const dataTransferMap: Record<string, string> = {
      [EXIT_DRAG_MIME]: serializeExitDrag("session_end"),
    };

    fireEvent.drop(dropZone, {
      dataTransfer: {
        types: [EXIT_DRAG_MIME],
        getData: (mime: string) => dataTransferMap[mime] ?? "",
      },
    });

    expect(onChange).toHaveBeenCalledOnce();
    const newBlocks = onChange.mock.calls[0][0] as ExitBlockData[];
    expect(newBlocks).toHaveLength(1);
    expect(newBlocks[0].template_id).toBe("session_end");
    expect(typeof newBlocks[0].id).toBe("string");
    expect(newBlocks[0].id.length).toBeGreaterThan(0);
    expect(newBlocks[0].params["minutes_before_close"]).toBe(5);
  });

  it("drop event with wrong MIME type is ignored", () => {
    const onChange = vi.fn();
    render(
      <ExitColumn side="long" blocks={[]} onChange={onChange} onCopyToOther={vi.fn()} />,
    );
    const dropZone = screen.getByRole("list", { name: /Long exits drop zone/i });

    fireEvent.dragOver(dropZone, {
      dataTransfer: { types: ["text/plain"] },
    });
    fireEvent.drop(dropZone, {
      dataTransfer: {
        types: ["text/plain"],
        getData: () => "5m.ema(9)",
      },
    });

    expect(onChange).not.toHaveBeenCalled();
  });

  it("dragOver with correct MIME sets dropEffect=copy and does not call onChange", () => {
    const onChange = vi.fn();
    render(
      <ExitColumn side="short" blocks={[]} onChange={onChange} onCopyToOther={vi.fn()} />,
    );
    const dropZone = screen.getByRole("list", { name: /Short exits drop zone/i });

    fireEvent.dragOver(dropZone, {
      dataTransfer: { types: [EXIT_DRAG_MIME], dropEffect: "" },
    });

    expect(onChange).not.toHaveBeenCalled();
  });
});

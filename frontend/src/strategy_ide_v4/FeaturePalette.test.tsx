/**
 * Tests for FeaturePalette — renders categories; search filters; drag emits payload;
 * Exit blocks tab renders all 4 templates with EXIT_DRAG_MIME payloads.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { installFetchMock, renderRoute } from "@/test/renderRoute";
import { FeaturePalette } from "./FeaturePalette";
import { EXIT_DRAG_MIME } from "./exitDragPayload";
import { EXIT_TEMPLATES } from "./exitTemplates";

const SAMPLE_FEATURES = {
  features: [
    {
      key: "ema",
      name: "ema",
      namespace: "ta",
      timeframe_bound: true,
      arity: 1,
      arg_names: ["period"],
      arg_defaults: [9],
      return_type: "float",
      description: "Exponential moving average",
      category: "trend",
    },
    {
      key: "rsi",
      name: "rsi",
      namespace: "ta",
      timeframe_bound: true,
      arity: 1,
      arg_names: ["period"],
      arg_defaults: [14],
      return_type: "float",
      description: "Relative strength index",
      category: "momentum",
    },
    {
      key: "volume",
      name: "volume",
      namespace: "bar",
      timeframe_bound: false,
      arity: 0,
      arg_names: [],
      arg_defaults: [],
      return_type: "float",
      description: "Current bar volume",
      category: "volume",
    },
  ],
};

describe("<FeaturePalette />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders category headers after features load", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    renderRoute(<FeaturePalette />);
    await waitFor(() => {
      // Match the category header span specifically (uppercase text in a button)
      expect(screen.getAllByText(/Trend/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Momentum/i).length).toBeGreaterThan(0);
      // "Volume" appears in both the category label and the feature name; check both
      expect(screen.getAllByText(/Volume/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("renders feature entries", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    renderRoute(<FeaturePalette />);
    await waitFor(() => {
      expect(screen.getByText("ema")).toBeInTheDocument();
      expect(screen.getByText("rsi")).toBeInTheDocument();
    });
  });

  it("filters features by search query", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    renderRoute(<FeaturePalette />);
    await waitFor(() => expect(screen.getByText("ema")).toBeInTheDocument());

    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "rsi" } });

    await waitFor(() => {
      expect(screen.queryByText("ema")).not.toBeInTheDocument();
      expect(screen.getByText("rsi")).toBeInTheDocument();
    });
  });

  it("calls onInsert with correct text when entry is clicked", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    const onInsert = vi.fn();
    renderRoute(<FeaturePalette onInsert={onInsert} />);
    await waitFor(() => expect(screen.getByText("ema")).toBeInTheDocument());

    fireEvent.click(screen.getByText("ema"));

    expect(onInsert).toHaveBeenCalledWith(expect.stringContaining("ema"));
  });

  it("sets dataTransfer on drag start", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    const onDragStart = vi.fn();
    renderRoute(<FeaturePalette onDragStart={onDragStart} />);
    await waitFor(() => expect(screen.getByText("ema")).toBeInTheDocument());

    const emaEntry = screen.getByText("ema").closest("[draggable]");
    expect(emaEntry).not.toBeNull();

    // Simulate dragstart
    const mockSetData = vi.fn();
    fireEvent.dragStart(emaEntry!, {
      dataTransfer: { setData: mockSetData, effectAllowed: "" },
    });

    expect(onDragStart).toHaveBeenCalledWith(expect.stringContaining("ema"));
  });

  it("renders Exit blocks tab button", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    renderRoute(<FeaturePalette />);
    await waitFor(() => expect(screen.getByText("ema")).toBeInTheDocument());

    expect(screen.getByTestId("exit-blocks-tab")).toBeInTheDocument();
    expect(screen.getByText(/Exit blocks/i)).toBeInTheDocument();
  });

  it("clicking Exit blocks tab shows all 4 exit templates as draggable items", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    renderRoute(<FeaturePalette />);
    await waitFor(() => expect(screen.getByText("ema")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("exit-blocks-tab"));

    for (const tpl of EXIT_TEMPLATES) {
      expect(screen.getByTestId(`exit-palette-item-${tpl.id}`)).toBeInTheDocument();
    }
    expect(EXIT_TEMPLATES).toHaveLength(4);
  });

  it("exit template items set EXIT_DRAG_MIME payload on dragstart", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    renderRoute(<FeaturePalette />);
    await waitFor(() => expect(screen.getByText("ema")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("exit-blocks-tab"));

    const item = screen.getByTestId("exit-palette-item-no_progress");
    const mockSetData = vi.fn();
    fireEvent.dragStart(item, {
      dataTransfer: { setData: mockSetData, effectAllowed: "" },
    });

    // Must use EXIT_DRAG_MIME, not text/plain
    expect(mockSetData).toHaveBeenCalledWith(EXIT_DRAG_MIME, expect.any(String));
    const callArgs = mockSetData.mock.calls.find((call) => call[0] === EXIT_DRAG_MIME);
    expect(callArgs).toBeDefined();
    const parsed = JSON.parse(callArgs![1] as string) as { kind: string; template_id: string };
    expect(parsed.kind).toBe("exit-template");
    expect(parsed.template_id).toBe("no_progress");
  });

  it("exit template drag does NOT use text/plain MIME", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/expression/features", body: SAMPLE_FEATURES },
    ]);
    renderRoute(<FeaturePalette />);
    await waitFor(() => expect(screen.getByText("ema")).toBeInTheDocument());

    fireEvent.click(screen.getByTestId("exit-blocks-tab"));

    const item = screen.getByTestId("exit-palette-item-session_end");
    const mockSetData = vi.fn();
    fireEvent.dragStart(item, {
      dataTransfer: { setData: mockSetData, effectAllowed: "" },
    });

    const textPlainCall = mockSetData.mock.calls.find((call) => call[0] === "text/plain");
    expect(textPlainCall).toBeUndefined();
  });
});

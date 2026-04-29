import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ExecutionPreviewRail, computeLevels } from "./ExecutionPreviewRail";
import type { ExecutionStylePresetValue } from "../ExecutionStylePresetRow";

describe("ExecutionPreviewRail / computeLevels", () => {
  it("returns null and renders nothing for market_entry_market_exit", () => {
    const preset: ExecutionStylePresetValue = {
      kind: "market_entry_market_exit",
      overrides: {},
    };
    expect(computeLevels(preset)).toBeNull();
    const { container } = render(<ExecutionPreviewRail preset={preset} />);
    expect(container.firstChild).toBeNull();
  });

  it("returns null and renders nothing for stop_entry_market_exit", () => {
    const preset: ExecutionStylePresetValue = {
      kind: "stop_entry_market_exit",
      overrides: { entry_stop_offset_bps: 10 },
    };
    expect(computeLevels(preset)).toBeNull();
    const { container } = render(<ExecutionPreviewRail preset={preset} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders entry, stop and target levels for bracket_stop_target", () => {
    const preset: ExecutionStylePresetValue = {
      kind: "bracket_stop_target",
      overrides: { stop_pct: 1.5, target_pct: 3.0 },
    };
    render(<ExecutionPreviewRail preset={preset} />);
    expect(screen.getByTestId("execution-preview-rail")).toBeInTheDocument();
    expect(screen.getByTestId("exec-preview-level-entry")).toHaveAttribute("data-pct", "0.00");
    expect(screen.getByTestId("exec-preview-level-stop")).toHaveAttribute("data-pct", "-1.50");
    expect(screen.getByTestId("exec-preview-level-target")).toHaveAttribute("data-pct", "3.00");
    // Runner is not part of this preset.
    expect(screen.queryByTestId("exec-preview-level-runner")).toBeNull();
  });

  it("renders runner + first target + trailing stop for bracket_runner", () => {
    const preset: ExecutionStylePresetValue = {
      kind: "bracket_runner",
      overrides: { first_target_pct: 1.0, first_slice_pct: 0.5, trail_pct: 0.75 },
    };
    render(<ExecutionPreviewRail preset={preset} />);
    expect(screen.getByTestId("exec-preview-level-runner")).toHaveAttribute("data-pct", "1.75");
    expect(screen.getByTestId("exec-preview-level-target-1")).toHaveAttribute("data-pct", "1.00");
    expect(screen.getByTestId("exec-preview-level-stop")).toHaveAttribute("data-pct", "-0.75");
  });

  it("renders one line per tier for multi_target_scale_out and omits stop when null", () => {
    const preset: ExecutionStylePresetValue = {
      kind: "multi_target_scale_out",
      overrides: {
        targets: [
          { target_pct: 1.0, slice_pct: 0.25 },
          { target_pct: 2.0, slice_pct: 0.25 },
          { target_pct: 3.0, slice_pct: 0.5 },
        ],
        stop_pct: null,
      },
    };
    render(<ExecutionPreviewRail preset={preset} />);
    expect(screen.getByTestId("exec-preview-level-target-1")).toHaveAttribute("data-pct", "1.00");
    expect(screen.getByTestId("exec-preview-level-target-2")).toHaveAttribute("data-pct", "2.00");
    expect(screen.getByTestId("exec-preview-level-target-3")).toHaveAttribute("data-pct", "3.00");
    expect(screen.queryByTestId("exec-preview-level-stop")).toBeNull();
  });

  it("renders the optional stop for multi_target_scale_out when present", () => {
    const preset: ExecutionStylePresetValue = {
      kind: "multi_target_scale_out",
      overrides: {
        targets: [
          { target_pct: 1.0, slice_pct: 0.5 },
          { target_pct: 2.0, slice_pct: 0.5 },
        ],
        stop_pct: 1.0,
      },
    };
    render(<ExecutionPreviewRail preset={preset} />);
    expect(screen.getByTestId("exec-preview-level-stop")).toHaveAttribute("data-pct", "-1.00");
  });
});

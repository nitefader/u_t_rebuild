/**
 * Tests for ExecutionPreview.
 */

import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderRoute } from "@/test/renderRoute";
import { ExecutionPreview } from "./ExecutionPreview";
import type { StrategyLegV4Draft, StrategyStopV4Draft } from "@/api/schemas/strategiesV4";

function makeStop(overrides?: Partial<StrategyStopV4Draft>): StrategyStopV4Draft {
  return {
    id: "stop-1",
    mode: "simple",
    scope: "all",
    simple_type: "%",
    simple_value: 2.0,
    ...overrides,
  };
}

function makeLeg(
  position: number,
  kind: "target" | "runner",
  targetType: string,
  targetValue: number,
  sizePct: number,
): StrategyLegV4Draft {
  return {
    id: `leg-${position}`,
    position,
    kind,
    size_pct: sizePct,
    target_type: targetType as StrategyLegV4Draft["target_type"],
    target_value: targetValue,
    on_fill_action: { kind: "be_exact" },
  };
}

describe("<ExecutionPreview />", () => {
  it("renders the section heading", () => {
    renderRoute(
      <ExecutionPreview
        legs={[makeLeg(1, "target", "%", 4.0, 1.0)]}
        stops={[makeStop()]}
      />,
    );
    expect(screen.getByRole("region", { name: /execution preview/i })).toBeInTheDocument();
  });

  it("renders Entry, stop, and target rail items for a simple setup", () => {
    renderRoute(
      <ExecutionPreview
        legs={[makeLeg(1, "target", "%", 4.0, 1.0)]}
        stops={[makeStop({ simple_value: 2.0 })]}
      />,
    );
    expect(screen.getByText("Entry 0.00%")).toBeInTheDocument();
    expect(screen.getAllByText(/-2\.00%/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/\+4\.00%/).length).toBeGreaterThanOrEqual(1);
  });

  it("renders 'expression stop' placeholder for expression-mode stop", () => {
    renderRoute(
      <ExecutionPreview
        legs={[makeLeg(1, "target", "%", 4.0, 1.0)]}
        stops={[makeStop({ mode: "expression", simple_type: null, simple_value: null })]}
      />,
    );
    expect(screen.getAllByText(/expression stop/i).length).toBeGreaterThanOrEqual(1);
  });

  it("renders 'feature target' placeholder for feature-type leg", () => {
    renderRoute(
      <ExecutionPreview
        legs={[makeLeg(1, "target", "feature", 0, 1.0)]}
        stops={[makeStop()]}
      />,
    );
    expect(screen.getAllByText(/feature target/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows runner caption for runner leg", () => {
    renderRoute(
      <ExecutionPreview
        legs={[makeLeg(1, "runner", "%", 3.0, 1.0)]}
        stops={[makeStop()]}
      />,
    );
    expect(screen.getByText(/runner/i)).toBeInTheDocument();
  });

  it("shows correct target caption with slice % for target leg", () => {
    renderRoute(
      <ExecutionPreview
        legs={[makeLeg(1, "target", "%", 5.0, 0.5)]}
        stops={[makeStop()]}
      />,
    );
    // Caption should mention 50% slice
    expect(screen.getByText(/50% slice/)).toBeInTheDocument();
  });

  it("renders multiple legs correctly", () => {
    renderRoute(
      <ExecutionPreview
        legs={[
          makeLeg(1, "target", "%", 4.0, 0.6),
          makeLeg(2, "runner", "%", 8.0, 0.4),
        ]}
        stops={[makeStop({ simple_value: 2.0 })]}
      />,
    );
    // Entry + stop + 2 legs = 4 rail items
    expect(screen.getByText("Entry 0.00%")).toBeInTheDocument();
    expect(screen.getAllByText(/-2\.00%/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/\+4\.00%/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/\+8\.00%/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows ATR stop placeholder when stop is ATR-based", () => {
    renderRoute(
      <ExecutionPreview
        legs={[makeLeg(1, "target", "%", 4.0, 1.0)]}
        stops={[makeStop({ simple_type: "ATR", simple_value: 1.5 })]}
      />,
    );
    expect(screen.getByText(/ATR stop/i)).toBeInTheDocument();
  });
});

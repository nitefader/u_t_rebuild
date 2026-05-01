import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@testing-library/react";
import { LegsSection } from "./LegsSection";
import type { StrategyLegV4Draft } from "@/api/schemas/strategiesV4";

const SUM_TOLERANCE = 1e-6;

function makeLeg(overrides: Partial<StrategyLegV4Draft> = {}): StrategyLegV4Draft {
  return {
    id: `leg-${Math.random()}`,
    position: 1,
    kind: "target",
    size_pct: 1.0,
    target_type: "%",
    target_value: 2.0,
    on_fill_action: { kind: "be_exact" },
    ...overrides,
  };
}

function sumSizePct(legs: StrategyLegV4Draft[]): number {
  return legs.reduce((acc, l) => acc + l.size_pct, 0);
}

describe("<LegsSection />", () => {
  it("renders existing legs", () => {
    render(
      <LegsSection
        legs={[makeLeg({ id: "a", position: 1 }), makeLeg({ id: "b", position: 2, size_pct: 0.0 })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getAllByTestId("leg-row")).toHaveLength(2);
  });

  it("Add target button adds a new leg and rebalances", () => {
    const onChange = vi.fn();
    render(
      <LegsSection legs={[makeLeg({ id: "a", position: 1, size_pct: 1.0 })]} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /\+ add target/i }));
    const updated = onChange.mock.calls[0][0] as StrategyLegV4Draft[];
    expect(updated).toHaveLength(2);
    expect(updated[updated.length - 1].kind).toBe("target");
    expect(Math.abs(sumSizePct(updated) - 1.0)).toBeLessThanOrEqual(SUM_TOLERANCE);
  });

  it("Add runner button adds a runner leg and rebalances", () => {
    const onChange = vi.fn();
    render(
      <LegsSection legs={[makeLeg({ id: "a", position: 1, size_pct: 1.0 })]} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /\+ add runner/i }));
    const updated = onChange.mock.calls[0][0] as StrategyLegV4Draft[];
    expect(updated.some((l) => l.kind === "runner")).toBe(true);
    expect(Math.abs(sumSizePct(updated) - 1.0)).toBeLessThanOrEqual(SUM_TOLERANCE);
  });

  it("Add runner button is disabled when a runner already exists", () => {
    render(
      <LegsSection
        legs={[
          makeLeg({ id: "a", position: 1, kind: "target", size_pct: 0.5 }),
          makeLeg({ id: "b", position: 2, kind: "runner", size_pct: 0.5 }),
        ]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /\+ add runner/i })).toBeDisabled();
  });

  it("removing a leg redistributes sizes and sum stays 1.0", () => {
    const onChange = vi.fn();
    render(
      <LegsSection
        legs={[
          makeLeg({ id: "a", position: 1, size_pct: 0.5 }),
          makeLeg({ id: "b", position: 2, size_pct: 0.3 }),
          makeLeg({ id: "c", position: 3, size_pct: 0.2 }),
        ]}
        onChange={onChange}
      />,
    );
    // Click first Remove button (leg 1)
    const removeBtns = screen.getAllByRole("button", { name: /remove leg/i });
    fireEvent.click(removeBtns[0]);
    const updated = onChange.mock.calls[0][0] as StrategyLegV4Draft[];
    expect(updated).toHaveLength(2);
    expect(Math.abs(sumSizePct(updated) - 1.0)).toBeLessThanOrEqual(SUM_TOLERANCE);
  });

  it("Auto-balance button evenly distributes sizes", () => {
    const onChange = vi.fn();
    render(
      <LegsSection
        legs={[
          makeLeg({ id: "a", position: 1, size_pct: 0.9 }),
          makeLeg({ id: "b", position: 2, size_pct: 0.1 }),
        ]}
        onChange={onChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /auto-balance/i }));
    const updated = onChange.mock.calls[0][0] as StrategyLegV4Draft[];
    expect(updated[0].size_pct).toBeCloseTo(0.5, 4);
    expect(updated[1].size_pct).toBeCloseTo(0.5, 4);
  });

  it("shows inline error when sum != 1.0", () => {
    render(
      <LegsSection
        legs={[
          makeLeg({ id: "a", position: 1, size_pct: 0.4 }),
          makeLeg({ id: "b", position: 2, size_pct: 0.3 }),
        ]}
        onChange={vi.fn()}
      />,
    );
    // The error text appears in both the error list and the bar summary.
    expect(screen.getAllByText(/total/i).length).toBeGreaterThanOrEqual(1);
  });

  it("shows error when no target leg", () => {
    render(
      <LegsSection
        legs={[makeLeg({ id: "a", position: 1, kind: "runner", size_pct: 1.0 })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/target leg/i)).toBeInTheDocument();
  });

  it("renders size summary bar", () => {
    render(
      <LegsSection
        legs={[makeLeg({ id: "a", position: 1, size_pct: 1.0 })]}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/size summary bar/i)).toBeInTheDocument();
  });
});

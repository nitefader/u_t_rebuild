import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { render } from "@testing-library/react";
import { StopsSection } from "./StopsSection";
import type { StrategyStopV4Draft } from "@/api/schemas/strategiesV4";

vi.mock("@monaco-editor/react", () => ({
  default: vi.fn(({ value, onChange }: { value: string; onChange?: (v: string) => void }) => (
    <textarea
      data-testid="monaco-stub"
      value={value}
      aria-label="Expression editor"
      onChange={(e) => onChange?.(e.target.value)}
    />
  )),
}));

vi.mock("@/api/strategiesV4", () => ({
  validateExpressionAbortable: vi.fn(() =>
    Promise.resolve({ valid: true, errors: [], warnings: [], feature_requirements: [], variables_used: [] }),
  ),
  listExpressionFeatures: vi.fn(() => Promise.resolve({ features: [] })),
}));

const defaultStop: StrategyStopV4Draft = {
  id: "stop-1",
  mode: "simple",
  scope: "all",
  simple_type: "%",
  simple_value: 1.0,
};

describe("<StopsSection />", () => {
  it("renders existing stops", () => {
    render(
      <StopsSection stops={[defaultStop]} legCount={1} onChange={vi.fn()} />,
    );
    expect(screen.getAllByTestId("stop-row")).toHaveLength(1);
  });

  it("clicking Add stop calls onChange with new stop appended", () => {
    const onChange = vi.fn();
    render(
      <StopsSection stops={[defaultStop]} legCount={1} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /\+ add stop/i }));
    expect(onChange).toHaveBeenCalledOnce();
    const updated = onChange.mock.calls[0][0] as StrategyStopV4Draft[];
    expect(updated).toHaveLength(2);
    expect(updated[1].mode).toBe("simple");
    expect(updated[1].simple_type).toBe("%");
  });

  it("removing a stop calls onChange with that stop removed", () => {
    const stop2: StrategyStopV4Draft = { id: "stop-2", mode: "simple", scope: "all", simple_type: "ATR", simple_value: 2.0 };
    const onChange = vi.fn();
    render(
      <StopsSection stops={[defaultStop, stop2]} legCount={1} onChange={onChange} />,
    );
    const removeButtons = screen.getAllByRole("button", { name: /remove stop/i });
    fireEvent.click(removeButtons[0]); // remove first
    const updated = onChange.mock.calls[0][0] as StrategyStopV4Draft[];
    expect(updated).toHaveLength(1);
    expect(updated[0].id).toBe("stop-2");
  });

  it("shows inline error when stops array is empty", () => {
    render(
      <StopsSection stops={[]} legCount={1} onChange={vi.fn()} />,
    );
    expect(screen.getByText(/at least one stop/i)).toBeInTheDocument();
  });

  it("does not show error for a valid stop", () => {
    render(
      <StopsSection stops={[defaultStop]} legCount={1} onChange={vi.fn()} />,
    );
    expect(screen.queryByText(/at least one stop/i)).not.toBeInTheDocument();
  });
});

import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { render } from "@testing-library/react";
import { StopRow } from "./StopRow";
import type { StrategyStopV4Draft } from "@/api/schemas/strategiesV4";

// Monaco stub
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

// Validation endpoint stub
vi.mock("@/api/strategiesV4", () => ({
  validateExpressionAbortable: vi.fn(() =>
    Promise.resolve({
      valid: true,
      errors: [],
      warnings: [],
      feature_requirements: [],
      variables_used: [],
    }),
  ),
  listExpressionFeatures: vi.fn(() => Promise.resolve({ features: [] })),
}));

function makeSimpleStop(overrides: Partial<StrategyStopV4Draft> = {}): StrategyStopV4Draft {
  return {
    id: "stop-1",
    mode: "simple",
    scope: "all",
    simple_type: "%",
    simple_value: 1.0,
    ...overrides,
  };
}

describe("<StopRow />", () => {
  it("renders simple mode fields", () => {
    render(
      <StopRow
        stop={makeSimpleStop()}
        legCount={2}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.getByRole("combobox", { name: /stop type/i })).toBeInTheDocument();
    expect(screen.getByRole("spinbutton", { name: /stop value/i })).toBeInTheDocument();
  });

  it("does not render Monaco editor in simple mode", () => {
    render(
      <StopRow
        stop={makeSimpleStop()}
        legCount={1}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    expect(screen.queryByTestId("monaco-stub")).not.toBeInTheDocument();
  });

  it("renders Monaco editor in expression mode", async () => {
    render(
      <StopRow
        stop={makeSimpleStop({ mode: "expression", expression_text: "5m.atr(14)", simple_type: null, simple_value: null })}
        legCount={1}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("monaco-stub")).toBeInTheDocument();
    });
  });

  it("switching simple -> expression calls onChange with cleared simple fields", () => {
    const onChange = vi.fn();
    render(
      <StopRow
        stop={makeSimpleStop()}
        legCount={1}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    // Press the Expression toggle button
    fireEvent.click(screen.getByRole("button", { name: /expression/i }));
    expect(onChange).toHaveBeenCalled();
    const updated = onChange.mock.calls[0][0] as StrategyStopV4Draft;
    expect(updated.mode).toBe("expression");
    expect(updated.simple_type).toBeNull();
    expect(updated.simple_value).toBeNull();
  });

  it("switching expression -> simple calls onChange with cleared expression fields", () => {
    const onChange = vi.fn();
    render(
      <StopRow
        stop={makeSimpleStop({ mode: "expression", expression_text: "5m.atr(14)", simple_type: null, simple_value: null })}
        legCount={1}
        onChange={onChange}
        onRemove={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /simple/i }));
    const updated = onChange.mock.calls[0][0] as StrategyStopV4Draft;
    expect(updated.mode).toBe("simple");
    expect(updated.expression_text).toBeNull();
  });

  it("scope picker reflects legCount", () => {
    render(
      <StopRow
        stop={makeSimpleStop()}
        legCount={3}
        onChange={vi.fn()}
        onRemove={vi.fn()}
      />,
    );
    const scopePicker = screen.getByRole("combobox", { name: /stop scope/i });
    const options = Array.from((scopePicker as HTMLSelectElement).options).map((o) => o.value);
    expect(options).toContain("all");
    expect(options).toContain("leg-1");
    expect(options).toContain("leg-2");
    expect(options).toContain("leg-3");
    expect(options).not.toContain("leg-4");
  });

  it("calls onRemove when Remove button clicked", () => {
    const onRemove = vi.fn();
    render(
      <StopRow
        stop={makeSimpleStop()}
        legCount={1}
        onChange={vi.fn()}
        onRemove={onRemove}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /remove stop/i }));
    expect(onRemove).toHaveBeenCalledOnce();
  });
});

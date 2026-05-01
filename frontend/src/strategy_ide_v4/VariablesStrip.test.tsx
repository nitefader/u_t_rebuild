/**
 * Tests for VariablesStrip — add / edit / remove flows.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { installFetchMock, renderRoute } from "@/test/renderRoute";
import { VariablesStrip } from "./VariablesStrip";
import type { StrategyVariableV4Draft } from "@/api/schemas/strategiesV4";

// Mock Monaco editor to avoid loading heavy deps in unit tests
vi.mock("@monaco-editor/react", () => ({
  default: vi.fn(
    ({
      value,
      onChange,
    }: {
      value: string;
      onChange?: (val: string) => void;
    }) => (
      <textarea
        data-testid="monaco-stub"
        value={value}
        aria-label="Expression editor"
        onChange={(e) => onChange?.(e.target.value)}
      />
    ),
  ),
}));

const VALIDATE_OK = {
  valid: true,
  errors: [],
  warnings: [],
  feature_requirements: [],
  variables_used: [],
};

const SAMPLE_VARS: StrategyVariableV4Draft[] = [
  { name: "fast_ema", expression_text: "5m.ema(9)", kind: "expression" },
  { name: "slow_ema", expression_text: "5m.ema(21)", kind: "expression" },
];

describe("<VariablesStrip />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
    vi.clearAllMocks();
  });

  it("renders variable chips", () => {
    renderRoute(
      <VariablesStrip variables={SAMPLE_VARS} onChange={vi.fn()} />,
    );
    expect(screen.getByText("fast_ema")).toBeInTheDocument();
    expect(screen.getByText("slow_ema")).toBeInTheDocument();
  });

  it("renders Add variable button", () => {
    renderRoute(
      <VariablesStrip variables={[]} onChange={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: /add variable/i })).toBeInTheDocument();
  });

  it("opens popover when Add variable is clicked", async () => {
    renderRoute(
      <VariablesStrip variables={[]} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
    await waitFor(() => {
      expect(screen.getByLabelText(/variable name/i)).toBeInTheDocument();
    });
  });

  it("calls onChange with new variable on Save", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/strategies/expression/validate",
        method: "POST",
        body: VALIDATE_OK,
      },
    ]);
    const onChange = vi.fn();
    renderRoute(
      <VariablesStrip variables={[]} onChange={onChange} />,
    );

    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/variable name/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/variable name/i), {
      target: { value: "my_var" },
    });

    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[editors.length - 1], {
      target: { value: "5m.ema(9)" },
    });

    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    await waitFor(() => {
      expect(onChange).toHaveBeenCalledWith(
        expect.arrayContaining([
          expect.objectContaining({ name: "my_var", expression_text: "5m.ema(9)" }),
        ]),
      );
    });
  });

  it("removes a variable when trash icon is clicked", () => {
    const onChange = vi.fn();
    renderRoute(
      <VariablesStrip variables={SAMPLE_VARS} onChange={onChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /delete variable fast_ema/i }));
    expect(onChange).toHaveBeenCalledWith(
      expect.not.arrayContaining([
        expect.objectContaining({ name: "fast_ema" }),
      ]),
    );
  });

  it("popover form root has fixed w-[480px] class", async () => {
    renderRoute(
      <VariablesStrip variables={[]} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
    await waitFor(() => {
      expect(screen.getByLabelText(/variable name/i)).toBeInTheDocument();
    });
    const nameInput = screen.getByLabelText(/variable name/i);
    const formRoot = nameInput.closest(".w-\\[480px\\]");
    expect(formRoot).not.toBeNull();
  });

  it("popover editor wrapper has rounded border class", async () => {
    renderRoute(
      <VariablesStrip variables={[]} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
    await waitFor(() => {
      expect(screen.getByLabelText(/variable name/i)).toBeInTheDocument();
    });
    const monacoStub = screen.getAllByTestId("monaco-stub");
    const lastStub = monacoStub[monacoStub.length - 1];
    const borderWrapper = lastStub.closest(".rounded.border");
    expect(borderWrapper).not.toBeNull();
  });

  it("popover content has bg-bg-raised background class", async () => {
    renderRoute(
      <VariablesStrip variables={[]} onChange={vi.fn()} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /add variable/i }));
    await waitFor(() => {
      expect(screen.getByLabelText(/variable name/i)).toBeInTheDocument();
    });
    const nameInput = screen.getByLabelText(/variable name/i);
    // Walk up the DOM tree to find the Popover.Content container
    let el: HTMLElement | null = nameInput;
    let found = false;
    while (el) {
      if (el.className && el.className.includes("bg-bg-raised")) {
        found = true;
        break;
      }
      el = el.parentElement;
    }
    expect(found).toBe(true);
  });
});

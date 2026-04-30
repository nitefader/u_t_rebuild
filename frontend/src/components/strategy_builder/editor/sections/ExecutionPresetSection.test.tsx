import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExecutionPresetSection } from "./ExecutionPresetSection";
import type { ExecutionStylePresetValue } from "../../ExecutionStylePresetRow";

/**
 * Bracket Program T-2 — Execution Mode selector lives on the Stop · Target ·
 * Execution tab's ExecutionPresetSection card. Default is post_fill_bracket;
 * operator can opt into native_alpaca_bracket. Both options show their hint
 * copy so the operator understands the Alpaca constraint trade-off.
 */
describe("<ExecutionPresetSection /> — execution_mode selector", () => {
  function defaultPreset(): ExecutionStylePresetValue {
    return {
      kind: "bracket_stop_target",
      overrides: { stop_pct: 5.0, target_pct: 10.0 },
    };
  }

  it("renders post_fill_bracket as the default selected option", () => {
    render(
      <ExecutionPresetSection
        preset={defaultPreset()}
        onChange={vi.fn()}
        executionMode="post_fill_bracket"
        onExecutionModeChange={vi.fn()}
      />,
    );

    const select = screen.getByLabelText(/execution mode/i) as HTMLSelectElement;
    expect(select.value).toBe("post_fill_bracket");
    expect(screen.getByText(/Post-fill bracket \(default\)/)).toBeInTheDocument();
    expect(
      screen.getByText(/wait for BrokerSync-confirmed fill/),
    ).toBeInTheDocument();
  });

  it("renders native_alpaca_bracket option with the operator-facing constraint hint", () => {
    render(
      <ExecutionPresetSection
        preset={defaultPreset()}
        onChange={vi.fn()}
        executionMode="native_alpaca_bracket"
        onExecutionModeChange={vi.fn()}
      />,
    );

    const select = screen.getByLabelText(/execution mode/i) as HTMLSelectElement;
    expect(select.value).toBe("native_alpaca_bracket");
    expect(
      screen.getByText(/Whole-share, day\/gtc, regular hours, ETB-if-short/),
    ).toBeInTheDocument();
  });

  it("invokes onExecutionModeChange when the operator picks a different mode", async () => {
    const onChange = vi.fn();
    render(
      <ExecutionPresetSection
        preset={defaultPreset()}
        onChange={vi.fn()}
        executionMode="post_fill_bracket"
        onExecutionModeChange={onChange}
      />,
    );

    const user = userEvent.setup();
    const select = screen.getByLabelText(/execution mode/i);
    await user.selectOptions(select, "native_alpaca_bracket");

    expect(onChange).toHaveBeenCalledWith("native_alpaca_bracket");
  });
});

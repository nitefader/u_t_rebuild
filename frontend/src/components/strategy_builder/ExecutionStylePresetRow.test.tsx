import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  ExecutionStylePresetRow,
  defaultPresetValue,
  validatePreset,
  type ExecutionStylePresetValue,
} from "./ExecutionStylePresetRow";

describe("<ExecutionStylePresetRow />", () => {
  it("renders all 5 locked presets in order with the default selected", () => {
    render(
      <ExecutionStylePresetRow
        value={defaultPresetValue("market_entry_market_exit")}
        onChange={() => {}}
      />,
    );
    expect(screen.getByRole("radio", { name: /Market Entry \/ Market Exit/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    for (const label of [
      "Market Entry / Market Exit",
      "Stop Entry / Market Exit",
      "Bracket: Stop + Target",
      "Bracket + Runner",
      "Multi-Target Scale-Out",
    ]) {
      expect(screen.getByRole("radio", { name: label })).toBeInTheDocument();
    }
  });

  it("selecting a different preset emits the default knobs for that preset", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(
      <ExecutionStylePresetRow
        value={defaultPresetValue("market_entry_market_exit")}
        onChange={onChange}
      />,
    );
    await user.click(screen.getByRole("radio", { name: /Bracket: Stop \+ Target/i }));
    expect(onChange).toHaveBeenCalledWith({
      kind: "bracket_stop_target",
      overrides: { stop_pct: 1, target_pct: 2 },
    });
  });

  it("Customize disclosure renders the preset-specific knob set", async () => {
    const user = userEvent.setup();
    const value: ExecutionStylePresetValue = {
      kind: "bracket_runner",
      overrides: { first_target_pct: 1, first_slice_pct: 0.5, trail_pct: 1 },
    };
    render(<ExecutionStylePresetRow value={value} onChange={() => {}} />);
    await user.click(screen.getByRole("button", { name: /Customize/i }));
    expect(screen.getByLabelText(/First target %/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/First slice/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Trail %/i)).toBeInTheDocument();
  });

  it("market preset hides the Customize disclosure (no knobs)", () => {
    render(
      <ExecutionStylePresetRow
        value={defaultPresetValue("market_entry_market_exit")}
        onChange={() => {}}
      />,
    );
    expect(screen.queryByRole("button", { name: /Customize/i })).not.toBeInTheDocument();
  });

  it("Tier-1 local validation flags negative knobs", () => {
    expect(
      validatePreset({
        kind: "bracket_stop_target",
        overrides: { stop_pct: -1, target_pct: 2 },
      }).valid,
    ).toBe(false);
  });

  it("Tier-1 local validation rejects multi-target slice sums above 1", () => {
    expect(
      validatePreset({
        kind: "multi_target_scale_out",
        overrides: {
          targets: [
            { target_pct: 1, slice_pct: 0.6 },
            { target_pct: 2, slice_pct: 0.6 },
          ],
          stop_pct: null,
        },
      }).valid,
    ).toBe(false);
  });
});

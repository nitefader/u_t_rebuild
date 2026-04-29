import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LogicalExitRulePicker } from "./LogicalExitRulePicker";
import { emptyLogicalExitRule } from "./conditionUtils";
import type { LogicalExitRule } from "@/api/schemas/strategyComposer";

describe("<LogicalExitRulePicker />", () => {
  it("offers a button for every one of the seven LogicalExitRule kinds", () => {
    const onChange = vi.fn();
    render(
      <LogicalExitRulePicker
        value={emptyLogicalExitRule("bars_since_entry")}
        onChange={onChange}
        catalog={[]}
      />,
    );
    // Short labels rendered as the kind buttons (mirrors LOGICAL_EXIT_KIND_SHORT).
    expect(screen.getByRole("button", { name: "Bars" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Seconds" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Time of day" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Before close" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Session" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Feature" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hybrid" })).toBeInTheDocument();
  });

  it("emits a re-defaulted rule when the operator picks a different kind", async () => {
    const user = userEvent.setup();
    let value: LogicalExitRule | null = emptyLogicalExitRule("bars_since_entry");
    const onChange = vi.fn((next) => {
      value = next;
    });
    render(
      <LogicalExitRulePicker value={value} onChange={onChange} catalog={[]} />,
    );
    await user.click(screen.getByRole("button", { name: "Time of day" }));
    expect(onChange).toHaveBeenCalled();
    expect(value).toMatchObject({ kind: "time_of_day_et" });
    expect((value as LogicalExitRule).hour).toBeTypeOf("number");
    expect((value as LogicalExitRule).minute).toBeTypeOf("number");
  });

  it("hybrid kind exposes child pickers that recurse to the same picker", () => {
    const onChange = vi.fn();
    render(
      <LogicalExitRulePicker
        value={emptyLogicalExitRule("hybrid")}
        onChange={onChange}
        catalog={[]}
      />,
    );
    // The outer picker AND the recursed child picker each render the seven
    // kind buttons. Two "Bars" buttons proves the recursion mounted.
    const barsButtons = screen.getAllByRole("button", { name: "Bars" });
    expect(barsButtons.length).toBeGreaterThanOrEqual(2);
    expect(screen.getByRole("button", { name: /Add child rule/i })).toBeInTheDocument();
  });
});

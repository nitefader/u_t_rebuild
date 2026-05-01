/**
 * Tests for DirectionToggle.
 */

import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderRoute } from "@/test/renderRoute";
import { DirectionToggle } from "./DirectionToggle";

describe("<DirectionToggle />", () => {
  it("renders three option buttons", () => {
    renderRoute(<DirectionToggle value="both" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /long only/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /short only/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /both/i })).toBeInTheDocument();
  });

  it("marks the current value as pressed", () => {
    renderRoute(<DirectionToggle value="long" onChange={vi.fn()} />);
    expect(screen.getByRole("button", { name: /long only/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /short only/i })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /both/i })).toHaveAttribute("aria-pressed", "false");
  });

  it("calls onChange with correct value when a button is clicked", () => {
    const onChange = vi.fn();
    renderRoute(<DirectionToggle value="both" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /long only/i }));
    expect(onChange).toHaveBeenCalledWith("long");
  });

  it("calls onChange with 'short' when Short only is clicked", () => {
    const onChange = vi.fn();
    renderRoute(<DirectionToggle value="long" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /short only/i }));
    expect(onChange).toHaveBeenCalledWith("short");
  });

  it("selected button uses accent styling class", () => {
    renderRoute(<DirectionToggle value="both" onChange={vi.fn()} />);
    const bothBtn = screen.getByRole("button", { name: /both/i });
    expect(bothBtn.className).toContain("bg-accent");
  });

  it("unselected buttons use raised background class", () => {
    renderRoute(<DirectionToggle value="both" onChange={vi.fn()} />);
    const longBtn = screen.getByRole("button", { name: /long only/i });
    expect(longBtn.className).toContain("bg-bg-raised");
  });
});

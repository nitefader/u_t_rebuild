/**
 * Tests for HorizonPicker.
 */

import { describe, expect, it, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderRoute } from "@/test/renderRoute";
import { HorizonPicker } from "./HorizonPicker";

describe("<HorizonPicker />", () => {
  it("renders four horizon buttons", () => {
    renderRoute(
      <HorizonPicker
        horizon={null}
        onHorizonChange={vi.fn()}
        timeframe="5m"
        onTimeframeChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /scalping/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /intraday/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /swing/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /position/i })).toBeInTheDocument();
  });

  it("renders timeframe select with the current value", () => {
    renderRoute(
      <HorizonPicker
        horizon={null}
        onHorizonChange={vi.fn()}
        timeframe="1h"
        onTimeframeChange={vi.fn()}
      />,
    );
    const select = screen.getByRole("combobox", { name: /base timeframe/i });
    expect((select as HTMLSelectElement).value).toBe("1h");
  });

  it("marks the selected horizon as pressed", () => {
    renderRoute(
      <HorizonPicker
        horizon="swing"
        onHorizonChange={vi.fn()}
        timeframe="1d"
        onTimeframeChange={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: /swing/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /intraday/i })).toHaveAttribute("aria-pressed", "false");
  });

  it("calls onHorizonChange when a horizon button is clicked", () => {
    const onHorizonChange = vi.fn();
    renderRoute(
      <HorizonPicker
        horizon={null}
        onHorizonChange={onHorizonChange}
        timeframe="5m"
        onTimeframeChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /intraday/i }));
    expect(onHorizonChange).toHaveBeenCalledWith("intraday");
  });

  it("deselects horizon when same button is clicked again", () => {
    const onHorizonChange = vi.fn();
    renderRoute(
      <HorizonPicker
        horizon="swing"
        onHorizonChange={onHorizonChange}
        timeframe="1d"
        onTimeframeChange={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /swing/i }));
    expect(onHorizonChange).toHaveBeenCalledWith(null);
  });

  it("calls onTimeframeChange when timeframe select changes", () => {
    const onTimeframeChange = vi.fn();
    renderRoute(
      <HorizonPicker
        horizon={null}
        onHorizonChange={vi.fn()}
        timeframe="5m"
        onTimeframeChange={onTimeframeChange}
      />,
    );
    const select = screen.getByRole("combobox", { name: /base timeframe/i });
    fireEvent.change(select, { target: { value: "15m" } });
    expect(onTimeframeChange).toHaveBeenCalledWith("15m");
  });
});

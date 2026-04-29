import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Sparkline } from "./Sparkline";

describe("<Sparkline />", () => {
  it("renders a fallback dash when fewer than 2 points are supplied", () => {
    render(<Sparkline values={[]} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("renders an SVG polyline with one point per value when given data", () => {
    const values = [10, 11, 12, 13, 14, 15];
    const { container } = render(<Sparkline values={values} />);
    const polyline = container.querySelector("polyline");
    expect(polyline).not.toBeNull();
    const points = polyline?.getAttribute("points") ?? "";
    expect(points.split(" ").length).toBe(values.length);
  });

  it("uses the ok tone when the last value is higher than the first", () => {
    const { container } = render(<Sparkline values={[10, 12, 15]} />);
    const polyline = container.querySelector("polyline");
    expect(polyline?.classList.contains("stroke-ok")).toBe(true);
  });

  it("uses the danger tone when the last value is lower than the first", () => {
    const { container } = render(<Sparkline values={[15, 12, 10]} />);
    const polyline = container.querySelector("polyline");
    expect(polyline?.classList.contains("stroke-danger")).toBe(true);
  });
});

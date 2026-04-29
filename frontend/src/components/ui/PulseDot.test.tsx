import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { PulseDot } from "./PulseDot";

describe("PulseDot", () => {
  it("renders with the requested tone label for accessibility", () => {
    render(<PulseDot tone="ok" pulse label="Live data running" />);
    expect(screen.getByLabelText("Live data running")).toBeInTheDocument();
  });

  it("does not pulse when pulse is false", () => {
    const { container } = render(<PulseDot tone="danger" pulse={false} label="Down" />);
    // The pulse animation class only applies when pulse is true.
    expect(container.querySelector(".animate-ut-pulse")).toBeNull();
  });

  it("applies the pulse animation class when pulse is true", () => {
    const { container } = render(<PulseDot tone="ok" pulse label="Streaming" />);
    expect(container.querySelector(".animate-ut-pulse")).not.toBeNull();
  });
});

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { SyncSignal } from "./SyncSignal";

describe("SyncSignal", () => {
  it("shows green pulsing connected when state is connected", () => {
    const { container } = render(<SyncSignal state="connected" />);
    expect(screen.getByRole("status", { name: /connected$/i })).toBeInTheDocument();
    expect(container.querySelector(".animate-ut-pulse")).not.toBeNull();
  });

  it("does not pulse when stale", () => {
    const { container } = render(<SyncSignal state="stale" />);
    expect(screen.getByRole("status", { name: /stale/i })).toBeInTheDocument();
    expect(container.querySelector(".animate-ut-pulse")).toBeNull();
  });

  it("renders down without pulse and with danger tone", () => {
    render(<SyncSignal state="down" />);
    expect(screen.getByRole("status", { name: /down/i })).toBeInTheDocument();
  });
});

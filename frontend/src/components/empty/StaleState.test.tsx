import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StaleState } from "./StaleState";

describe("StaleState", () => {
  it("renders the default operator copy when no props supplied", () => {
    render(<StaleState />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.getByText("Live data is stale")).toBeInTheDocument();
  });

  it("surfaces a detail line and a Reconnect button when handler is provided", async () => {
    const onReconnect = vi.fn();
    render(
      <StaleState
        title="Stream disconnected"
        message="Showing the last bars received."
        detail="last bar 3m ago"
        onReconnect={onReconnect}
      />,
    );
    expect(screen.getByText("Stream disconnected")).toBeInTheDocument();
    expect(screen.getByText("Showing the last bars received.")).toBeInTheDocument();
    expect(screen.getByText(/last bar 3m ago/)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Reconnect" }));
    expect(onReconnect).toHaveBeenCalledTimes(1);
  });
});

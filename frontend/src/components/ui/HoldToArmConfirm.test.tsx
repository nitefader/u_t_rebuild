import { afterEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HoldToArmConfirm } from "./HoldToArmConfirm";

describe("HoldToArmConfirm", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("arms only after a full hold and passes optional notes", async () => {
    const onConfirm = vi.fn();
    render(
      <HoldToArmConfirm
        open
        onOpenChange={() => {}}
        title="Delete selected?"
        message="Hold before deleting."
        actionLabel="Delete Selected"
        onConfirm={onConfirm}
      />,
    );

    const deleteButton = screen.getByRole("button", { name: "Delete Selected" });
    const verifier = screen.getByRole("button", { name: /Hold 2 seconds to verify/i });
    expect(deleteButton).toBeDisabled();

    vi.useFakeTimers();
    fireEvent.pointerDown(verifier);
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    fireEvent.pointerUp(verifier);
    expect(deleteButton).toBeDisabled();

    fireEvent.pointerDown(verifier);
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    vi.useRealTimers();

    expect(screen.getByRole("button", { name: "Verified" })).toHaveAttribute("aria-pressed", "true");
    expect(deleteButton).toBeEnabled();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Notes/i), "cleanup after review");
    await user.click(deleteButton);

    expect(onConfirm).toHaveBeenCalledWith("cleanup after review");
  });
});

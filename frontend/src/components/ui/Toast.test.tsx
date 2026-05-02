import { describe, expect, it } from "vitest";
import { act, render, renderHook, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ToastProvider, useToast } from "./Toast";

function withProviders(children: React.ReactNode): JSX.Element {
  return (
    <MemoryRouter>
      <ToastProvider>{children}</ToastProvider>
    </MemoryRouter>
  );
}

describe("ToastProvider + useToast", () => {
  it("returns a no-op when no provider is mounted (test-friendly)", () => {
    const { result } = renderHook(() => useToast());
    // Should not throw and should return a stable shape.
    expect(typeof result.current.show).toBe("function");
    expect(typeof result.current.dismiss).toBe("function");
    // Calling show without a provider is a no-op and returns the empty id.
    expect(result.current.show({ severity: "ok", title: "ignored" })).toBe("");
  });

  it("shows a toast with title + description and dismisses it", () => {
    function Probe(): JSX.Element {
      const toast = useToast();
      return (
        <button
          type="button"
          onClick={() =>
            toast.show({
              severity: "ok",
              title: "Account deleted",
              description: "Paper Account 1 removed.",
            })
          }
        >
          fire
        </button>
      );
    }

    render(withProviders(<Probe />));
    act(() => {
      screen.getByRole("button", { name: "fire" }).click();
    });
    expect(screen.getByText("Account deleted")).toBeInTheDocument();
    expect(screen.getByText("Paper Account 1 removed.")).toBeInTheDocument();

    // The Close button uses aria-label="Close" per the component.
    act(() => {
      screen.getByRole("button", { name: "Close" }).click();
    });
    expect(screen.queryByText("Account deleted")).not.toBeInTheDocument();
  });

  it("dedupes toasts when the same id is reused", () => {
    function Probe(): JSX.Element {
      const toast = useToast();
      return (
        <button
          type="button"
          onClick={() =>
            toast.show({
              id: "fixed",
              severity: "warn",
              title: "Stream disconnected",
            })
          }
        >
          fire
        </button>
      );
    }

    render(withProviders(<Probe />));
    act(() => {
      screen.getByRole("button", { name: "fire" }).click();
      screen.getByRole("button", { name: "fire" }).click();
      screen.getByRole("button", { name: "fire" }).click();
    });
    // Only one toast should be visible because the id is shared.
    const titles = screen.getAllByText("Stream disconnected");
    expect(titles).toHaveLength(1);
  });
});

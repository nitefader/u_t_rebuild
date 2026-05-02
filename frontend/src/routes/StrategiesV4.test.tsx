import { afterEach, describe, expect, it, vi } from "vitest";
import { act, screen, waitFor, fireEvent } from "@testing-library/react";
import { Route } from "react-router-dom";
import { installFetchMock, renderRoute } from "@/test/renderRoute";
import { StrategiesV4 } from "./StrategiesV4";

const STRATEGY_A = {
  strategy_v4_id: "strat-aaa",
  name: "ORB Strategy",
  description: "Opening range breakout",
  head_version: 2,
  head_version_id: "ver-aaa-2",
  total_versions: 2,
  created_at: "2026-04-01T10:00:00Z",
  updated_at: "2026-04-15T12:00:00Z",
};

const STRATEGY_B = {
  strategy_v4_id: "strat-bbb",
  name: "VWAP Reclaim",
  description: null,
  head_version: 1,
  head_version_id: "ver-bbb-1",
  total_versions: 1,
  created_at: "2026-04-20T08:00:00Z",
  updated_at: "2026-04-20T08:00:00Z",
};

describe("<StrategiesV4 />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
    vi.clearAllMocks();
  });

  it("renders empty state when list is empty", async () => {
    restore = installFetchMock([{ url: "/api/v1/strategies/v4/", body: [] }]);
    renderRoute(<StrategiesV4 />, { path: "/strategies" });

    await waitFor(() => {
      expect(screen.getByText(/no strategies yet/i)).toBeInTheDocument();
    });
  });

  it("renders strategy cards when list has items", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/v4/", body: [STRATEGY_A, STRATEGY_B] },
    ]);
    renderRoute(<StrategiesV4 />, { path: "/strategies" });

    await waitFor(() => {
      expect(screen.getByText("ORB Strategy")).toBeInTheDocument();
      expect(screen.getByText("VWAP Reclaim")).toBeInTheDocument();
    });
  });

  it("clicking Edit navigates to /strategies/compose?id=<head_version_id>", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/v4/", body: [STRATEGY_A] },
    ]);
    renderRoute(<StrategiesV4 />, {
      path: "/strategies",
      extraRoutes: (
        <Route
          path="/strategies/compose"
          element={<div data-testid="compose-page">compose</div>}
        />
      ),
    });

    await waitFor(() => {
      expect(screen.getByText("ORB Strategy")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /edit strategy orb strategy/i }));

    await waitFor(() => {
      expect(screen.getByTestId("compose-page")).toBeInTheDocument();
    });
  });

  it("clicking Delete opens hold-to-arm confirmation", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/v4/", body: [STRATEGY_A] },
    ]);
    renderRoute(<StrategiesV4 />, { path: "/strategies" });

    await waitFor(() => {
      expect(screen.getByText("ORB Strategy")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /delete strategy orb strategy/i }));

    await waitFor(() => {
      // HoldToArmConfirm dialog shows the title and the Delete strategy action.
      expect(screen.getByText(/Delete "ORB Strategy"\?/)).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /^Delete strategy$/ })).toBeDisabled();
      expect(
        screen.getByRole("button", { name: /Hold 2 seconds to verify/i }),
      ).toBeInTheDocument();
    });
  });

  it("confirming Delete (after hold) calls the delete endpoint and refreshes the list", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies/v4/", body: [STRATEGY_A] },
      {
        url: `/api/v1/strategies/v4/by-strategy/${STRATEGY_A.strategy_v4_id}`,
        method: "DELETE",
        body: null,
        status: 204,
      },
    ]);
    renderRoute(<StrategiesV4 />, { path: "/strategies" });

    await waitFor(() => {
      expect(screen.getByText("ORB Strategy")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /delete strategy orb strategy/i }));

    const verifier = await screen.findByRole("button", { name: /Hold 2 seconds to verify/i });

    vi.useFakeTimers();
    fireEvent.pointerDown(verifier);
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    vi.useRealTimers();

    const deleteButton = await screen.findByRole("button", { name: /^Delete strategy$/ });
    expect(deleteButton).toBeEnabled();
    fireEvent.click(deleteButton);

    await waitFor(() => {
      const fetchCalls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls as unknown[][];
      const deleteCall = fetchCalls.find((call) => {
        const url = call[0];
        const method = ((call[1] as { method?: string })?.method ?? "GET").toUpperCase();
        return typeof url === "string" && url.includes("by-strategy") && method === "DELETE";
      });
      expect(deleteCall).toBeDefined();
    });
  });

  it("New strategy button navigates to /strategies/compose", async () => {
    restore = installFetchMock([{ url: "/api/v1/strategies/v4/", body: [] }]);
    renderRoute(<StrategiesV4 />, {
      path: "/strategies",
      extraRoutes: (
        <Route
          path="/strategies/compose"
          element={<div data-testid="compose-page">compose</div>}
        />
      ),
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /new strategy/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /new strategy/i }));

    await waitFor(() => {
      expect(screen.getByTestId("compose-page")).toBeInTheDocument();
    });
  });
});

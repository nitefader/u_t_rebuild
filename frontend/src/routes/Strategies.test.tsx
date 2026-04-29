import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { Strategies } from "./Strategies";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const STATUS_OK = {
  alpaca_endpoint: "https://paper-api.alpaca.markets",
  alpaca_data_feed: "sip",
  alpaca_credentials_present: true,
  alpaca_test_stream: false,
  operator_environment: "paper",
  operator_environment_source: "explicit",
  operator_environment_conflict: null,
};

describe("<Strategies />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state with no strategies", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Strategies />);
    await waitFor(() => {
      expect(screen.getByText(/No strategies yet/i)).toBeInTheDocument();
    });
  });

  it("renders a strategy card on the happy path", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/strategies",
        body: {
          strategies: [
            {
              strategy_id: "11111111-1111-1111-1111-111111111111",
              name: "Mean Reversion",
              description: "tests",
              tags: [],
              status: "draft",
              created_at: new Date().toISOString(),
              latest_version_id: null,
              frozen_version_ids: [],
              version_count: 0,
            },
          ],
        },
      },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Strategies />);
    await waitFor(() => {
      expect(screen.getByText("Mean Reversion")).toBeInTheDocument();
    });
  });

  it("primary header CTA opens the focused-mode composer", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Strategies />);
    const composeBtn = await screen.findByRole("button", { name: /Compose new strategy/i });
    // Primary CTA must be the elevated entry point — it's wrapped in a Link to
    // the focused-mode composer route mounted outside AppShell (router.tsx).
    const link = composeBtn.closest("a");
    expect(link).not.toBeNull();
    expect(link?.getAttribute("href")).toBe("/strategies/compose");
    // Blank flow stays available but is demoted to secondary.
    expect(screen.getByRole("button", { name: /New blank strategy/i })).toBeInTheDocument();
  });

  it("empty-state mirrors the dual-CTA hierarchy", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies", body: { strategies: [] } },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Strategies />);
    await screen.findByText(/No strategies yet/i);
    // Two header buttons + two empty-state buttons → two of each label total.
    expect(screen.getAllByRole("button", { name: /Compose new strategy/i })).toHaveLength(2);
    expect(screen.getAllByRole("button", { name: /New blank strategy/i })).toHaveLength(2);
  });

  it("surfaces a degraded read state when strategies list fails", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategies", body: { detail: "kaboom" }, status: 500 },
      { url: "/api/v1/system/status", body: STATUS_OK },
    ]);
    renderRoute(<Strategies />);
    await waitFor(() => {
      expect(screen.getByText(/Could not load strategies/i)).toBeInTheDocument();
    });
  });
});

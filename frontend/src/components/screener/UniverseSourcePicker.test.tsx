import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { UniverseSourcePicker } from "./UniverseSourcePicker";
import type { ScreenerUniverseSource } from "@/api/schemas/screener";
import { installFetchMock } from "@/test/renderRoute";

function mount(value: ScreenerUniverseSource, onChange = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return {
    onChange,
    ...render(
      <QueryClientProvider client={queryClient}>
        <UniverseSourcePicker value={value} onChange={onChange} />
      </QueryClientProvider>,
    ),
  };
}

function mountControlled(initialValue: ScreenerUniverseSource) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  function Harness(): JSX.Element {
    const [value, setValue] = useState<ScreenerUniverseSource>(initialValue);
    return <UniverseSourcePicker value={value} onChange={setValue} />;
  }
  return render(
    <QueryClientProvider client={queryClient}>
      <Harness />
    </QueryClientProvider>,
  );
}

describe("<UniverseSourcePicker />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("syncs explicit symbol text from the controlled value", async () => {
    restore = installFetchMock([
      { url: "/api/v1/screeners/presets", body: { presets: [] } },
      { url: "/api/v1/watchlists", body: { watchlists: [] } },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
    ]);
    const { rerender } = mount({ kind: "explicit", symbols: ["AAPL", "MSFT"] });
    expect(screen.getByLabelText(/Symbols/i)).toHaveValue("AAPL, MSFT");

    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
        mutations: { retry: false },
      },
    });
    rerender(
      <QueryClientProvider client={queryClient}>
        <UniverseSourcePicker value={{ kind: "explicit", symbols: ["NVDA"] }} onChange={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(screen.getByLabelText(/Symbols/i)).toHaveValue("NVDA");
  });

  it("shows Watchlists by readable name instead of raw id", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      { url: "/api/v1/screeners/presets", body: { presets: [] } },
      {
        url: "/api/v1/watchlists",
        body: {
          watchlists: [
            {
              watchlist_id: "11111111-1111-1111-1111-111111111111",
              name: "Opening Range Entries",
              description: null,
              kind: "dynamic",
              static_symbols: ["AAPL", "MSFT"],
              dynamic_rules: {
                universe: "us_equities",
                filters: [],
                source_type: "screener_version",
                screener_id: "22222222-2222-2222-2222-222222222222",
                screener_version_id: "33333333-3333-3333-3333-333333333333",
                refresh_policy: "manual",
                approval_policy: "operator_review",
              },
              created_at: "2026-04-29T09:00:00-04:00",
              updated_at: "2026-04-29T09:00:00-04:00",
              latest_snapshot_id: "44444444-4444-4444-4444-444444444444",
              snapshot_count: 1,
              status: "active",
              archived_at: null,
            },
          ],
        },
      },
      { url: "/api/v1/market-lists", body: { market_lists: [] } },
    ]);
    mountControlled({ kind: "explicit", symbols: [] });

    await screen.findByRole("button", { name: /Watchlist/i });
    await user.click(screen.getByRole("button", { name: /Watchlist/i }));
    expect(await screen.findByText(/Opening Range Entries/i)).toBeInTheDocument();
    expect(screen.getByText(/Dynamic - 1 snapshot/i)).toBeInTheDocument();
    expect(screen.queryByText(/2 symbols/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/11111111/)).not.toBeInTheDocument();
  });
});

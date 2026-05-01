import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { StrategyControlsEdit } from "./StrategyControlsEdit";
import { installFetchMock } from "@/test/renderRoute";

const NOW = "2026-04-30T00:00:00.000Z";
const SC_ID = "sc-edit-1";

function mountAt(path: string): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/controls/:id/edit" element={<StrategyControlsEdit />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const SAMPLE_LIBRARY = {
  strategy_controls_id: SC_ID,
  name: "Swing Config",
  is_default: false,
  retired_at: null,
  head: {
    payload: {
      id: "ver-1",
      strategy_controls_id: SC_ID,
      version: 1,
      name: "Swing Config",
      timeframe: "15m",
      allowed_directions: "both",
      higher_timeframe_confirmation_required: false,
      session_preference: "regular_only",
      session_windows: [],
      avoid_first_minutes: null,
      no_new_entries_after: null,
      force_flat_by: null,
      time_based_exit_after_bars: null,
      time_based_exit_after_minutes: null,
      time_based_exit_after_days: null,
      cooldown_bars: null,
      cooldown_minutes: 5,
      max_trades_per_session: 2,
      max_trades_per_day: 4,
      earnings_news_blackout_enabled: true,
      feature_refs: [],
      regime_filter_refs: [],
      created_at: NOW,
    },
    saved_at: NOW,
  },
  history: [{ version_id: "ver-1", version: 1, saved_at: NOW }],
};

const UPDATED_RECORD = {
  payload: { ...SAMPLE_LIBRARY.head.payload, version: 2, name: "Swing Config Updated" },
  saved_at: NOW,
};

const USED_BY = { deployment_ids: ["dep-abc", "dep-xyz"] };

describe("<StrategyControlsEdit />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the loaded library fields", async () => {
    restore = installFetchMock([
      { url: `/api/v1/strategy-controls/${SC_ID}/used-by`, body: USED_BY },
      { url: `/api/v1/strategy-controls/${SC_ID}`, body: SAMPLE_LIBRARY },
    ]);
    mountAt(`/controls/${SC_ID}/edit`);
    await waitFor(() => {
      expect(screen.getByText("Swing Config")).toBeInTheDocument();
    });
    expect(screen.getByDisplayValue("15m")).toBeInTheDocument();
  });

  it("renders version history and used-by in the right rail", async () => {
    restore = installFetchMock([
      { url: `/api/v1/strategy-controls/${SC_ID}/used-by`, body: USED_BY },
      { url: `/api/v1/strategy-controls/${SC_ID}`, body: SAMPLE_LIBRARY },
    ]);
    mountAt(`/controls/${SC_ID}/edit`);
    await waitFor(() => {
      expect(screen.getByText("Version history")).toBeInTheDocument();
    });
    expect(screen.getAllByText("v1").length).toBeGreaterThan(0);
    expect(screen.getByText("Where this is used")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("dep-abc")).toBeInTheDocument();
    });
    expect(screen.getByText("dep-xyz")).toBeInTheDocument();
  });

  it("edits a field and saves, calling PUT with new draft", async () => {
    const putCalls: { url: string; body: unknown }[] = [];
    const originalFetch = globalThis.fetch;

    globalThis.fetch = vi.fn(async (input, init) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "PUT" && url.includes(`/api/v1/strategy-controls/${SC_ID}`)) {
        const body = init?.body ? JSON.parse(init.body as string) : null;
        putCalls.push({ url, body });
        return new Response(JSON.stringify(UPDATED_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes(`/api/v1/strategy-controls/${SC_ID}/used-by`)) {
        return new Response(JSON.stringify(USED_BY), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes(`/api/v1/strategy-controls/${SC_ID}`)) {
        return new Response(JSON.stringify(SAMPLE_LIBRARY), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ detail: `unmocked: ${method} ${url}` }), {
        status: 599,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof globalThis.fetch;

    restore = () => {
      globalThis.fetch = originalFetch;
    };

    mountAt(`/controls/${SC_ID}/edit`);

    await waitFor(() => {
      expect(screen.getByDisplayValue("15m")).toBeInTheDocument();
    });

    const nameInput = screen.getByLabelText(/^Name$/i);
    fireEvent.change(nameInput, { target: { value: "Swing Config Updated" } });

    fireEvent.click(screen.getByRole("button", { name: /Save \(new version\)/i }));

    await waitFor(() => {
      expect(putCalls.length).toBeGreaterThan(0);
    });
    expect(putCalls[0].body).toMatchObject({
      draft: expect.objectContaining({ name: "Swing Config Updated" }),
    });
  });
});

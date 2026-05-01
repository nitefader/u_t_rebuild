import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { ExecutionPlansEdit } from "./ExecutionPlansEdit";
import { installFetchMock } from "@/test/renderRoute";

const NOW = "2026-04-30T00:00:00.000Z";
const EP_ID = "ep-edit-1";

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
          <Route path="/execution-plans/:id/edit" element={<ExecutionPlansEdit />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const SAMPLE_LIBRARY = {
  execution_plan_id: EP_ID,
  name: "Bracket Runner",
  is_default: false,
  retired_at: null,
  head: {
    payload: {
      id: "ver-1",
      execution_style_id: EP_ID,
      version: 1,
      name: "Bracket Runner",
      entry_order_type: "market",
      exit_order_type: "market",
      time_in_force: "day",
      entry_limit_offset_bps: null,
      cancel_after_bars: null,
      bracket: {
        enabled: true,
        take_profit_r_multiple: 2.0,
        stop_loss_r_multiple: 1.0,
      },
      execution_mode: "post_fill_bracket",
      trailing_stop_enabled: true,
      scale_out_enabled: false,
      feature_refs: [],
      preset: null,
      created_at: NOW,
    },
    saved_at: NOW,
  },
  history: [{ version_id: "ver-1", version: 1, saved_at: NOW }],
};

const UPDATED_RECORD = {
  payload: { ...SAMPLE_LIBRARY.head.payload, version: 2, name: "Bracket Runner Updated" },
  saved_at: NOW,
};

const USED_BY = { deployment_ids: ["dep-abc", "dep-xyz"] };

describe("<ExecutionPlansEdit />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the loaded library fields", async () => {
    restore = installFetchMock([
      { url: `/api/v1/execution-plans/${EP_ID}/used-by`, body: USED_BY },
      { url: `/api/v1/execution-plans/${EP_ID}`, body: SAMPLE_LIBRARY },
    ]);
    mountAt(`/execution-plans/${EP_ID}/edit`);
    await waitFor(() => {
      expect(screen.getByText("Bracket Runner")).toBeInTheDocument();
    });
  });

  it("renders version history and used-by in the right rail", async () => {
    restore = installFetchMock([
      { url: `/api/v1/execution-plans/${EP_ID}/used-by`, body: USED_BY },
      { url: `/api/v1/execution-plans/${EP_ID}`, body: SAMPLE_LIBRARY },
    ]);
    mountAt(`/execution-plans/${EP_ID}/edit`);
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

  it("renders ownership reference panel", async () => {
    restore = installFetchMock([
      { url: `/api/v1/execution-plans/${EP_ID}/used-by`, body: USED_BY },
      { url: `/api/v1/execution-plans/${EP_ID}`, body: SAMPLE_LIBRARY },
    ]);
    mountAt(`/execution-plans/${EP_ID}/edit`);
    await waitFor(() => {
      expect(screen.getByText("What this profile owns")).toBeInTheDocument();
    });
    expect(screen.getByText(/Entry order type & time-in-force/i)).toBeInTheDocument();
    expect(screen.getByText(/Does NOT own/i)).toBeInTheDocument();
  });

  it("edits a field and saves, calling PUT with new draft", async () => {
    const putCalls: { url: string; body: unknown }[] = [];
    const originalFetch = globalThis.fetch;

    globalThis.fetch = vi.fn(async (input, init) => {
      const url = typeof input === "string" ? input : (input as Request).url;
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "PUT" && url.includes(`/api/v1/execution-plans/${EP_ID}`)) {
        const body = init?.body ? JSON.parse(init.body as string) : null;
        putCalls.push({ url, body });
        return new Response(JSON.stringify(UPDATED_RECORD), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes(`/api/v1/execution-plans/${EP_ID}/used-by`)) {
        return new Response(JSON.stringify(USED_BY), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes(`/api/v1/execution-plans/${EP_ID}`)) {
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

    mountAt(`/execution-plans/${EP_ID}/edit`);

    await waitFor(() => {
      expect(screen.getByText("Bracket Runner")).toBeInTheDocument();
    });

    const nameInput = screen.getByLabelText(/^Name$/i);
    fireEvent.change(nameInput, { target: { value: "Bracket Runner Updated" } });

    fireEvent.click(screen.getByRole("button", { name: /Save \(new version\)/i }));

    await waitFor(() => {
      expect(putCalls.length).toBeGreaterThan(0);
    });
    expect(putCalls[0].body).toMatchObject({
      draft: expect.objectContaining({ name: "Bracket Runner Updated" }),
    });
  });
});

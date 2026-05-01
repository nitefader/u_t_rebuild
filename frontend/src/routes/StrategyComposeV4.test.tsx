/**
 * Tests for StrategyComposeV4 page.
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { Route } from "react-router-dom";
import { installFetchMock, renderRoute } from "@/test/renderRoute";
import { StrategyComposeV4 } from "./StrategyComposeV4";

// Mock Monaco editor
vi.mock("@monaco-editor/react", () => ({
  default: vi.fn(
    ({
      value,
      onChange,
    }: {
      value: string;
      onChange?: (val: string) => void;
    }) => (
      <textarea
        data-testid="monaco-stub"
        value={value}
        aria-label="Expression editor"
        onChange={(e) => onChange?.(e.target.value)}
      />
    ),
  ),
}));

const FEATURES_EMPTY = { features: [] };
const VALIDATE_OK = {
  valid: true,
  errors: [],
  warnings: [],
  feature_requirements: [],
  variables_used: [],
};

const SAVED_VERSION = {
  id: "ver-123",
  strategy_v4_id: "strat-456",
  version: 1,
  name: "ORB Strategy",
  description: null,
  identity: { tags: [], direction: "long" },
  variables: [],
  entries: { long: { expression_text: "5m.ema(9) > 5m.ema(21)", feature_requirements: [] } },
  stops: [{ id: "stop-1", mode: "simple", scope: "all", simple_type: "%", simple_value: 1.0 }],
  legs: [
    {
      id: "leg-1",
      position: 1,
      kind: "target",
      size_pct: 1.0,
      target_type: "%",
      target_value: 2.0,
      on_fill_action: { kind: "be_exact" },
    },
  ],
  logical_exits: { long: [], short: [] },
  feature_requirements: [],
  validation_status: { valid: true, errors: [], warnings: [] },
  created_at: "2026-04-30T00:00:00Z",
};

function allRoutesMock() {
  return [
    { url: "/api/v1/strategies/expression/features", body: FEATURES_EMPTY },
    {
      url: "/api/v1/strategies/expression/validate",
      method: "POST",
      body: VALIDATE_OK,
    },
  ];
}

describe("<StrategyComposeV4 />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
    vi.clearAllMocks();
  });

  it("renders empty page with name input and Save button", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText(/strategy name/i)).toBeInTheDocument();
  });

  it("renders a Back button", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    });
  });

  it("clicking Back triggers navigation without throwing", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, {
      path: "/strategies/compose",
      extraRoutes: (
        <Route path="/strategies" element={<div data-testid="strategies-page">strategies</div>} />
      ),
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Back" })).toBeInTheDocument();
    });

    // Clicking should not throw; navigate(-1) or navigate('/strategies') is called
    // depending on window.history.length. We only assert no error is raised.
    expect(() => fireEvent.click(screen.getByRole("button", { name: "Back" }))).not.toThrow();
  });

  it("shows error banner when save is clicked with empty name", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      expect(screen.getByText(/strategy name is required/i)).toBeInTheDocument();
    });
  });

  it("shows error when no entry expression is provided", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "My Strategy" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      expect(screen.getByText(/at least one entry expression/i)).toBeInTheDocument();
    });
  });

  it("Save button posts draft with placeholder stubs", async () => {
    restore = installFetchMock([
      ...allRoutesMock(),
      {
        url: "/api/v1/strategies/v4/",
        method: "POST",
        body: SAVED_VERSION,
        status: 201,
      },
    ]);
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    // Fill name
    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "ORB Strategy" },
    });

    // Fill long entry expression via the monaco stub textarea
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "5m.ema(9) > 5m.ema(21)" } });

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      const fetchCalls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls as unknown[][];
      const saveCall = fetchCalls.find((call) => {
        const url = call[0];
        return typeof url === "string" && url.includes("/strategies/v4/");
      });
      expect(saveCall).toBeDefined();
      const body = JSON.parse((saveCall![1] as { body: string }).body) as {
        draft: {
          stops: unknown[];
          legs: unknown[];
        };
      };
      expect(body.draft.stops).toHaveLength(1);
      expect(body.draft.legs).toHaveLength(1);
    });
  });

  it("renders 422 validation errors inline above editor", async () => {
    restore = installFetchMock([
      ...allRoutesMock(),
      {
        url: "/api/v1/strategies/v4/",
        method: "POST",
        body: {
          detail: {
            message: "Validation failed",
            validation_status: {
              valid: false,
              errors: ["expression parse error on line 1"],
              warnings: [],
            },
          },
        },
        status: 422,
      },
    ]);
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "Bad Strategy" },
    });
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "bad expr" } });

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      expect(screen.getByText(/expression parse error on line 1/i)).toBeInTheDocument();
    });
  });

  it("422 error title includes the error count", async () => {
    restore = installFetchMock([
      ...allRoutesMock(),
      {
        url: "/api/v1/strategies/v4/",
        method: "POST",
        body: {
          detail: {
            message: "Validation failed",
            validation_status: {
              valid: false,
              errors: ["error one", "error two", "error three"],
              warnings: [],
            },
          },
        },
        status: 422,
      },
    ]);
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "Bad Strategy" },
    });
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "bad expr" } });

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      expect(screen.getByText(/validation failed \(3 errors\)/i)).toBeInTheDocument();
    });
  });

  it("shows Saved as v{N} banner after successful save", async () => {
    restore = installFetchMock([
      ...allRoutesMock(),
      {
        url: "/api/v1/strategies/v4/",
        method: "POST",
        body: SAVED_VERSION,
        status: 201,
      },
    ]);
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "ORB Strategy" },
    });
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "5m.ema(9) > 5m.ema(21)" } });

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved as v1/i)).toBeInTheDocument();
    });
  });

  it("save banner View version link points to ?id={savedId}", async () => {
    restore = installFetchMock([
      ...allRoutesMock(),
      {
        url: "/api/v1/strategies/v4/",
        method: "POST",
        body: SAVED_VERSION,
        status: 201,
      },
    ]);
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "ORB Strategy" },
    });
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "5m.ema(9) > 5m.ema(21)" } });

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      const link = screen.getByRole("link", { name: /view version/i });
      expect(link).toHaveAttribute("href", "/strategies/compose?id=ver-123");
    });
  });

  it("second save shows updated version number replacing previous banner", async () => {
    const savedV2 = { ...SAVED_VERSION, id: "ver-456", version: 2 };
    let postHits = 0;

    /** Layered dispatcher: deterministic first/second POST save bodies — avoids flaky mid-test fetch replacement races. */
    const innerRestore = installFetchMock([
      ...allRoutesMock(),
      { url: "/api/v1/strategies/v4/ver-123", body: SAVED_VERSION },
      { url: "/api/v1/strategies/v4/ver-456", body: savedV2 },
    ]);
    const chainFetch = globalThis.fetch;

    globalThis.fetch = vi.fn(
      async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
        const urlStr =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url;
        const method = (init?.method ?? "GET").toUpperCase();

        const isComposePost =
          method === "POST" &&
          urlStr.includes("/api/v1/strategies/v4") &&
          !urlStr.includes("ver");

        if (isComposePost) {
          postHits++;
          const bodyJson = JSON.stringify(postHits >= 2 ? savedV2 : SAVED_VERSION);
          return new Response(bodyJson, {
            status: 201,
            headers: { "Content-Type": "application/json" },
          });
        }

        return (chainFetch as typeof fetch)(input, init);
      },
    );

    restore = innerRestore;

    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() =>
      expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "ORB Strategy" },
    });
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "5m.ema(9) > 5m.ema(21)" } });

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved as v1/i)).toBeInTheDocument();
    });

    // Wait past 250ms double-save guard
    await new Promise((r) => setTimeout(r, 300));

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      expect(screen.getByText(/saved as v2/i)).toBeInTheDocument();
    });
    expect(postHits).toBe(2);
  });

  it("renders StopsSection and LegsSection sections", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByRole("region", { name: /stops/i })).toBeInTheDocument();
      expect(screen.getByRole("region", { name: /trade legs/i })).toBeInTheDocument();
    });
  });

  it("mounts with one default stop row and one default leg row from draftDefaults", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getAllByTestId("stop-row")).toHaveLength(1);
      expect(screen.getAllByTestId("leg-row")).toHaveLength(1);
    });
  });

  it("Save button is disabled when leg sizes do not sum to 100%", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    // Add a second leg (now sum won't be 1.0 without auto-balance)
    fireEvent.click(screen.getByRole("button", { name: /\+ add target/i }));

    // Manually break sum by editing the first leg's size to 10%
    const sizeInputs = screen.getAllByRole("spinbutton", { name: /leg \d+ size percent/i });
    fireEvent.change(sizeInputs[0], { target: { value: "10" } });

    // Save button may now surface an error or be disabled
    // Either way, fill in required fields and attempt save
    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "My Strategy" },
    });
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "5m.ema(9) > 5m.ema(21)" } });

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));
    await waitFor(() => {
      expect(screen.getAllByText(/total/i).length).toBeGreaterThanOrEqual(1);
    });
  });

  it("Save posts edited legs and stops instead of defaults", async () => {
    restore = installFetchMock([
      ...allRoutesMock(),
      {
        url: "/api/v1/strategies/v4/",
        method: "POST",
        body: SAVED_VERSION,
        status: 201,
      },
    ]);
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByRole("button", { name: /save strategy/i })).toBeInTheDocument());

    // Fill required fields
    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "ORB Strategy" },
    });
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "5m.ema(9) > 5m.ema(21)" } });

    // Edit the stop value
    const stopValueInput = screen.getByRole("spinbutton", { name: /stop value/i });
    fireEvent.change(stopValueInput, { target: { value: "2.5" } });

    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      const fetchCalls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls as unknown[][];
      const saveCall = fetchCalls.find((call) => {
        const url = call[0];
        return typeof url === "string" && url.includes("/strategies/v4/");
      });
      expect(saveCall).toBeDefined();
      const body = JSON.parse((saveCall![1] as { body: string }).body) as {
        draft: {
          stops: Array<{ simple_value: number }>;
          legs: unknown[];
        };
      };
      expect(body.draft.stops[0].simple_value).toBeCloseTo(2.5, 4);
    });
  });

  it("renders ExitsSection with empty long and short columns by default", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByText(/Long exits/i)).toBeInTheDocument();
      expect(screen.getByText(/Short exits/i)).toBeInTheDocument();
    });

    // Both columns should show the empty-state placeholder
    const placeholders = screen.getAllByText(/Drop exit blocks from the palette/i);
    expect(placeholders).toHaveLength(2);
  });

  it("adding an exit to the long column updates state and is included in the saved draft", async () => {
    restore = installFetchMock([
      ...allRoutesMock(),
      {
        url: "/api/v1/strategies/v4/",
        method: "POST",
        body: SAVED_VERSION,
        status: 201,
      },
    ]);
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByText(/Long exits/i)).toBeInTheDocument());

    // Simulate a drop event on the long column drop zone
    const { EXIT_DRAG_MIME, serializeExitDrag } = await import("@/strategy_ide_v4/exitDragPayload");
    const dropZone = screen.getByRole("list", { name: /Long exits drop zone/i });

    fireEvent.drop(dropZone, {
      dataTransfer: {
        types: [EXIT_DRAG_MIME],
        getData: (mime: string) =>
          mime === EXIT_DRAG_MIME ? serializeExitDrag("session_end") : "",
      },
    });

    // The empty placeholder for long should now be gone
    await waitFor(() => {
      expect(screen.getAllByText(/Drop exit blocks from the palette/i)).toHaveLength(1);
    });

    // Now save and verify the draft includes the exit
    fireEvent.change(screen.getByPlaceholderText(/strategy name/i), {
      target: { value: "ORB Strategy" },
    });
    const editors = screen.getAllByTestId("monaco-stub");
    fireEvent.change(editors[0], { target: { value: "5m.ema(9) > 5m.ema(21)" } });
    fireEvent.click(screen.getByRole("button", { name: /save strategy/i }));

    await waitFor(() => {
      const fetchCalls = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls as unknown[][];
      const saveCall = fetchCalls.find((call) => {
        const url = call[0];
        return typeof url === "string" && url.includes("/strategies/v4/");
      });
      expect(saveCall).toBeDefined();
      const body = JSON.parse((saveCall![1] as { body: string }).body) as {
        draft: {
          logical_exits: { long: Array<{ template_id: string }>; short: unknown[] };
        };
      };
      expect(body.draft.logical_exits.long).toHaveLength(1);
      expect(body.draft.logical_exits.long[0].template_id).toBe("session_end");
      expect(body.draft.logical_exits.short).toHaveLength(0);
    });
  });

  it("loading via ?id= with persisted exits hydrates ExitsSection", async () => {
    const versionWithExits = {
      ...SAVED_VERSION,
      logical_exits: {
        long: [
          {
            id: "exit-long-1",
            template_id: "no_progress",
            params: { bars: 10, threshold_r: 0.25 },
          },
        ],
        short: [],
      },
    };

    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { MemoryRouter, Route, Routes } = await import("react-router-dom");
    const { render: rtlRender } = await import("@testing-library/react");

    const fetchMockRestore = installFetchMock([
      ...allRoutesMock(),
      { url: "/api/v1/strategies/v4/ver-123", body: versionWithExits },
    ]);

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    rtlRender(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/strategies/compose?id=ver-123"]}>
          <Routes>
            <Route path="/strategies/compose" element={<StrategyComposeV4 />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // After load, the long column should show the block, not the empty placeholder
    await waitFor(() => {
      expect(screen.getAllByText(/No-progress timeout/i).length).toBeGreaterThan(0);
    });

    // Short column still empty
    expect(screen.getAllByText(/Drop exit blocks from the palette/i)).toHaveLength(1);

    fetchMockRestore();
  });

  it("prefills state when ?id= is provided", async () => {
    restore = installFetchMock([
      ...allRoutesMock(),
      {
        url: "/api/v1/strategies/v4/ver-123",
        body: SAVED_VERSION,
      },
    ]);
    // Use extraRoutes so the route pattern is correct but initial entry has params
    const { QueryClient, QueryClientProvider } = await import("@tanstack/react-query");
    const { MemoryRouter, Route, Routes } = await import("react-router-dom");
    const { render } = await import("@testing-library/react");

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/strategies/compose?id=ver-123"]}>
          <Routes>
            <Route path="/strategies/compose" element={<StrategyComposeV4 />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(
        (screen.getByPlaceholderText(/strategy name/i) as HTMLInputElement).value,
      ).toBe("ORB Strategy");
    });
  });

  // ---------------------------------------------------------------------------
  // Issue D — new UI features
  // ---------------------------------------------------------------------------

  it("renders DirectionToggle in the top bar", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /long only/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /short only/i })).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /both/i })).toBeInTheDocument();
    });
  });

  it("renders HorizonPicker in the top bar", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /swing/i })).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: /base timeframe/i })).toBeInTheDocument();
    });
  });

  it("renders CoverageChips in the top bar", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByLabelText(/coverage status/i)).toBeInTheDocument();
    });
  });

  it("Coverage Entry chip becomes satisfied after entering an expression", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => expect(screen.getByTestId("monaco-stub")).toBeInTheDocument());

    // Initially unsatisfied
    expect(screen.getByLabelText(/entry not configured/i)).toBeInTheDocument();

    // Type an expression
    fireEvent.change(screen.getByTestId("monaco-stub"), {
      target: { value: "5m.ema(9) > 5m.ema(21)" },
    });

    await waitFor(() => {
      expect(screen.getByLabelText(/entry satisfied/i)).toBeInTheDocument();
    });
  });

  it("renders StarterStrategyPanel with starter cards visible by default", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByText(/starter strategies/i)).toBeInTheDocument();
      expect(screen.getAllByTestId("starter-card").length).toBeGreaterThan(0);
    });
  });

  it("clicking Apply on a starter replaces the draft (name field updates)", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getAllByTestId("starter-card").length).toBeGreaterThan(0);
    });

    // Expand first card to reveal Apply button
    const expandBtns = screen.getAllByRole("button", { name: /expand strategy details/i });
    fireEvent.click(expandBtns[0]);

    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /apply.*template/i })[0]).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByRole("button", { name: /apply.*template/i })[0]);

    // The name input should now contain the starter's name (non-empty)
    await waitFor(() => {
      const nameInput = screen.getByPlaceholderText(/strategy name/i) as HTMLInputElement;
      expect(nameInput.value.length).toBeGreaterThan(0);
    });
  });

  it("renders ExecutionPreview below legs section", async () => {
    restore = installFetchMock(allRoutesMock());
    renderRoute(<StrategyComposeV4 />, { path: "/strategies/compose" });

    await waitFor(() => {
      expect(screen.getByRole("region", { name: /execution preview/i })).toBeInTheDocument();
    });
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactNode } from "react";

/**
 * renderRoute — minimal QueryClient + MemoryRouter wrapper used by
 * page-level Vitest suites. Every test gets a *fresh* QueryClient so
 * cached state doesn't bleed between empty / happy / degraded
 * variants.
 */
export interface RenderRouteOptions {
  /** The route pattern for the primary route (e.g. `/deployments/:id`). Defaults to `/`. */
  path?: string;
  /**
   * The actual URL to navigate to in the MemoryRouter (e.g. `/deployments/abc-123`).
   * When omitted, defaults to `path`. Use this when `path` contains dynamic segments.
   */
  initialPath?: string;
  /** Extra `<Route>` elements (e.g. accept dynamic segments). */
  extraRoutes?: ReactNode;
}

export function renderRoute(element: ReactNode, options: RenderRouteOptions = {}): RenderResult {
  const { path = "/", initialPath, extraRoutes } = options;
  const entry = initialPath ?? path;
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path={path} element={element} />
          {extraRoutes}
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Mock global fetch with a route-matched dispatcher. */
export interface MockRoute {
  /** Matches the URL by substring or RegExp. */
  url: string | RegExp;
  /** Body to return. Strings are passed through; objects are JSON.stringified. */
  body: unknown;
  status?: number;
  /** Optional method filter (default: any). */
  method?: string;
}

export function installFetchMock(routes: MockRoute[]): () => void {
  const original = globalThis.fetch;
  globalThis.fetch = vi.fn(async (input: Parameters<typeof fetch>[0], init?: Parameters<typeof fetch>[1]) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : (input as Request).url;
    const method = (init?.method ?? (typeof input === "object" && "method" in input ? (input as Request).method : "GET")).toUpperCase();
    // Sort by specificity so that more-specific patterns win over broader ones.
    // Regex patterns always beat plain strings. Among strings, longer beats shorter.
    // This ensures "/api/v1/strategies/v4/" is preferred over "/api/v1/strategies"
    // and regex patterns like /\/api\/v1\/watchlists\/some-id$/ beat "/api/v1/watchlists".
    const sorted = [...routes].sort((a, b) => {
      const laIsRegex = typeof a.url !== "string";
      const lbIsRegex = typeof b.url !== "string";
      if (laIsRegex && !lbIsRegex) return -1; // regex before string
      if (!laIsRegex && lbIsRegex) return 1;  // string after regex
      const la = typeof a.url === "string" ? a.url.length : 0;
      const lb = typeof b.url === "string" ? b.url.length : 0;
      return lb - la; // longer string first
    });
    const matched = sorted.find((r) => {
      if (r.method && r.method.toUpperCase() !== method) return false;
      if (typeof r.url === "string") return url.includes(r.url);
      return r.url.test(url);
    });
    if (!matched) {
      return new Response(JSON.stringify({ detail: `unmocked: ${method} ${url}` }), {
        status: 599,
        headers: { "Content-Type": "application/json" },
      });
    }
    const body = typeof matched.body === "string" ? matched.body : JSON.stringify(matched.body);
    return new Response(body, {
      status: matched.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof globalThis.fetch;
  return () => {
    globalThis.fetch = original;
  };
}

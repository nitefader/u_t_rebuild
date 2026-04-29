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
  /** The route to mount. Defaults to `/`. */
  path?: string;
  /** Extra `<Route>` elements (e.g. accept dynamic segments). */
  extraRoutes?: ReactNode;
}

export function renderRoute(element: ReactNode, options: RenderRouteOptions = {}): RenderResult {
  const { path = "/", extraRoutes } = options;
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
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
    const matched = routes.find((r) => {
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

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { ChartLabHubCard } from "./ChartLabHubCard";
import { writeChartLabPin } from "@/lib/chartLabPin";

// jsdom does not implement WebSocket; provide a no-op stub so the
// pin-driven hub card can mount without exercising the real network.
class StubWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  readyState = StubWebSocket.CONNECTING;
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  constructor(_url: string) {}
  addEventListener(): void {}
  removeEventListener(): void {}
  send(): void {}
  close(): void {
    this.readyState = StubWebSocket.CLOSED;
  }
}
(globalThis as { WebSocket: typeof WebSocket }).WebSocket =
  StubWebSocket as unknown as typeof WebSocket;

function mount(): void {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <ChartLabHubCard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("<ChartLabHubCard />", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });
  afterEach(() => {
    window.localStorage.clear();
  });

  it("renders the unpinned state with a link to Chart Lab", () => {
    mount();
    expect(screen.getByText(/no pin/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Open Chart Lab/i })).toBeInTheDocument();
    // Helper copy explains the pin behaviour without leaking internal state.
    expect(screen.getByText(/Pin a Chart Lab session/i)).toBeInTheDocument();
  });

  it("renders the pinned symbol + Unpin control + status row", () => {
    writeChartLabPin("SPY");
    mount();
    expect(screen.getByText("SPY")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Unpin/i })).toBeInTheDocument();
    // Stream / Last bar / Last update rows are present
    expect(screen.getByText("Stream")).toBeInTheDocument();
    expect(screen.getByText("Last bar")).toBeInTheDocument();
    expect(screen.getByText("Last update")).toBeInTheDocument();
  });

  it("clicking Unpin releases the pin and falls back to the unpinned panel", () => {
    writeChartLabPin("AAPL");
    mount();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Unpin/i }));
    expect(screen.getByText(/no pin/i)).toBeInTheDocument();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DiscoveryScheduleControls } from "./DiscoveryScheduleControls";
import { installFetchMock } from "@/test/renderRoute";

const SCHEDULE_ID = "11111111-1111-1111-1111-111111111111";
const SCREENER_ID = "22222222-2222-2222-2222-222222222222";
const VERSION_ID = "33333333-3333-3333-3333-333333333333";
const WATCHLIST_ID = "44444444-4444-4444-4444-444444444444";

function mount(node: JSX.Element): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  render(<QueryClientProvider client={queryClient}>{node}</QueryClientProvider>);
}

function schedule(overrides = {}) {
  return {
    schedule_id: SCHEDULE_ID,
    name: "Premarket movers",
    target_kind: "screener_run",
    screener_id: SCREENER_ID,
    screener_version_id: VERSION_ID,
    watchlist_id: null,
    cadence: "daily",
    interval_minutes: null,
    time_of_day: "09:15",
    weekdays: [0, 1, 2, 3, 4],
    timezone_name: "America/New_York",
    session_start: null,
    session_end: null,
    approval_policy: "operator_review",
    enabled: true,
    status: "active",
    created_at: "2026-04-29T12:00:00Z",
    updated_at: "2026-04-29T12:00:00Z",
    last_attempt_at: "2026-04-29T13:15:00Z",
    last_success_at: "2026-04-29T13:15:10Z",
    next_run_at: "2026-04-30T13:15:00Z",
    last_status: "completed",
    last_error: null,
    last_screener_run_id: "55555555-5555-5555-5555-555555555555",
    last_watchlist_snapshot_id: null,
    execution_count: 1,
    audit_events: [],
    ...overrides,
  };
}

describe("<DiscoveryScheduleControls />", () => {
  let restore: (() => void) | null = null;

  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("shows execution history with readable evidence labels and diff counts", async () => {
    restore = installFetchMock([
      {
        url: /\/api\/v1\/discovery-schedules\/11111111-1111-1111-1111-111111111111\/executions$/,
        body: {
          executions: [
            {
              execution_id: "66666666-6666-6666-6666-666666666666",
              schedule_id: SCHEDULE_ID,
              schedule_name: "Premarket movers",
              target_kind: "watchlist_refresh",
              trigger: "run_now",
              started_at: "2026-04-29T13:30:00Z",
              completed_at: "2026-04-29T13:30:02Z",
              status: "completed",
              screener_run_id: null,
              watchlist_snapshot_id: "77777777-7777-7777-7777-777777777777",
              added_symbols: ["AAPL", "MSFT"],
              removed_symbols: ["TSLA"],
              stayed_symbols: ["NVDA", "AMD", "META", "GOOGL", "AMZN"],
              error: null,
              audit_events: [],
            },
          ],
        },
      },
      {
        url: "/api/v1/discovery-schedules",
        method: "GET",
        body: {
          schedules: [schedule({ target_kind: "watchlist_refresh", watchlist_id: WATCHLIST_ID })],
        },
      },
    ]);

    mount(
      <DiscoveryScheduleControls
        targetKind="watchlist_refresh"
        targetName="Opening Range Entries"
        watchlistId={WATCHLIST_ID}
      />,
    );

    expect(await screen.findByText("Premarket movers")).toBeInTheDocument();
    expect(await screen.findByText("Execution history")).toBeInTheDocument();
    expect(screen.getByText(/Watchlist snapshot recorded/i)).toBeInTheDocument();
    expect(screen.getByTitle(/Watchlist snapshot id: 77777777/i)).toBeInTheDocument();
    expect(screen.getByText(/\+2 \/ -1 \/ =5/)).toBeInTheDocument();
    expect(screen.getByText(/America\/New_York \(market time\)/)).toBeInTheDocument();
    expect(screen.getByText(/Days: Mon-Fri/i)).toBeInTheDocument();
  });

  it("creates a watchlist refresh schedule through visible controls", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      { url: "/api/v1/discovery-schedules", method: "GET", body: { schedules: [] } },
      {
        url: "/api/v1/discovery-schedules",
        method: "POST",
        body: schedule({
          name: "Open-hour refresh",
          target_kind: "watchlist_refresh",
          screener_id: null,
          screener_version_id: null,
          watchlist_id: WATCHLIST_ID,
          cadence: "every_n_minutes",
          interval_minutes: 15,
          time_of_day: null,
          session_start: "09:30",
          session_end: "10:30",
          approval_policy: "auto_snapshot",
        }),
      },
    ]);

    mount(
      <DiscoveryScheduleControls
        targetKind="watchlist_refresh"
        targetName="Opening Range Entries"
        watchlistId={WATCHLIST_ID}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /Schedule refresh/i }));
    await user.clear(screen.getByLabelText(/Schedule name/i));
    await user.type(screen.getByLabelText(/Schedule name/i), "Open-hour refresh");
    await user.selectOptions(screen.getByLabelText(/Cadence/i), "every_n_minutes");
    fireEvent.change(screen.getByLabelText(/Interval minutes/i), { target: { value: "15" } });
    await user.type(screen.getByLabelText(/Session start/i), "09:30");
    await user.type(screen.getByLabelText(/Session end/i), "10:30");
    await user.click(screen.getByRole("button", { name: /^Sat$/i }));
    await user.selectOptions(screen.getByLabelText(/Approval policy/i), "auto_snapshot");
    await user.click(screen.getByRole("button", { name: /Save schedule/i }));

    await waitFor(() => {
      const createCall = vi
        .mocked(fetch)
        .mock.calls.find(
          ([url, init]) =>
            String(url).includes("/api/v1/discovery-schedules") && init?.method === "POST",
        );
      expect(createCall).toBeTruthy();
      expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
        name: "Open-hour refresh",
        target_kind: "watchlist_refresh",
        watchlist_id: WATCHLIST_ID,
        cadence: "every_n_minutes",
        interval_minutes: 15,
        session_start: "09:30",
        session_end: "10:30",
        weekdays: [0, 1, 2, 3, 4, 5],
        timezone_name: "America/New_York",
        approval_policy: "auto_snapshot",
      });
    });
  });

  it("runs, pauses, and archives schedules through visible controls", async () => {
    const user = userEvent.setup();
    restore = installFetchMock([
      {
        url: /\/api\/v1\/discovery-schedules\/11111111-1111-1111-1111-111111111111\/executions$/,
        method: "GET",
        body: { executions: [] },
      },
      { url: "/api/v1/discovery-schedules", method: "GET", body: { schedules: [schedule()] } },
      {
        url: /\/api\/v1\/discovery-schedules\/11111111-1111-1111-1111-111111111111\/run-now$/,
        method: "POST",
        body: {
          execution_id: "66666666-6666-6666-6666-666666666666",
          schedule_id: SCHEDULE_ID,
          schedule_name: "Premarket movers",
          target_kind: "screener_run",
          trigger: "run_now",
          started_at: "2026-04-29T13:30:00Z",
          completed_at: "2026-04-29T13:30:02Z",
          status: "completed",
          screener_run_id: "55555555-5555-5555-5555-555555555555",
          watchlist_snapshot_id: null,
          added_symbols: [],
          removed_symbols: [],
          stayed_symbols: [],
          error: null,
          audit_events: [],
        },
      },
      {
        url: /\/api\/v1\/discovery-schedules\/11111111-1111-1111-1111-111111111111\/pause$/,
        method: "POST",
        body: schedule({ status: "paused", enabled: false }),
      },
      {
        url: /\/api\/v1\/discovery-schedules\/11111111-1111-1111-1111-111111111111\/archive$/,
        method: "POST",
        body: schedule({ status: "archived", enabled: false }),
      },
    ]);

    mount(
      <DiscoveryScheduleControls
        targetKind="screener_run"
        targetName="Day Gainers"
        screenerId={SCREENER_ID}
        screenerVersionId={VERSION_ID}
      />,
    );

    await user.click(await screen.findByRole("button", { name: /Run schedule now/i }));
    await user.click(screen.getByRole("button", { name: /Pause/i }));
    await user.click(screen.getByRole("button", { name: /Archive/i }));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/run-now"),
        expect.objectContaining({ method: "POST" }),
      );
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/pause"),
        expect.objectContaining({ method: "POST" }),
      );
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/archive"),
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});

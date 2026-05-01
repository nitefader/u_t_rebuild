import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { StrategyControls } from "./StrategyControls";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const NOW = "2026-04-30T00:00:00.000Z";

const SAMPLE_LIBRARY = {
  strategy_controls_id: "sc-1",
  name: "Intraday ORB",
  head_version_number: 2,
  is_default: true,
  retired_at: null,
  usage_count: 3,
};

const SAMPLE_RECORD = {
  payload: {
    id: "ver-2",
    strategy_controls_id: "sc-1",
    version: 2,
    name: "Intraday ORB",
    timeframe: "5m",
    allowed_directions: "long",
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
    cooldown_minutes: 10,
    max_trades_per_session: 3,
    max_trades_per_day: null,
    earnings_news_blackout_enabled: false,
    feature_refs: [],
    regime_filter_refs: [],
    created_at: NOW,
  },
  saved_at: NOW,
};

describe("<StrategyControls />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders empty state when no libraries exist", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: { libraries: [] } },
    ]);
    renderRoute(<StrategyControls />);
    await waitFor(() => {
      expect(screen.getByText(/No controls libraries yet/i)).toBeInTheDocument();
    });
  });

  it("renders library cards on the happy path", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: { libraries: [SAMPLE_LIBRARY] } },
    ]);
    renderRoute(<StrategyControls />);
    await waitFor(() => {
      expect(screen.getByText("Intraday ORB")).toBeInTheDocument();
    });
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.getByText("3 deployments")).toBeInTheDocument();
  });

  it("fires duplicate action without crashing", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: { libraries: [SAMPLE_LIBRARY] } },
      {
        url: "/api/v1/strategy-controls/sc-1/duplicate",
        method: "POST",
        body: SAMPLE_RECORD,
        status: 201,
      },
    ]);
    renderRoute(<StrategyControls />);
    await waitFor(() => expect(screen.getByText("Intraday ORB")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Duplicate/i }));
    await waitFor(() => {
      expect(screen.queryByText(/action failed/i)).toBeNull();
    });
  });

  it("opens create drawer on New Library click", async () => {
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: { libraries: [] } },
    ]);
    renderRoute(<StrategyControls />);
    await waitFor(() =>
      expect(screen.getByText(/No controls libraries yet/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getAllByRole("button", { name: /New Library/i })[0]);
    await waitFor(() => {
      expect(screen.getByText(/New Controls Library/i)).toBeInTheDocument();
    });
  });

  it("opens retire confirm dialog", async () => {
    const nonDefaultLib = { ...SAMPLE_LIBRARY, is_default: false };
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: { libraries: [nonDefaultLib] } },
    ]);
    renderRoute(<StrategyControls />);
    await waitFor(() => expect(screen.getByText("Intraday ORB")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Retire/i }));
    await waitFor(() => {
      expect(screen.getByText(/Retire "Intraday ORB"/i)).toBeInTheDocument();
    });
  });

  it("fires set-default action without crashing", async () => {
    const nonDefaultLib = { ...SAMPLE_LIBRARY, is_default: false };
    restore = installFetchMock([
      { url: "/api/v1/strategy-controls", body: { libraries: [nonDefaultLib] } },
      {
        url: "/api/v1/strategy-controls/sc-1/set-default",
        method: "POST",
        body: "",
        status: 204,
      },
    ]);
    renderRoute(<StrategyControls />);
    await waitFor(() => expect(screen.getByText("Intraday ORB")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Set default/i }));
    await waitFor(() => {
      expect(screen.queryByText(/action failed/i)).toBeNull();
    });
  });
});

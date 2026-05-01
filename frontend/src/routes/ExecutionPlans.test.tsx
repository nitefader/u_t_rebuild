import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { ExecutionPlans } from "./ExecutionPlans";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const NOW = "2026-04-30T00:00:00.000Z";

const SAMPLE_LIBRARY = {
  execution_plan_id: "ep-1",
  name: "Market Entry Fast",
  head_version_number: 2,
  is_default: true,
  retired_at: null,
  usage_count: 3,
};

const SAMPLE_RECORD = {
  payload: {
    id: "ver-2",
    execution_style_id: "ep-1",
    version: 2,
    name: "Market Entry Fast",
    entry_order_type: "market",
    exit_order_type: "market",
    time_in_force: "day",
    entry_limit_offset_bps: null,
    cancel_after_bars: null,
    bracket: { enabled: false },
    execution_mode: "post_fill_bracket",
    trailing_stop_enabled: false,
    scale_out_enabled: false,
    feature_refs: [],
    preset: null,
    created_at: NOW,
  },
  saved_at: NOW,
};

describe("<ExecutionPlans />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders empty state when no libraries exist", async () => {
    restore = installFetchMock([
      { url: "/api/v1/execution-plans", body: { libraries: [] } },
    ]);
    renderRoute(<ExecutionPlans />);
    await waitFor(() => {
      expect(screen.getByText(/No execution profiles yet/i)).toBeInTheDocument();
    });
  });

  it("renders library cards on the happy path", async () => {
    restore = installFetchMock([
      { url: "/api/v1/execution-plans", body: { libraries: [SAMPLE_LIBRARY] } },
    ]);
    renderRoute(<ExecutionPlans />);
    await waitFor(() => {
      expect(screen.getByText("Market Entry Fast")).toBeInTheDocument();
    });
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText("Default")).toBeInTheDocument();
    expect(screen.getByText("3 deployments")).toBeInTheDocument();
  });

  it("fires duplicate action without crashing", async () => {
    restore = installFetchMock([
      { url: "/api/v1/execution-plans", body: { libraries: [SAMPLE_LIBRARY] } },
      {
        url: "/api/v1/execution-plans/ep-1/duplicate",
        method: "POST",
        body: SAMPLE_RECORD,
        status: 201,
      },
    ]);
    renderRoute(<ExecutionPlans />);
    await waitFor(() => expect(screen.getByText("Market Entry Fast")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Duplicate/i }));
    await waitFor(() => {
      expect(screen.queryByText(/action failed/i)).toBeNull();
    });
  });

  it("opens create drawer on New Profile click", async () => {
    restore = installFetchMock([
      { url: "/api/v1/execution-plans", body: { libraries: [] } },
    ]);
    renderRoute(<ExecutionPlans />);
    await waitFor(() =>
      expect(screen.getByText(/No execution profiles yet/i)).toBeInTheDocument(),
    );
    fireEvent.click(screen.getAllByRole("button", { name: /New Profile/i })[0]);
    await waitFor(() => {
      expect(screen.getByText(/New Execution Profile/i)).toBeInTheDocument();
    });
  });

  it("opens retire confirm dialog", async () => {
    const nonDefaultLib = { ...SAMPLE_LIBRARY, is_default: false };
    restore = installFetchMock([
      { url: "/api/v1/execution-plans", body: { libraries: [nonDefaultLib] } },
    ]);
    renderRoute(<ExecutionPlans />);
    await waitFor(() => expect(screen.getByText("Market Entry Fast")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Retire/i }));
    await waitFor(() => {
      expect(screen.getByText(/Retire "Market Entry Fast"/i)).toBeInTheDocument();
    });
  });

  it("fires set-default action without crashing", async () => {
    const nonDefaultLib = { ...SAMPLE_LIBRARY, is_default: false };
    restore = installFetchMock([
      { url: "/api/v1/execution-plans", body: { libraries: [nonDefaultLib] } },
      {
        url: "/api/v1/execution-plans/ep-1/set-default",
        method: "POST",
        body: "",
        status: 204,
      },
    ]);
    renderRoute(<ExecutionPlans />);
    await waitFor(() => expect(screen.getByText("Market Entry Fast")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Set default/i }));
    await waitFor(() => {
      expect(screen.queryByText(/action failed/i)).toBeNull();
    });
  });
});

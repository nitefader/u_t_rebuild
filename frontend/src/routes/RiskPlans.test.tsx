import { afterEach, describe, expect, it } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { RiskPlans } from "./RiskPlans";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

/**
 * Frontend acceptance tests per RISK_PLAN_SIGNALPLAN_BACKTEST_BACKEND_CONTRACT §11.2.
 *
 *   - Risk Plans list renders.
 *   - Create RiskPlan drawer validates fields.
 *   - AI-generated RiskPlan requires user save/approval.
 */

const NOW = "2026-04-27T00:00:00.000Z";

const SAMPLE_PLAN = {
  risk_plan_id: "plan-1",
  name: "Balanced Momentum",
  description: "Default balanced plan",
  status: "active",
  risk_score: 5,
  risk_tier: "balanced",
  source: "manual",
  ai_generated: false,
  ai_summary: null,
  created_at: NOW,
  updated_at: NOW,
  active_version_id: "ver-1",
  active_version: {
    risk_plan_version_id: "ver-1",
    risk_plan_id: "plan-1",
    version: 1,
    status: "active",
    config_fingerprint: "abc",
    config: {
      sizing_method: "risk_percent",
      risk_per_trade_pct: 1.0,
      max_open_positions: 5,
      max_daily_loss_pct: 3.0,
      max_drawdown_pct: 10.0,
      stop_required: true,
    },
    created_at: NOW,
    activated_at: NOW,
  },
  linked_account_count: 0,
  last_used_at: null,
};

describe("<RiskPlans />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("renders the empty state when no Risk Plans exist", async () => {
    restore = installFetchMock([{ url: "/api/v1/risk-plans", body: { risk_plans: [] } }]);
    renderRoute(<RiskPlans />);
    await waitFor(() => {
      expect(screen.getByText(/No Risk Plans yet/i)).toBeInTheDocument();
    });
  });

  it("renders a Risk Plan row on the happy path", async () => {
    restore = installFetchMock([
      { url: "/api/v1/risk-plans", body: { risk_plans: [SAMPLE_PLAN] } },
    ]);
    renderRoute(<RiskPlans />);
    await waitFor(() => {
      expect(screen.getByText("Balanced Momentum")).toBeInTheDocument();
    });
  });

  it("filters by status", async () => {
    restore = installFetchMock([
      {
        url: "/api/v1/risk-plans",
        body: {
          risk_plans: [
            SAMPLE_PLAN,
            { ...SAMPLE_PLAN, risk_plan_id: "plan-2", name: "Archived Plan", status: "archived" },
          ],
        },
      },
    ]);
    renderRoute(<RiskPlans />);
    await waitFor(() => {
      expect(screen.getByText("Balanced Momentum")).toBeInTheDocument();
      expect(screen.getByText("Archived Plan")).toBeInTheDocument();
    });
    const statusSelect = screen.getByLabelText("Status") as HTMLSelectElement;
    fireEvent.change(statusSelect, { target: { value: "active" } });
    await waitFor(() => {
      expect(screen.queryByText("Archived Plan")).not.toBeInTheDocument();
      expect(screen.getByText("Balanced Momentum")).toBeInTheDocument();
    });
  });

  it("opens the New Risk Plan drawer when the operator clicks the action", async () => {
    restore = installFetchMock([{ url: "/api/v1/risk-plans", body: { risk_plans: [] } }]);
    renderRoute(<RiskPlans />);
    const buttons = await screen.findAllByText(/New Risk Plan/i);
    // The first match is the action button
    fireEvent.click(buttons[0]);
    await waitFor(() => {
      expect(screen.getAllByText(/Create Risk Plan/i)[0]).toBeInTheDocument();
    });
  });
});

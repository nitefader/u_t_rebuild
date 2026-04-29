import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { RiskPlanPicker } from "./RiskPlanPicker";
import { installFetchMock, renderRoute } from "@/test/renderRoute";

const SAMPLE_PLAN = {
  risk_plan_id: "plan-1",
  name: "Balanced Momentum",
  description: "",
  status: "active",
  risk_score: 5,
  risk_tier: "balanced",
  source: "manual",
  ai_generated: false,
  created_at: "2026-04-27T00:00:00.000Z",
  updated_at: "2026-04-27T00:00:00.000Z",
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
    },
    created_at: "2026-04-27T00:00:00.000Z",
  },
};

function Harness({ onChange }: { onChange?: (v: string | null) => void }): JSX.Element {
  const [value, setValue] = useState<string | null>(null);
  return (
    <RiskPlanPicker
      value={value}
      onChange={(v) => {
        setValue(v);
        onChange?.(v);
      }}
      required
    />
  );
}

describe("<RiskPlanPicker />", () => {
  let restore: (() => void) | null = null;
  afterEach(() => {
    restore?.();
    restore = null;
  });

  it("emits the version id of the selected plan", async () => {
    restore = installFetchMock([
      { url: "/api/v1/risk-plans", body: { risk_plans: [SAMPLE_PLAN] } },
    ]);
    const onChange = vi.fn();
    renderRoute(<Harness onChange={onChange} />);
    await waitFor(() => {
      expect(screen.getByText(/Balanced Momentum/)).toBeInTheDocument();
    });
    const select = screen.getByLabelText(/Risk Plan/, { selector: "select" }) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "ver-1" } });
    expect(onChange).toHaveBeenCalledWith("ver-1");
  });

  it("renders inline risk score / tier / sizing once selected", async () => {
    restore = installFetchMock([
      { url: "/api/v1/risk-plans", body: { risk_plans: [SAMPLE_PLAN] } },
    ]);
    renderRoute(<Harness />);
    await waitFor(() => {
      expect(screen.getByText(/Balanced Momentum/)).toBeInTheDocument();
    });
    const select = screen.getByLabelText(/Risk Plan/, { selector: "select" }) as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "ver-1" } });
    await waitFor(() => {
      const card = screen.getByTestId("risk-plan-picker-inline");
      expect(card.textContent).toMatch(/score 5/);
      expect(card.textContent).toMatch(/balanced/);
      expect(card.textContent).toMatch(/risk_percent/);
    });
  });
});

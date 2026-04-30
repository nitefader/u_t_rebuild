import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { HorizonRiskPlanPicker } from "./HorizonRiskPlanPicker";
import type { RiskPlanSummary } from "@/api/schemas/riskPlans";

const MOCK_PLANS: RiskPlanSummary[] = [
  {
    risk_plan_id: "aaa",
    name: "Conservative Swing",
    description: null,
    status: "active",
    risk_score: 2,
    risk_tier: "conservative",
    source: "manual",
    ai_generated: false,
    ai_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    created_by: null,
    active_version_id: "ver-aaa-1",
    active_version: {
      risk_plan_version_id: "ver-aaa-1",
      risk_plan_id: "aaa",
      version: 3,
      status: "active",
      config_fingerprint: "fp1",
      config: { sizing_method: "risk_percent" },
      created_at: "2026-01-01T00:00:00Z",
    },
    linked_account_count: 1,
    last_used_at: null,
  },
  {
    risk_plan_id: "bbb",
    name: "Aggressive Scalping",
    description: null,
    status: "active",
    risk_score: 8,
    risk_tier: "aggressive",
    source: "manual",
    ai_generated: false,
    ai_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    created_by: null,
    active_version_id: "ver-bbb-2",
    active_version: {
      risk_plan_version_id: "ver-bbb-2",
      risk_plan_id: "bbb",
      version: 2,
      status: "active",
      config_fingerprint: "fp2",
      config: { sizing_method: "fixed_shares" },
      created_at: "2026-01-01T00:00:00Z",
    },
    linked_account_count: 0,
    last_used_at: null,
  },
  // Plan with no active version — must be excluded from the dropdown.
  {
    risk_plan_id: "ccc",
    name: "Draft Plan",
    description: null,
    status: "draft",
    risk_score: 5,
    risk_tier: "balanced",
    source: "manual",
    ai_generated: false,
    ai_summary: null,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    created_by: null,
    active_version_id: null,
    active_version: undefined,
    linked_account_count: 0,
    last_used_at: null,
  },
];

describe("<HorizonRiskPlanPicker />", () => {
  it('renders the horizon label "Swing" in the select', () => {
    render(
      <HorizonRiskPlanPicker
        horizon="swing"
        selectedRiskPlanVersionId={null}
        availableRiskPlans={MOCK_PLANS}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/Swing risk plan/i)).toBeInTheDocument();
  });

  it("renders — None — as the first option when nothing selected", () => {
    render(
      <HorizonRiskPlanPicker
        horizon="intraday"
        selectedRiskPlanVersionId={null}
        availableRiskPlans={MOCK_PLANS}
        onChange={vi.fn()}
      />,
    );
    const select = screen.getByLabelText(/Intraday risk plan/i) as HTMLSelectElement;
    expect(select.value).toBe("");
    const options = Array.from(select.options).map((o) => o.text);
    expect(options[0]).toBe("— None —");
  });

  it("shows active-version plans but excludes draft-only plans", () => {
    render(
      <HorizonRiskPlanPicker
        horizon="scalping"
        selectedRiskPlanVersionId={null}
        availableRiskPlans={MOCK_PLANS}
        onChange={vi.fn()}
      />,
    );
    const select = screen.getByLabelText(/Scalping risk plan/i) as HTMLSelectElement;
    const optionTexts = Array.from(select.options).map((o) => o.text);
    expect(optionTexts.some((t) => t.includes("Conservative Swing"))).toBe(true);
    expect(optionTexts.some((t) => t.includes("Aggressive Scalping"))).toBe(true);
    // Draft plan has no active version and must be excluded.
    expect(optionTexts.some((t) => t.includes("Draft Plan"))).toBe(false);
  });

  it("reflects the current selection when selectedRiskPlanVersionId is set", () => {
    render(
      <HorizonRiskPlanPicker
        horizon="position"
        selectedRiskPlanVersionId="ver-aaa-1"
        availableRiskPlans={MOCK_PLANS}
        onChange={vi.fn()}
      />,
    );
    const select = screen.getByLabelText(/Position risk plan/i) as HTMLSelectElement;
    expect(select.value).toBe("ver-aaa-1");
  });

  it("calls onChange with a version id when a plan is selected", () => {
    const onChange = vi.fn();
    render(
      <HorizonRiskPlanPicker
        horizon="swing"
        selectedRiskPlanVersionId={null}
        availableRiskPlans={MOCK_PLANS}
        onChange={onChange}
      />,
    );
    const select = screen.getByLabelText(/Swing risk plan/i);
    fireEvent.change(select, { target: { value: "ver-bbb-2" } });
    expect(onChange).toHaveBeenCalledWith("ver-bbb-2");
  });

  it("calls onChange with null when — None — is selected", () => {
    const onChange = vi.fn();
    render(
      <HorizonRiskPlanPicker
        horizon="other"
        selectedRiskPlanVersionId="ver-aaa-1"
        availableRiskPlans={MOCK_PLANS}
        onChange={onChange}
      />,
    );
    const select = screen.getByLabelText(/Other risk plan/i);
    fireEvent.change(select, { target: { value: "" } });
    expect(onChange).toHaveBeenCalledWith(null);
  });

  it("disables the select when disabled prop is true", () => {
    render(
      <HorizonRiskPlanPicker
        horizon="intraday"
        selectedRiskPlanVersionId={null}
        availableRiskPlans={MOCK_PLANS}
        onChange={vi.fn()}
        disabled
      />,
    );
    const select = screen.getByLabelText(/Intraday risk plan/i) as HTMLSelectElement;
    expect(select.disabled).toBe(true);
  });

  it("includes version number in option text", () => {
    render(
      <HorizonRiskPlanPicker
        horizon="swing"
        selectedRiskPlanVersionId={null}
        availableRiskPlans={MOCK_PLANS}
        onChange={vi.fn()}
      />,
    );
    const select = screen.getByLabelText(/Swing risk plan/i) as HTMLSelectElement;
    const optionTexts = Array.from(select.options).map((o) => o.text);
    expect(optionTexts.some((t) => t.includes("(v3)"))).toBe(true);
    expect(optionTexts.some((t) => t.includes("(v2)"))).toBe(true);
  });
});

describe("<HorizonRiskPlanPicker /> — all 5 horizons render", () => {
  const horizons = ["scalping", "intraday", "swing", "position", "other"] as const;

  for (const horizon of horizons) {
    it(`renders horizon label for ${horizon}`, () => {
      render(
        <HorizonRiskPlanPicker
          horizon={horizon}
          selectedRiskPlanVersionId={null}
          availableRiskPlans={[]}
          onChange={vi.fn()}
        />,
      );
      // Each horizon has a distinct aria-label ending in "risk plan"
      const select = screen.getByRole("combobox", { name: new RegExp(horizon, "i") });
      expect(select).toBeInTheDocument();
    });
  }
});
